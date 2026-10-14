from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.models import (
    AppUser, Visit, Disease, Medication, SideEffect, LabTest, Doctor, Patient, Hospital
)
from src.schemas.clinical import DiseaseOut, MedicationOut, VisitCreate, VisitOut
from src.routers.deps import get_current_user, require_role

router = APIRouter(prefix="", tags=["Clinical Encounters & Catalog"])

@router.get("/diseases", response_model=List[DiseaseOut])
async def list_diseases(db: AsyncSession = Depends(get_db)):
    diseases = (await db.execute(select(Disease).order_by(Disease.name.asc()))).scalars().all()
    return diseases

@router.get("/medications", response_model=List[MedicationOut])
async def list_medications(db: AsyncSession = Depends(get_db)):
    meds = (await db.execute(select(Medication).order_by(Medication.name.asc()))).scalars().all()
    return meds

@router.post("/visits", response_model=VisitOut)
async def create_visit(
    visit_data: VisitCreate,
    current_user: AppUser = Depends(require_role(["doctor", "admin"])),
    db: AsyncSession = Depends(get_db)
):
    patient = (await db.execute(select(Patient).where(Patient.id == visit_data.patient_id))).scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")

    doctor = (await db.execute(select(Doctor).where(Doctor.id == visit_data.doctor_id))).scalar_one_or_none()
    if not doctor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found.")

    hosp = (await db.execute(select(Hospital).where(Hospital.id == visit_data.hospital_id))).scalar_one_or_none()
    if not hosp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hospital not found.")

    v = Visit(
        patient_id=visit_data.patient_id,
        doctor_id=visit_data.doctor_id,
        hospital_id=visit_data.hospital_id,
        visit_type=visit_data.visit_type,
        summary_code=visit_data.summary_code
    )
    db.add(v)
    await db.commit()
    await db.refresh(v)

    return VisitOut(
        id=v.id,
        patient_id=v.patient_id,
        doctor_id=v.doctor_id,
        doctor_name=doctor.display_name,
        hospital_name=hosp.name,
        visit_at=v.visit_at,
        visit_type=v.visit_type,
        summary_code=v.summary_code,
        diagnoses=[],
        prescriptions=[],
        treatments=[],
        lab_results=[]
    )
