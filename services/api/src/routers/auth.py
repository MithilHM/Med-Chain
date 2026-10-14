from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.config import settings
from src.models import AppUser, Patient, Doctor
from src.schemas.auth import LoginRequest, TokenResponse, UserOut
from src.services.auth import verify_password, create_access_token, hash_password
from src.routers.deps import get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/login", response_model=TokenResponse)
async def login(credentials: LoginRequest, db: AsyncSession = Depends(get_db)):
    login_id = credentials.user_email
    user = (await db.execute(select(AppUser).where(AppUser.email == login_id))).scalar_one_or_none()
    if not user or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User account is inactive.")

    patient_id = None
    doctor_id = None
    if user.role == "patient":
        pt = (await db.execute(select(Patient).where(Patient.user_id == user.id))).scalar_one_or_none()
        patient_id = pt.id if pt else None
    elif user.role == "doctor":
        doc = (await db.execute(select(Doctor).where(Doctor.user_id == user.id))).scalar_one_or_none()
        doctor_id = doc.id if doc else None

    token = create_access_token(data={"sub": user.id, "role": user.role, "email": user.email})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "role": user.role,
            "is_active": user.is_active,
            "patient_id": patient_id,
            "doctor_id": doctor_id
        }
    }

@router.get("/me", response_model=UserOut)
async def get_me(current_user: AppUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    patient_id = None
    doctor_id = None
    if current_user.role == "patient":
        pt = (await db.execute(select(Patient).where(Patient.user_id == current_user.id))).scalar_one_or_none()
        patient_id = pt.id if pt else None
    elif current_user.role == "doctor":
        doc = (await db.execute(select(Doctor).where(Doctor.user_id == current_user.id))).scalar_one_or_none()
        doctor_id = doc.id if doc else None

    return {
        "id": current_user.id,
        "email": current_user.email,
        "role": current_user.role,
        "is_active": current_user.is_active,
        "patient_id": patient_id,
        "doctor_id": doctor_id
    }

@router.post("/demo-switch")
async def demo_switch(role: str, db: AsyncSession = Depends(get_db)):
    """Convenience helper for local demo presentation only."""
    if not settings.DEMO_MODE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Demo switching disabled in production.")
    
    role_email_map = {
        "patient": "patient@medchain.local",
        "doctor": "doctor@medchain.local",
        "researcher": "researcher@medchain.local",
        "insurance_analyst": "analyst@medchain.local",
        "admin": "admin@medchain.local",
    }
    email = role_email_map.get(role)
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid demo role: {role}")

    user = (await db.execute(select(AppUser).where(AppUser.email == email))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Demo user for role {role} not found. Please run seed script.")

    patient_id = None
    doctor_id = None
    if user.role == "patient":
        pt = (await db.execute(select(Patient).where(Patient.user_id == user.id))).scalar_one_or_none()
        patient_id = pt.id if pt else None
    elif user.role == "doctor":
        doc = (await db.execute(select(Doctor).where(Doctor.user_id == user.id))).scalar_one_or_none()
        doctor_id = doc.id if doc else None

    token = create_access_token(data={"sub": user.id, "role": user.role, "email": user.email})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "role": user.role,
            "is_active": user.is_active,
            "patient_id": patient_id,
            "doctor_id": doctor_id
        }
    }
