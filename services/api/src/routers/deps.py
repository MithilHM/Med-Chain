import logging
from datetime import datetime, timezone
from typing import List, Optional, Set

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.database import get_db
from src.models import (
    AccessEvent, AppUser, CareTeamAssignment, Doctor, EmergencyAccessGrant, Patient, Visit,
)
from src.request_context import current_request_id
from src.services.auth import decode_access_token, get_active_session
from src.services.outbox import OutboxService

logger = logging.getLogger("medchain.deps")
security = HTTPBearer(auto_error=False)


def _utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


async def record_access_event(
    db: AsyncSession,
    actor_id: str,
    patient_id: Optional[str],
    resource_type: str,
    resource_reference: str,
    action: str,
    decision: str = "GRANTED",
    reason: str = "AUTHORIZED",
    commit: bool = True,
) -> AccessEvent:
    """Persist an access decision and queue its chain evidence in the same transaction.

    Commits by default so DENIED decisions survive the HTTPException that usually follows.
    """
    event = AccessEvent(
        actor_user_id=actor_id,
        patient_id=patient_id,
        resource_type=resource_type,
        resource_reference=resource_reference[:150],
        action=action[:50],
        decision=decision,
        reason_code=reason[:100],
        request_id=current_request_id(),
    )
    db.add(event)
    await db.flush()
    await OutboxService.enqueue_access_event(db, event)
    if commit:
        await db.commit()
    return event


async def _record_patient_access(
    db: AsyncSession,
    user: AppUser,
    patient_id: str,
    action: str,
    decision: str,
    reason: str,
) -> None:
    await record_access_event(
        db,
        actor_id=user.id,
        patient_id=patient_id,
        resource_type="PATIENT_RECORD",
        resource_reference=patient_id,
        action=action,
        decision=decision,
        reason=reason,
    )


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> AppUser:
    if credentials and not settings.is_development:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token authentication is disabled; use the secure session flow.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials if credentials else request.cookies.get("medchain_session")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication session required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token_jti = payload.get("jti")
    user_id = payload.get("sub")
    # Fail closed: every token must map to a registered, unrevoked, unexpired session.
    session = await get_active_session(db, token_jti) if token_jti else None
    if not session or not user_id or session.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has been revoked or has expired. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = (await db.execute(select(AppUser).where(AppUser.id == user_id))).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account inactive or not found.",
        )
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not credentials and request.cookies.get("medchain_session"):
        origin = request.headers.get("origin")
        if not origin or origin.rstrip("/") not in {item.rstrip("/") for item in settings.cors_origin_list}:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Request origin is not allowed.")
    return user


def require_role(allowed_roles: List[str]):
    async def role_checker(user: AppUser = Depends(get_current_user)) -> AppUser:
        if user.role not in allowed_roles and user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {allowed_roles}. Current role: {user.role}"
            )
        return user
    return role_checker


def _visit_relationship_filter(now: datetime):
    """A visit grants access while it is open, and for CARE_TEAM_POST_DISCHARGE_DAYS after discharge.
    Cancelled visits grant nothing. VISIT_RELATIONSHIP_ACCESS_DAYS (>0) also caps open visits by age."""
    from datetime import timedelta
    cutoff = now - timedelta(days=settings.CARE_TEAM_POST_DISCHARGE_DAYS)
    conditions = [Visit.status == "ACTIVE", or_(Visit.discharged_at.is_(None), Visit.discharged_at > cutoff)]
    if settings.VISIT_RELATIONSHIP_ACCESS_DAYS > 0:
        conditions.append(Visit.visit_at > now - timedelta(days=settings.VISIT_RELATIONSHIP_ACCESS_DAYS))
    return conditions


async def doctor_access_reason(db: AsyncSession, doctor: Doctor, user: AppUser, patient_id: str) -> Optional[str]:
    """Return why this doctor may access the patient, or None if no relationship exists."""
    now = datetime.now(timezone.utc)
    care = (await db.execute(
        select(CareTeamAssignment.id).where(
            CareTeamAssignment.patient_id == patient_id,
            CareTeamAssignment.doctor_id == doctor.id,
            CareTeamAssignment.active_from <= now,
            or_(CareTeamAssignment.active_until.is_(None), CareTeamAssignment.active_until > now),
        ).limit(1)
    )).scalar_one_or_none()
    if care:
        return "CARE_TEAM_ASSIGNMENT"
    visit = (await db.execute(
        select(Visit.id).where(
            Visit.patient_id == patient_id, Visit.doctor_id == doctor.id, *_visit_relationship_filter(now)
        ).limit(1)
    )).scalar_one_or_none()
    if visit:
        return "ASSIGNED_CARE_ACCESS"
    emergency = (await db.execute(
        select(EmergencyAccessGrant.id).where(
            EmergencyAccessGrant.user_id == user.id,
            EmergencyAccessGrant.patient_id == patient_id,
            EmergencyAccessGrant.expires_at > now,
            EmergencyAccessGrant.review_status != "INAPPROPRIATE",
        ).limit(1)
    )).scalar_one_or_none()
    if emergency:
        return "BREAK_GLASS_EMERGENCY_ACCESS"
    return None


async def doctor_accessible_patient_ids(db: AsyncSession, doctor: Doctor, user: AppUser) -> Set[str]:
    now = datetime.now(timezone.utc)
    visit_ids = (await db.execute(
        select(Visit.patient_id).where(Visit.doctor_id == doctor.id, *_visit_relationship_filter(now)).distinct()
    )).scalars().all()
    care_ids = (await db.execute(
        select(CareTeamAssignment.patient_id).where(
            CareTeamAssignment.doctor_id == doctor.id,
            CareTeamAssignment.active_from <= now,
            or_(CareTeamAssignment.active_until.is_(None), CareTeamAssignment.active_until > now),
        )
    )).scalars().all()
    emergency_ids = (await db.execute(
        select(EmergencyAccessGrant.patient_id).where(
            EmergencyAccessGrant.user_id == user.id,
            EmergencyAccessGrant.expires_at > now,
            EmergencyAccessGrant.review_status != "INAPPROPRIATE",
        )
    )).scalars().all()
    return set(visit_ids) | set(care_ids) | set(emergency_ids)


async def verify_patient_access(
    patient_id: str,
    user: AppUser,
    db: AsyncSession,
    action: str = "READ_PATIENT_RECORD",
):
    """
    Enforces horizontal access control:
    - Admin: can access any patient
    - Patient: can ONLY access their own linked patient ID
    - Doctor: care-team assignment, a visit relationship, or an active break-glass grant
    - Others: forbidden
    A record merged into another patient is read-only history; callers are pointed to the survivor.
    """
    merged_into = (await db.execute(
        select(Patient.merged_into_id).where(Patient.id == patient_id, Patient.record_status == "MERGED")
    )).scalar_one_or_none()
    if merged_into and not action.startswith(("READ_", "LIST_", "VERIFY_", "FHIR_EXPORT")):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "This record was merged into another patient record.", "merged_into": merged_into},
        )

    if user.role == "admin":
        patient_exists = (await db.execute(select(Patient.id).where(Patient.id == patient_id))).scalar_one_or_none()
        if patient_exists:
            await _record_patient_access(db, user, patient_id, action, "GRANTED", "ADMIN_ACCESS")
        return True

    if user.role == "patient":
        pt = (await db.execute(select(Patient).where(Patient.user_id == user.id))).scalar_one_or_none()
        if not pt or pt.id != patient_id:
            patient_exists = (await db.execute(select(Patient.id).where(Patient.id == patient_id))).scalar_one_or_none()
            if patient_exists:
                await _record_patient_access(db, user, patient_id, action, "DENIED", "NOT_OWN_PATIENT")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You are not authorized to view another patient's medical records."
            )
        await _record_patient_access(db, user, patient_id, action, "GRANTED", "PATIENT_SELF_ACCESS")
        return True

    if user.role == "doctor":
        doc = (await db.execute(select(Doctor).where(Doctor.user_id == user.id))).scalar_one_or_none()
        if not doc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Doctor profile not found.")
        reason = await doctor_access_reason(db, doc, user, patient_id)
        if reason is None:
            patient_exists = (await db.execute(select(Patient.id).where(Patient.id == patient_id))).scalar_one_or_none()
            if patient_exists:
                await _record_patient_access(db, user, patient_id, action, "DENIED", "NOT_ASSIGNED_TO_CARE")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: This patient is not assigned to your care. Use break-the-glass in an emergency.",
            )
        await _record_patient_access(db, user, patient_id, action, "GRANTED", reason)
        return True

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Role '{user.role}' is not authorized for direct patient record access."
    )
