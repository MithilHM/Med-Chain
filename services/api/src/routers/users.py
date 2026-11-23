"""Administrator management of staff accounts, hospitals, and directory reference data.

Staff accounts are created here (or by SSO/SCIM). A new local account has no usable password;
the person sets one through a one-time activation link. Patients never get accounts here:
they sign up through the patient-portal activation code issued at registration.
"""
import secrets
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.database import get_db
from src.models import (
    AccountInvitation, AppUser, Doctor, Hospital, InsuranceAnalyst, InsuranceProvider,
)
from src.routers.deps import get_current_user, record_access_event, require_role
from src.services import accounts
from src.services.auth import revoke_all_user_sessions

router = APIRouter(tags=["Administration: Users & Directory"])

STAFF_ROLES = ("doctor", "researcher", "insurance_analyst", "admin")
PENDING_PASSWORD_PREFIX = "!pending-activation:"


class StaffCreate(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)
    role: str = Field(..., pattern="^(doctor|researcher|insurance_analyst|admin)$")
    # doctor profile
    display_name: Optional[str] = Field(default=None, max_length=100)
    specialty: Optional[str] = Field(default=None, max_length=100)
    hospital_id: Optional[str] = None
    external_provider_id: Optional[str] = Field(default=None, max_length=64)
    # insurance analyst profile
    insurance_provider_id: Optional[str] = None


class StaffUpdate(BaseModel):
    is_active: Optional[bool] = None
    role: Optional[str] = Field(default=None, pattern="^(doctor|researcher|insurance_analyst|admin)$")


class HospitalCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=150)
    region: str = Field(..., min_length=1, max_length=100)
    facility_code: str = Field(..., min_length=2, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")


def _activation_link(token: str) -> str:
    return f"/signup?token={token}"


async def _user_out(db: AsyncSession, user: AppUser) -> dict:
    doctor = (await db.execute(select(Doctor).where(Doctor.user_id == user.id))).scalar_one_or_none()
    analyst = (await db.execute(select(InsuranceAnalyst).where(InsuranceAnalyst.user_id == user.id))).scalar_one_or_none()
    pending = (await db.execute(
        select(func.count(AccountInvitation.id)).where(
            AccountInvitation.user_id == user.id, AccountInvitation.used_at.is_(None),
            AccountInvitation.revoked_at.is_(None), AccountInvitation.purpose == "STAFF_ACTIVATION",
        )
    )).scalar() or 0
    return {
        "id": user.id, "email": user.email, "role": user.role, "is_active": user.is_active,
        "auth_source": user.auth_source, "mfa_enabled": bool(user.mfa_enabled),
        "last_login_at": user.last_login_at, "created_at": user.created_at,
        "activation_pending": user.password_hash.startswith(PENDING_PASSWORD_PREFIX) and pending > 0,
        "locked": bool(user.locked_until),
        "doctor": {"id": doctor.id, "display_name": doctor.display_name, "specialty": doctor.specialty,
                   "hospital_id": doctor.hospital_id, "external_provider_id": doctor.external_provider_id} if doctor else None,
        "insurance_provider_id": analyst.provider_id if analyst else None,
    }


@router.get("/admin/users")
async def list_users(
    role: Optional[str] = None,
    q: Optional[str] = Query(default=None, max_length=100),
    include_patients: bool = False,
    current_user: AppUser = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db),
):
    query = select(AppUser).order_by(AppUser.created_at.desc()).limit(500)
    if role:
        query = query.where(AppUser.role == role)
    elif not include_patients:
        query = query.where(AppUser.role != "patient")
    if q:
        query = query.where(AppUser.email.contains(q.strip().lower()))
    return [await _user_out(db, user) for user in (await db.execute(query)).scalars().all()]


@router.post("/admin/users")
async def create_staff_user(
    body: StaffCreate,
    current_user: AppUser = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db),
):
    email = body.email.strip().lower()
    if "@" not in email:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Enter a valid email address.")
    if (await db.execute(select(AppUser.id).where(AppUser.email == email))).scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists.")
    if body.role == "doctor":
        if not (body.display_name and body.specialty and body.hospital_id):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="Doctors need a display name, specialty, and hospital.")
        if await db.get(Hospital, body.hospital_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hospital not found.")
        if body.external_provider_id and (await db.execute(
            select(Doctor.id).where(Doctor.external_provider_id == body.external_provider_id)
        )).scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That provider ID is already registered.")
    if body.role == "insurance_analyst":
        if not body.insurance_provider_id or await db.get(InsuranceProvider, body.insurance_provider_id) is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Choose the analyst's insurance provider.")

    user = AppUser(email=email, role=body.role, auth_source="LOCAL",
                   password_hash=PENDING_PASSWORD_PREFIX + secrets.token_hex(16))
    db.add(user)
    await db.flush()
    if body.role == "doctor":
        db.add(Doctor(user_id=user.id, hospital_id=body.hospital_id, display_name=body.display_name.strip(),
                      specialty=body.specialty.strip(), external_provider_id=(body.external_provider_id or None)))
    if body.role == "insurance_analyst":
        db.add(InsuranceAnalyst(user_id=user.id, provider_id=body.insurance_provider_id))
    invitation, token = await accounts.issue_invitation(db, "STAFF_ACTIVATION", created_by=current_user.id, user_id=user.id)
    await record_access_event(db, current_user.id, None, "USER_ACCOUNT", user.id, "CREATE_STAFF_ACCOUNT",
                              "GRANTED", f"ROLE_{body.role.upper()}", commit=False)
    await db.commit()
    return {
        "user": await _user_out(db, user),
        "activation_token": token,
        "activation_link": _activation_link(token),
        "expires_at": invitation.expires_at,
        "note": "Give this one-time link to the person through a trusted channel. It is shown only once.",
    }


@router.patch("/admin/users/{user_id}")
async def update_staff_user(
    user_id: str,
    body: StaffUpdate,
    current_user: AppUser = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(AppUser, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if user.id == current_user.id and (body.is_active is False or (body.role and body.role != "admin")):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="You cannot deactivate or demote your own account.")
    if body.role and body.role != user.role:
        if user.role == "patient":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Patient portal accounts cannot become staff accounts.")
        if body.role == "doctor" and not (await db.execute(select(Doctor.id).where(Doctor.user_id == user.id))).scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Create a doctor profile first (new doctor account).")
        if body.role == "insurance_analyst" and not (await db.execute(
            select(InsuranceAnalyst.id).where(InsuranceAnalyst.user_id == user.id)
        )).scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Create an analyst profile first (new analyst account).")
        await record_access_event(db, current_user.id, None, "USER_ACCOUNT", user.id, "CHANGE_ROLE", "GRANTED",
                                  f"{user.role.upper()}_TO_{body.role.upper()}", commit=False)
        user.role = body.role
        await revoke_all_user_sessions(db, user.id)  # new permissions take effect at next sign-in
    if body.is_active is not None and body.is_active != user.is_active:
        user.is_active = body.is_active
        if not body.is_active:
            await revoke_all_user_sessions(db, user.id)
        await record_access_event(db, current_user.id, None, "USER_ACCOUNT", user.id,
                                  "REACTIVATE_ACCOUNT" if body.is_active else "DEACTIVATE_ACCOUNT", "GRANTED",
                                  "ADMIN_ACTION", commit=False)
    await db.commit()
    return await _user_out(db, user)


@router.post("/admin/users/{user_id}/password-reset")
async def issue_password_reset(
    user_id: str,
    current_user: AppUser = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(AppUser, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if user.auth_source != "LOCAL":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="SSO account passwords are reset in the hospital identity provider.")
    purpose = "STAFF_ACTIVATION" if user.password_hash.startswith(PENDING_PASSWORD_PREFIX) else "PASSWORD_RESET"
    invitation, token = await accounts.issue_invitation(db, purpose, created_by=current_user.id, user_id=user.id)
    await revoke_all_user_sessions(db, user.id)
    await record_access_event(db, current_user.id, None, "USER_ACCOUNT", user.id, "ISSUE_PASSWORD_RESET", "GRANTED",
                              purpose, commit=False)
    await db.commit()
    return {"activation_token": token, "activation_link": _activation_link(token), "expires_at": invitation.expires_at,
            "purpose": purpose}


@router.post("/admin/users/{user_id}/mfa-reset")
async def reset_user_mfa(
    user_id: str,
    current_user: AppUser = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(AppUser, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if user.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Another administrator must reset your MFA.")
    user.mfa_enabled, user.mfa_secret_encrypted, user.mfa_recovery_hashes, user.mfa_last_timestep = False, None, None, None
    await revoke_all_user_sessions(db, user.id)
    await record_access_event(db, current_user.id, None, "USER_ACCOUNT", user.id, "RESET_MFA", "GRANTED",
                              "LOST_AUTHENTICATOR", commit=False)
    await db.commit()
    return {"status": "MFA_RESET", "note": "The user must enroll a new authenticator at next sign-in."}


@router.get("/admin/hospitals")
async def list_hospitals(current_user: AppUser = Depends(require_role(["admin"])), db: AsyncSession = Depends(get_db)):
    hospitals = (await db.execute(select(Hospital).order_by(Hospital.name))).scalars().all()
    allowed = settings.allowed_facility_codes
    return [{"id": h.id, "name": h.name, "region": h.region, "facility_code": h.facility_code,
             "served_by_installation": not allowed or h.facility_code in allowed} for h in hospitals]


@router.post("/admin/hospitals")
async def create_hospital(body: HospitalCreate, current_user: AppUser = Depends(require_role(["admin"])),
                          db: AsyncSession = Depends(get_db)):
    if (await db.execute(select(Hospital.id).where(Hospital.facility_code == body.facility_code))).scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That facility code is already registered.")
    hospital = Hospital(name=body.name.strip(), region=body.region.strip(), facility_code=body.facility_code)
    db.add(hospital)
    await db.flush()
    await record_access_event(db, current_user.id, None, "DIRECTORY", hospital.id, "CREATE_HOSPITAL", "GRANTED",
                              "ADMIN_ACTION", commit=False)
    await db.commit()
    return {"id": hospital.id, "name": hospital.name, "region": hospital.region, "facility_code": hospital.facility_code}


@router.get("/admin/insurance-providers")
async def list_insurance_providers(current_user: AppUser = Depends(require_role(["admin"])),
                                   db: AsyncSession = Depends(get_db)):
    providers = (await db.execute(select(InsuranceProvider).order_by(InsuranceProvider.name))).scalars().all()
    return [{"id": p.id, "name": p.name, "provider_code": p.provider_code} for p in providers]


@router.get("/doctors")
async def list_doctors(current_user: AppUser = Depends(require_role(["doctor", "admin"])),
                       db: AsyncSession = Depends(get_db)):
    """Directory of active doctors (for care-team and encounter assignment)."""
    rows = (await db.execute(
        select(Doctor, Hospital, AppUser)
        .join(Hospital, Hospital.id == Doctor.hospital_id)
        .join(AppUser, AppUser.id == Doctor.user_id)
        .where(AppUser.is_active.is_(True))
        .order_by(Doctor.display_name)
    )).all()
    return [{"id": d.id, "display_name": d.display_name, "specialty": d.specialty, "hospital_id": h.id,
             "hospital_name": h.name, "external_provider_id": d.external_provider_id} for d, h, _ in rows]
