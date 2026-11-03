import logging
from typing import List, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.services.auth import decode_access_token
from src.models import AppUser, Patient, Doctor, Visit, AccessEvent
from src.services.blockchain import BlockchainService

logger = logging.getLogger("medchain.deps")
security = HTTPBearer(auto_error=False)

async def record_access_event(
    db: AsyncSession,
    actor_id: str,
    patient_id: Optional[str],
    resource_type: str,
    resource_reference: str,
    action: str,
    decision: str = "GRANTED",
    reason: str = "AUTHORIZED",
) -> AccessEvent:
    event = AccessEvent(
        actor_user_id=actor_id,
        patient_id=patient_id,
        resource_type=resource_type,
        resource_reference=resource_reference,
        action=action,
        decision=decision,
        reason_code=reason,
    )
    db.add(event)
    await db.flush()
    await db.commit()
    try:
        chain_status, tx_hash = await BlockchainService.log_access_event(
            event.id, actor_id, resource_reference, action, decision
        )
        if chain_status == "CONFIRMED":
            event.chain_tx_hash = tx_hash
            await db.commit()
    except Exception as exc:
        logger.warning("Could not anchor access event %s: %s", event.id, exc)
    return event

async def _record_patient_access(
    db: AsyncSession,
    user: AppUser,
    patient_id: str,
    action: str,
    decision: str,
    reason: str,
) -> None:
    """Persist an access decision and best-effort mirror it to the audit chain."""
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
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> AppUser:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload.",
        )
    user = (await db.execute(select(AppUser).where(AppUser.id == user_id))).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account inactive or not found.",
        )
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
    - Doctor: can access assigned patients
    - Others: forbidden
    """
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
        assignment = await db.execute(
            select(Visit.id).where(Visit.patient_id == patient_id, Visit.doctor_id == doc.id).limit(1)
        )
        if assignment.scalar_one_or_none() is None:
            patient_exists = (await db.execute(select(Patient.id).where(Patient.id == patient_id))).scalar_one_or_none()
            if patient_exists:
                await _record_patient_access(db, user, patient_id, action, "DENIED", "NOT_ASSIGNED_TO_CARE")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: This patient is not assigned to your care.",
            )
        await _record_patient_access(db, user, patient_id, action, "GRANTED", "ASSIGNED_CARE_ACCESS")
        return True

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Role '{user.role}' is not authorized for direct patient record access."
    )
