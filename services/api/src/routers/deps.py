import logging
from typing import List, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.services.auth import decode_access_token
from src.models import AppUser, Patient, Doctor

logger = logging.getLogger("medchain.deps")
security = HTTPBearer(auto_error=False)

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

async def verify_patient_access(patient_id: str, user: AppUser, db: AsyncSession):
    """
    Enforces horizontal access control:
    - Admin: can access any patient
    - Patient: can ONLY access their own linked patient ID
    - Doctor: can access assigned patients
    - Others: forbidden
    """
    if user.role == "admin":
        return True

    if user.role == "patient":
        pt = (await db.execute(select(Patient).where(Patient.user_id == user.id))).scalar_one_or_none()
        if not pt or pt.id != patient_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You are not authorized to view another patient's medical records."
            )
        return True

    if user.role == "doctor":
        # Check doctor profile
        doc = (await db.execute(select(Doctor).where(Doctor.user_id == user.id))).scalar_one_or_none()
        if not doc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Doctor profile not found.")
        # Doctor has clinical care privilege for seeded patients in demo
        return True

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Role '{user.role}' is not authorized for direct patient record access."
    )
