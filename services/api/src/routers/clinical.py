"""Clinical encounters and clinical data entry (diagnoses, prescriptions, lab results, discharge).

Doctors work under their own profile on patients they have a care relationship with; administrators
may record on behalf of a chosen doctor (for corrections and back-entry). Every write is audited,
and new results are pushed to the care team's live feed.
"""
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.database import get_db
from src.models import (
    AppUser, CareTeamAssignment, Diagnosis, Disease, Doctor, Hospital, LabResult, LabTest, Medication, Patient,
    Prescription, Visit,
)
from src.routers.deps import record_access_event, require_role, verify_patient_access
from src.schemas.clinical import DiseaseOut, MedicationOut, VisitCreate, VisitOut
from src.services.events import ClinicalEvent, EventBus

router = APIRouter(prefix="", tags=["Clinical Encounters & Catalog"])

_RANGE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*[-–]\s*(-?\d+(?:\.\d+)?)")


class DiagnosisCreate(BaseModel):
    disease_code: str = Field(..., max_length=50)
    severity: str = Field(..., pattern="^(Mild|Moderate|Severe|Critical)$")
    status: str = Field(default="Active", pattern="^(Active|Resolved|Remission|Ruled out)$")


class PrescriptionCreate(BaseModel):
    medication_code: str = Field(..., max_length=50)
    dose_text: str = Field(..., min_length=1, max_length=100)
    frequency_text: str = Field(..., min_length=1, max_length=100)
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class LabResultCreate(BaseModel):
    lab_test_code: str = Field(..., max_length=50)
    result_value: Decimal
    measured_at: Optional[datetime] = None
    is_abnormal: Optional[bool] = Field(default=None, description="Leave empty to derive from the reference range")


@router.get("/diseases", response_model=List[DiseaseOut])
async def list_diseases(db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(Disease).order_by(Disease.name.asc()))).scalars().all()


@router.get("/medications", response_model=List[MedicationOut])
async def list_medications(db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(Medication).order_by(Medication.name.asc()))).scalars().all()


@router.get("/lab-tests")
async def list_lab_tests(db: AsyncSession = Depends(get_db)):
    tests = (await db.execute(select(LabTest).order_by(LabTest.name.asc()))).scalars().all()
    return [{"id": t.id, "code": t.code, "name": t.name, "unit": t.unit, "reference_range_text": t.reference_range_text}
            for t in tests]


async def _acting_doctor(db: AsyncSession, user: AppUser, requested_doctor_id: Optional[str]) -> Doctor:
    if user.role == "doctor":
        own = (await db.execute(select(Doctor).where(Doctor.user_id == user.id))).scalar_one_or_none()
        if own is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Doctor profile not found.")
        if requested_doctor_id and requested_doctor_id != own.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Doctors may create visits only under their own profile.")
        return own
    if not requested_doctor_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Choose the attending doctor for this encounter.")
    doctor = await db.get(Doctor, requested_doctor_id)
    if doctor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found.")
    return doctor


def _visit_out(v: Visit, doctor: Optional[Doctor], hospital: Optional[Hospital]) -> VisitOut:
    return VisitOut(id=v.id, patient_id=v.patient_id, doctor_id=v.doctor_id,
                    doctor_name=doctor.display_name if doctor else None, hospital_id=v.hospital_id,
                    hospital_name=hospital.name if hospital else None, visit_at=v.visit_at, visit_type=v.visit_type,
                    summary_code=v.summary_code, status=v.status, discharged_at=v.discharged_at,
                    diagnoses=[], prescriptions=[], treatments=[], lab_results=[])


@router.post("/visits", response_model=VisitOut)
async def create_visit(
    visit_data: VisitCreate,
    current_user: AppUser = Depends(require_role(["doctor", "admin"])),
    db: AsyncSession = Depends(get_db)
):
    patient = await db.get(Patient, visit_data.patient_id)
    if not patient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")
    await verify_patient_access(patient.id, current_user, db, action="CREATE_PATIENT_VISIT")
    doctor = await _acting_doctor(db, current_user, visit_data.doctor_id)
    hospital_id = visit_data.hospital_id or doctor.hospital_id
    if current_user.role == "doctor" and hospital_id != doctor.hospital_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Visit hospital must match the doctor's assigned hospital.")
    hospital = await db.get(Hospital, hospital_id)
    if not hospital:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hospital not found.")
    visit_at = visit_data.visit_at or datetime.now(timezone.utc)
    if (visit_at if visit_at.tzinfo else visit_at.replace(tzinfo=timezone.utc)) > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Encounters cannot be recorded in the future.")

    v = Visit(patient_id=patient.id, doctor_id=doctor.id, hospital_id=hospital.id, visit_type=visit_data.visit_type,
              summary_code=visit_data.summary_code, visit_at=visit_at)
    db.add(v)
    await db.flush()
    await record_access_event(db, current_user.id, patient.id, "VISIT", v.id, "CREATE_VISIT", "GRANTED",
                              visit_data.visit_type.upper().replace(" ", "_")[:60], commit=False)
    await db.commit()
    await db.refresh(v)
    EventBus.publish(ClinicalEvent("encounter.recorded", patient.id, {"visit_id": v.id, "visit_type": v.visit_type}))
    return _visit_out(v, doctor, hospital)


async def _writable_visit(db: AsyncSession, visit_id: str, user: AppUser, action: str) -> Visit:
    visit = await db.get(Visit, visit_id)
    if visit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Visit not found.")
    if visit.status != "ACTIVE":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This visit was cancelled and cannot be changed.")
    await verify_patient_access(visit.patient_id, user, db, action=action)
    return visit


@router.post("/visits/{visit_id}/diagnoses")
async def add_diagnosis(visit_id: str, body: DiagnosisCreate,
                        current_user: AppUser = Depends(require_role(["doctor", "admin"])),
                        db: AsyncSession = Depends(get_db)):
    visit = await _writable_visit(db, visit_id, current_user, "RECORD_DIAGNOSIS")
    disease = (await db.execute(select(Disease).where(Disease.code == body.disease_code))).scalar_one_or_none()
    if disease is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown diagnosis code; choose one from the catalog.")
    diagnosis = Diagnosis(visit_id=visit.id, disease_id=disease.id, severity=body.severity, status=body.status,
                          notes_reference="Recorded in MedChain")
    db.add(diagnosis)
    await db.flush()
    await record_access_event(db, current_user.id, visit.patient_id, "DIAGNOSIS", diagnosis.id, "RECORD_DIAGNOSIS",
                              "GRANTED", disease.code, commit=False)
    await db.commit()
    EventBus.publish(ClinicalEvent("diagnosis.recorded", visit.patient_id, {"visit_id": visit.id, "code": disease.code}))
    return {"id": diagnosis.id, "disease_code": disease.code, "disease_name": disease.name,
            "severity": diagnosis.severity, "status": diagnosis.status, "diagnosed_at": diagnosis.diagnosed_at}


@router.post("/visits/{visit_id}/prescriptions")
async def add_prescription(visit_id: str, body: PrescriptionCreate,
                           current_user: AppUser = Depends(require_role(["doctor", "admin"])),
                           db: AsyncSession = Depends(get_db)):
    visit = await _writable_visit(db, visit_id, current_user, "RECORD_PRESCRIPTION")
    medication = (await db.execute(select(Medication).where(Medication.code == body.medication_code))).scalar_one_or_none()
    if medication is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown medication code; choose one from the formulary.")
    start = body.start_date or date.today()
    if body.end_date and body.end_date < start:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="End date must be on or after the start date.")
    prescriber = await _acting_doctor(db, current_user, visit.doctor_id if current_user.role == "admin" else None)
    prescription = Prescription(visit_id=visit.id, medication_id=medication.id, start_date=start, end_date=body.end_date,
                                dose_text=body.dose_text.strip(), frequency_text=body.frequency_text.strip(),
                                prescribed_by=prescriber.id)
    db.add(prescription)
    await db.flush()
    await record_access_event(db, current_user.id, visit.patient_id, "PRESCRIPTION", prescription.id,
                              "RECORD_PRESCRIPTION", "GRANTED", medication.code, commit=False)
    await db.commit()
    EventBus.publish(ClinicalEvent("prescription.recorded", visit.patient_id, {"visit_id": visit.id, "code": medication.code}))
    return {"id": prescription.id, "medication_code": medication.code, "medication_name": medication.name,
            "dose_text": prescription.dose_text, "frequency_text": prescription.frequency_text,
            "start_date": prescription.start_date, "end_date": prescription.end_date}


def _outside_range(value: Decimal, reference: str) -> Optional[bool]:
    match = _RANGE.match(reference or "")
    if not match:
        return None
    low, high = Decimal(match.group(1)), Decimal(match.group(2))
    return value < low or value > high


@router.post("/visits/{visit_id}/lab-results")
async def add_lab_result(visit_id: str, body: LabResultCreate,
                         current_user: AppUser = Depends(require_role(["doctor", "admin"])),
                         db: AsyncSession = Depends(get_db)):
    visit = await _writable_visit(db, visit_id, current_user, "RECORD_LAB_RESULT")
    lab_test = (await db.execute(select(LabTest).where(LabTest.code == body.lab_test_code))).scalar_one_or_none()
    if lab_test is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown lab test code.")
    measured_at = body.measured_at or datetime.now(timezone.utc)
    derived = _outside_range(body.result_value, lab_test.reference_range_text)
    abnormal = body.is_abnormal if body.is_abnormal is not None else bool(derived)
    result = LabResult(visit_id=visit.id, lab_test_id=lab_test.id, result_value=body.result_value,
                       measured_at=measured_at, is_abnormal=abnormal, result_status="F")
    db.add(result)
    await db.flush()
    await record_access_event(db, current_user.id, visit.patient_id, "LAB_RESULT", result.id, "RECORD_LAB_RESULT",
                              "GRANTED", lab_test.code, commit=False)
    await db.commit()
    EventBus.publish(ClinicalEvent("lab_result.created", visit.patient_id, {
        "lab_result_id": result.id, "visit_id": visit.id, "test_code": lab_test.code, "abnormal": abnormal,
        "critical": False, "result_status": "F",
    }))
    return {"id": result.id, "test_code": lab_test.code, "test_name": lab_test.name, "result_value": float(body.result_value),
            "unit": lab_test.unit, "reference_range_text": lab_test.reference_range_text, "is_abnormal": abnormal,
            "abnormal_derived_from_range": body.is_abnormal is None and derived is not None, "measured_at": measured_at}


@router.post("/visits/{visit_id}/discharge")
async def discharge_visit(visit_id: str, current_user: AppUser = Depends(require_role(["doctor", "admin"])),
                          db: AsyncSession = Depends(get_db)):
    visit = await _writable_visit(db, visit_id, current_user, "DISCHARGE_VISIT")
    if visit.discharged_at:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This visit is already closed.")
    now = datetime.now(timezone.utc)
    visit.discharged_at = now
    # Encounter-based attending access ends after the configured post-discharge window.
    until = now + timedelta(days=settings.CARE_TEAM_POST_DISCHARGE_DAYS)
    for assignment in (await db.execute(select(CareTeamAssignment).where(
        CareTeamAssignment.patient_id == visit.patient_id, CareTeamAssignment.doctor_id == visit.doctor_id,
        CareTeamAssignment.relationship_type == "ATTENDING",
        or_(CareTeamAssignment.active_until.is_(None), CareTeamAssignment.active_until > until),
    ))).scalars().all():
        assignment.active_until = until
    await record_access_event(db, current_user.id, visit.patient_id, "VISIT", visit.id, "DISCHARGE_VISIT", "GRANTED",
                              "ENCOUNTER_CLOSED", commit=False)
    await db.commit()
    EventBus.publish(ClinicalEvent("encounter.discharged", visit.patient_id, {"visit_id": visit.id}))
    return {"id": visit.id, "status": "DISCHARGED", "discharged_at": now}
