import logging
from typing import List, Optional
from datetime import date, datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.services.crypto import name_blind_index
from src.config import settings
from src.database import get_db
from src.models import (
    AppUser, Patient, Visit, Diagnosis, Disease, Prescription, Medication,
    Treatment, LabResult, LabTest, ObservedAdverseEvent, SideEffect, Doctor, Hospital,
    AccessEvent, CareTeamAssignment, EmergencyAccessGrant, PatientIdentifier,
)
from src.schemas.clinical import PatientOut, PatientTimelineOut, VisitOut, DiagnosisOut, PrescriptionOut, LabResultOut, TreatmentOut, AdverseEventOut
from src.routers.deps import (
    doctor_accessible_patient_ids, get_current_user, require_role, verify_patient_access, record_access_event,
)
from src.services.events import ClinicalEvent, EventBus

router = APIRouter(prefix="/patients", tags=["Patients"])
logger = logging.getLogger("medchain.patients")


class PatientCreate(BaseModel):
    display_code: str = Field(..., min_length=1, max_length=50)
    date_of_birth: date
    sex: str = Field(..., pattern="^[MFO]$")
    # Assigning authority for display_code as an MRN (e.g. the hospital facility code).
    identifier_system: Optional[str] = Field(default=None, max_length=150)
    given_name: Optional[str] = Field(default=None, max_length=100)
    family_name: Optional[str] = Field(default=None, max_length=100)


class BreakGlassRequest(BaseModel):
    justification: str = Field(..., min_length=10, max_length=2000)

@router.get("", response_model=List[PatientOut])
async def list_patients(
    family_name: Optional[str] = Query(default=None, max_length=100, description="Exact family-name search"),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    current_user: AppUser = Depends(require_role(["doctor", "patient", "admin"])),
    db: AsyncSession = Depends(get_db)
):
    if current_user.role == "patient":
        pt = (await db.execute(select(Patient).where(Patient.user_id == current_user.id))).scalar_one_or_none()
        return [pt] if pt else []

    patient_query = select(Patient).order_by(Patient.display_code.asc())
    if family_name:
        index = name_blind_index(family_name)
        if index is None:
            return []
        patient_query = patient_query.where(Patient.family_name_index == index)
    if current_user.role == "doctor":
        doctor = (await db.execute(select(Doctor).where(Doctor.user_id == current_user.id))).scalar_one_or_none()
        if not doctor:
            return []
        accessible = await doctor_accessible_patient_ids(db, doctor, current_user)
        if not accessible:
            return []
        patient_query = patient_query.where(Patient.id.in_(accessible))
    return (await db.execute(patient_query.offset(offset).limit(limit))).scalars().all()

@router.get("/{patient_id}", response_model=PatientOut)
async def get_patient(
    patient_id: str,
    current_user: AppUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    await verify_patient_access(patient_id, current_user, db, action="READ_PATIENT_PROFILE")
    pt = (await db.execute(select(Patient).where(Patient.id == patient_id))).scalar_one_or_none()
    if not pt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")
    return pt

@router.get("/{patient_id}/timeline", response_model=PatientTimelineOut)
async def get_patient_timeline(
    patient_id: str,
    limit: int = Query(default=100, ge=1, le=500, description="Most recent visits to return"),
    offset: int = Query(default=0, ge=0),
    include_cancelled: bool = Query(default=False),
    current_user: AppUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    await verify_patient_access(patient_id, current_user, db, action="READ_PATIENT_TIMELINE")
    pt = (await db.execute(select(Patient).where(Patient.id == patient_id))).scalar_one_or_none()
    if not pt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")

    # Eager loading keeps this to a fixed number of queries regardless of chart size.
    visit_query = (
        select(Visit)
        .where(Visit.patient_id == patient_id)
        .options(
            selectinload(Visit.doctor), selectinload(Visit.hospital),
            selectinload(Visit.diagnoses).selectinload(Diagnosis.disease),
            selectinload(Visit.prescriptions).selectinload(Prescription.medication),
            selectinload(Visit.treatments),
            selectinload(Visit.lab_results).selectinload(LabResult.lab_test),
        )
        .order_by(Visit.visit_at.desc())
        .offset(offset)
        .limit(limit)
    )
    if not include_cancelled:
        visit_query = visit_query.where(Visit.status == "ACTIVE")
    visits = (await db.execute(visit_query)).scalars().all()

    visits_out = [
        VisitOut(
            id=v.id,
            patient_id=v.patient_id,
            doctor_id=v.doctor_id,
            doctor_name=v.doctor.display_name if v.doctor else None,
            hospital_name=v.hospital.name if v.hospital else None,
            visit_at=v.visit_at,
            visit_type=v.visit_type,
            summary_code=v.summary_code,
            diagnoses=[
                DiagnosisOut(id=d.id, disease_code=d.disease.code if d.disease else "",
                             disease_name=d.disease.name if d.disease else "", severity=d.severity,
                             status=d.status, diagnosed_at=d.diagnosed_at)
                for d in v.diagnoses
            ],
            prescriptions=[
                PrescriptionOut(id=pr.id, medication_name=pr.medication.name if pr.medication else "",
                                medication_code=pr.medication.code if pr.medication else "", dose_text=pr.dose_text,
                                frequency_text=pr.frequency_text, start_date=pr.start_date, end_date=pr.end_date)
                for pr in v.prescriptions
            ],
            treatments=[
                TreatmentOut(id=t.id, treatment_type=t.treatment_type, description_code=t.description_code,
                             start_date=t.start_date, end_date=t.end_date, outcome_status=t.outcome_status)
                for t in v.treatments
            ],
            lab_results=[
                LabResultOut(id=l.id, test_name=l.lab_test.name if l.lab_test else "",
                             test_code=l.lab_test.code if l.lab_test else "", result_value=float(l.result_value),
                             unit=l.lab_test.unit if l.lab_test else "",
                             reference_range_text=l.lab_test.reference_range_text if l.lab_test else "",
                             is_abnormal=l.is_abnormal, measured_at=l.measured_at)
                for l in sorted(v.lab_results, key=lambda item: item.measured_at, reverse=True)
            ],
        )
        for v in visits
    ]

    aes = (await db.execute(
        select(ObservedAdverseEvent).where(ObservedAdverseEvent.patient_id == patient_id)
        .options(selectinload(ObservedAdverseEvent.side_effect))
    )).scalars().all()
    aes_out = [
        AdverseEventOut(id=ae.id, side_effect_name=ae.side_effect.name if ae.side_effect else "",
                        side_effect_code=ae.side_effect.code if ae.side_effect else "", severity=ae.severity,
                        outcome=ae.outcome, evidence_quality=ae.evidence_quality, reported_at=ae.reported_at)
        for ae in aes
    ]

    return PatientTimelineOut(
        patient=pt,
        visits=visits_out,
        adverse_events=aes_out
    )


@router.post("", response_model=PatientOut)
async def create_patient(
    pt_in: PatientCreate,
    current_user: AppUser = Depends(require_role(["admin", "doctor"])),
    db: AsyncSession = Depends(get_db),
):
    """Register a new patient (clinical onboarding)."""
    existing = (await db.execute(
        select(Patient).where(Patient.display_code == pt_in.display_code)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Patient with MRN {pt_in.display_code} already exists.",
        )

    patient = Patient(
        user_id=None,
        display_code=pt_in.display_code,
        date_of_birth=pt_in.date_of_birth,
        sex=pt_in.sex,
    )
    db.add(patient)
    await db.flush()
    patient.set_name(pt_in.given_name, pt_in.family_name)

    doctor = None
    if current_user.role == "doctor":
        doctor = (await db.execute(select(Doctor).where(Doctor.user_id == current_user.id))).scalar_one_or_none()
    system = pt_in.identifier_system
    if not system and doctor:
        hospital = await db.get(Hospital, doctor.hospital_id)
        system = hospital.facility_code if hospital else None
    if system:
        clash = (await db.execute(
            select(PatientIdentifier.id).where(PatientIdentifier.system == system, PatientIdentifier.value == pt_in.display_code)
        )).scalar_one_or_none()
        if clash:
            await db.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That MRN is already registered for this authority.")
        db.add(PatientIdentifier(patient_id=patient.id, system=system, value=pt_in.display_code, identifier_type="MR"))
    if doctor:
        # The onboarding clinician joins the care team; otherwise they could not open the chart they created.
        db.add(CareTeamAssignment(
            patient_id=patient.id, doctor_id=doctor.id, relationship_type="PRIMARY_CARE",
            source="ONBOARDING", created_by=current_user.id,
        ))

    await record_access_event(
        db, current_user.id, patient.id,
        "PATIENT_ONBOARDING", patient.id, "CREATE_PATIENT",
        commit=False,
    )
    await db.commit()
    await db.refresh(patient)
    logger.info("Patient %s onboarded by %s", patient.id, current_user.id)
    EventBus.publish(ClinicalEvent("patient.registered", patient.id, {"source": "ONBOARDING"}))
    return patient


@router.post("/{patient_id}/break-glass")
async def break_glass_emergency(
    patient_id: str,
    req: BreakGlassRequest,
    current_user: AppUser = Depends(require_role(["admin", "doctor"])),
    db: AsyncSession = Depends(get_db),
):
    """
    Emergency break-the-glass access: creates a time-boxed grant that the access check honors,
    with a mandatory justification. Every grant enters the compliance review queue
    (GET /admin/break-glass) and is announced to administrators in real time.
    """
    # Resolve patient by UUID or MRN
    patient = (await db.execute(
        select(Patient).where(Patient.id == patient_id)
    )).scalar_one_or_none()
    if not patient:
        patient = (await db.execute(
            select(Patient).where(Patient.display_code == patient_id)
        )).scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")

    now = datetime.now(timezone.utc)
    window = settings.BREAK_GLASS_WINDOW_MINUTES
    grant = EmergencyAccessGrant(
        user_id=current_user.id,
        patient_id=patient.id,
        justification=req.justification,
        granted_at=now,
        expires_at=now + timedelta(minutes=window),
        review_status="PENDING_REVIEW",
    )
    db.add(grant)
    await db.flush()
    # The justification itself stays in the database; the audit reason (also chain-anchored) is a code.
    await record_access_event(
        db, current_user.id, patient.id,
        "BREAK_GLASS_EMERGENCY", grant.id,
        "BREAK_GLASS_GRANT", "GRANTED", "EMERGENCY_ACCESS_PENDING_REVIEW",
        commit=False,
    )
    await db.commit()
    logger.warning("BREAK-GLASS: user %s opened emergency access to patient %s (grant %s).",
                   current_user.id, patient.id, grant.id)
    EventBus.publish(ClinicalEvent("break_glass.granted", patient.id, {
        "grant_id": grant.id, "user_id": current_user.id, "expires_at": grant.expires_at.isoformat(),
    }, admin_only=True))

    return {
        "status": "GRANTED",
        "grant_id": grant.id,
        "patient_id": patient.id,
        "patient_mrn": patient.display_code,
        "emergency_window_minutes": window,
        "expires_at": grant.expires_at,
        "justification_recorded": True,
        "audit_note": "This access is logged and queued for compliance review.",
    }
