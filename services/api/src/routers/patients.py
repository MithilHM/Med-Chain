from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.models import (
    AppUser, Patient, Visit, Diagnosis, Disease, Prescription, Medication,
    Treatment, LabResult, LabTest, ObservedAdverseEvent, SideEffect, Doctor, Hospital
)
from src.schemas.clinical import PatientOut, PatientTimelineOut, VisitOut, DiagnosisOut, PrescriptionOut, LabResultOut, TreatmentOut, AdverseEventOut
from src.routers.deps import get_current_user, require_role, verify_patient_access

router = APIRouter(prefix="/patients", tags=["Patients"])

@router.get("", response_model=List[PatientOut])
async def list_patients(
    current_user: AppUser = Depends(require_role(["doctor", "patient", "admin"])),
    db: AsyncSession = Depends(get_db)
):
    if current_user.role == "patient":
        pt = (await db.execute(select(Patient).where(Patient.user_id == current_user.id))).scalar_one_or_none()
        return [pt] if pt else []
    
    # Doctor or Admin
    pts = (await db.execute(select(Patient).order_by(Patient.display_code.asc()))).scalars().all()
    return pts

@router.get("/{patient_id}", response_model=PatientOut)
async def get_patient(
    patient_id: str,
    current_user: AppUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    await verify_patient_access(patient_id, current_user, db)
    pt = (await db.execute(select(Patient).where(Patient.id == patient_id))).scalar_one_or_none()
    if not pt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")
    return pt

@router.get("/{patient_id}/timeline", response_model=PatientTimelineOut)
async def get_patient_timeline(
    patient_id: str,
    current_user: AppUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    await verify_patient_access(patient_id, current_user, db)
    pt = (await db.execute(select(Patient).where(Patient.id == patient_id))).scalar_one_or_none()
    if not pt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")

    # Fetch visits
    visits = (await db.execute(
        select(Visit).where(Visit.patient_id == patient_id).order_by(Visit.visit_at.desc())
    )).scalars().all()

    visits_out = []
    for v in visits:
        doc = (await db.execute(select(Doctor).where(Doctor.id == v.doctor_id))).scalar_one_or_none()
        hosp = (await db.execute(select(Hospital).where(Hospital.id == v.hospital_id))).scalar_one_or_none()

        # Diagnoses
        diags = (await db.execute(select(Diagnosis).where(Diagnosis.visit_id == v.id))).scalars().all()
        diags_out = []
        for d in diags:
            dis = (await db.execute(select(Disease).where(Disease.id == d.disease_id))).scalar_one_or_none()
            diags_out.append(DiagnosisOut(
                id=d.id,
                disease_code=dis.code if dis else "",
                disease_name=dis.name if dis else "",
                severity=d.severity,
                status=d.status,
                diagnosed_at=d.diagnosed_at
            ))

        # Prescriptions
        prescs = (await db.execute(select(Prescription).where(Prescription.visit_id == v.id))).scalars().all()
        prescs_out = []
        for pr in prescs:
            med = (await db.execute(select(Medication).where(Medication.id == pr.medication_id))).scalar_one_or_none()
            prescs_out.append(PrescriptionOut(
                id=pr.id,
                medication_name=med.name if med else "",
                medication_code=med.code if med else "",
                dose_text=pr.dose_text,
                frequency_text=pr.frequency_text,
                start_date=pr.start_date,
                end_date=pr.end_date
            ))

        # Treatments
        treats = (await db.execute(select(Treatment).where(Treatment.visit_id == v.id))).scalars().all()
        treats_out = [
            TreatmentOut(
                id=t.id,
                treatment_type=t.treatment_type,
                description_code=t.description_code,
                start_date=t.start_date,
                end_date=t.end_date,
                outcome_status=t.outcome_status
            )
            for t in treats
        ]

        # Labs
        labs = (await db.execute(select(LabResult).where(LabResult.visit_id == v.id))).scalars().all()
        labs_out = []
        for l in labs:
            lt = (await db.execute(select(LabTest).where(LabTest.id == l.lab_test_id))).scalar_one_or_none()
            labs_out.append(LabResultOut(
                id=l.id,
                test_name=lt.name if lt else "",
                test_code=lt.code if lt else "",
                result_value=float(l.result_value),
                unit=lt.unit if lt else "",
                reference_range_text=lt.reference_range_text if lt else "",
                is_abnormal=l.is_abnormal,
                measured_at=l.measured_at
            ))

        visits_out.append(VisitOut(
            id=v.id,
            patient_id=v.patient_id,
            doctor_id=v.doctor_id,
            doctor_name=doc.display_name if doc else None,
            hospital_name=hosp.name if hosp else None,
            visit_at=v.visit_at,
            visit_type=v.visit_type,
            summary_code=v.summary_code,
            diagnoses=diags_out,
            prescriptions=prescs_out,
            treatments=treats_out,
            lab_results=labs_out
        ))

    # Adverse events
    aes = (await db.execute(select(ObservedAdverseEvent).where(ObservedAdverseEvent.patient_id == patient_id))).scalars().all()
    aes_out = []
    for ae in aes:
        se = (await db.execute(select(SideEffect).where(SideEffect.id == ae.side_effect_id))).scalar_one_or_none()
        aes_out.append(AdverseEventOut(
            id=ae.id,
            side_effect_name=se.name if se else "",
            side_effect_code=se.code if se else "",
            severity=ae.severity,
            outcome=ae.outcome,
            evidence_quality=ae.evidence_quality,
            reported_at=ae.reported_at
        ))

    return PatientTimelineOut(
        patient=pt,
        visits=visits_out,
        adverse_events=aes_out
    )
