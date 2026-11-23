import logging
from typing import List, Optional
from datetime import date, datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.services import accounts
from src.services.crypto import name_blind_index
from src.config import settings
from src.database import get_db
from src.models import (
    AppUser, Patient, Visit, Diagnosis, Disease, Prescription, Medication,
    Treatment, LabResult, LabTest, ObservedAdverseEvent, SideEffect, Doctor, Hospital,
    AccessEvent, CareTeamAssignment, EmergencyAccessGrant, PatientIdentifier, PatientAllergy,
)
from src.schemas.clinical import PatientOut, PatientTimelineOut, VisitOut, DiagnosisOut, PrescriptionOut, LabResultOut, TreatmentOut, AdverseEventOut
from src.routers.deps import (
    doctor_accessible_patient_ids, get_current_user, require_role, verify_patient_access, record_access_event,
)
from src.services.events import ClinicalEvent, EventBus

router = APIRouter(prefix="/patients", tags=["Patients"])
logger = logging.getLogger("medchain.patients")


class PatientCreate(BaseModel):
    display_code: str = Field(..., min_length=1, max_length=50, description="MRN issued by the hospital")
    date_of_birth: date
    sex: str = Field(..., pattern="^[MFO]$")
    given_name: Optional[str] = Field(default=None, max_length=100)
    family_name: Optional[str] = Field(default=None, max_length=100)
    hospital_id: Optional[str] = None  # registering hospital; its facility code is the MRN authority
    # Explicit assigning authority, if it differs from the hospital facility code.
    identifier_system: Optional[str] = Field(default=None, max_length=150)
    primary_doctor_id: Optional[str] = None
    issue_portal_invitation: bool = False

    @field_validator("date_of_birth")
    @classmethod
    def _not_in_future(cls, value: date) -> date:
        if value > date.today() or value.year < 1900:
            raise ValueError("Date of birth must be a real past date.")
        return value


class PatientCreatedOut(PatientOut):
    portal_activation_code: Optional[str] = None
    portal_activation_expires_at: Optional[datetime] = None


class PatientUpdate(BaseModel):
    given_name: Optional[str] = Field(default=None, max_length=100)
    family_name: Optional[str] = Field(default=None, max_length=100)
    date_of_birth: Optional[date] = None
    sex: Optional[str] = Field(default=None, pattern="^[MFO]$")


class CareTeamCreate(BaseModel):
    doctor_id: str
    relationship_type: str = Field(default="ATTENDING", pattern="^(ATTENDING|CONSULTING|REFERRING|ADMITTING|PRIMARY_CARE)$")
    days: Optional[int] = Field(default=None, ge=1, le=3650, description="Leave empty for an open-ended assignment")


class AllergyCreate(BaseModel):
    substance: str = Field(..., min_length=2, max_length=150)
    reaction: Optional[str] = Field(default=None, max_length=200)
    severity: str = Field(default="UNKNOWN", pattern="^(MILD|MODERATE|SEVERE|UNKNOWN)$")


class AllergyStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(ACTIVE|INACTIVE|ENTERED_IN_ERROR)$")


class BreakGlassRequest(BaseModel):
    justification: str = Field(..., min_length=10, max_length=2000)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _allergy_out(a: PatientAllergy) -> dict:
    return {"id": a.id, "substance": a.substance, "reaction": a.reaction, "severity": a.severity,
            "status": a.status, "recorded_at": a.recorded_at, "recorded_by": a.recorded_by}

@router.get("", response_model=List[PatientOut])
async def list_patients(
    family_name: Optional[str] = Query(default=None, max_length=100, description="Exact family-name search"),
    q: Optional[str] = Query(default=None, max_length=100, description="MRN (partial) or exact family name"),
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
    if q and q.strip():
        term = q.strip()
        conditions = [Patient.display_code.ilike(f"%{term}%")]
        if name_blind_index(term):
            conditions.append(Patient.family_name_index == name_blind_index(term))
        patient_query = patient_query.where(or_(*conditions))
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
            hospital_id=v.hospital_id,
            hospital_name=v.hospital.name if v.hospital else None,
            status=v.status,
            discharged_at=v.discharged_at,
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

    allergies = (await db.execute(
        select(PatientAllergy).where(PatientAllergy.patient_id == patient_id, PatientAllergy.status == "ACTIVE")
        .order_by(PatientAllergy.recorded_at.desc())
    )).scalars().all()
    now = datetime.now(timezone.utc)
    care_rows = (await db.execute(
        select(CareTeamAssignment, Doctor).join(Doctor, Doctor.id == CareTeamAssignment.doctor_id)
        .where(CareTeamAssignment.patient_id == patient_id,
               or_(CareTeamAssignment.active_until.is_(None), CareTeamAssignment.active_until > now))
    )).all()
    facilities = sorted({v.hospital.name for v in visits if v.hospital})

    return PatientTimelineOut(
        patient=pt,
        visits=visits_out,
        adverse_events=aes_out,
        allergies=[_allergy_out(a) for a in allergies],
        care_team=[{"id": a.id, "doctor_id": d.id, "doctor_name": d.display_name,
                    "relationship_type": a.relationship_type} for a, d in care_rows],
        facilities=facilities,
    )


@router.post("", response_model=PatientCreatedOut)
async def create_patient(
    pt_in: PatientCreate,
    current_user: AppUser = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db),
):
    """Register a patient (administrators / registration staff only).

    Records the MRN under the hospital's assigning authority, optionally places a primary doctor on
    the care team (so the patient appears in that doctor's list), and optionally issues a one-time
    patient-portal activation code.
    """
    hospital = await db.get(Hospital, pt_in.hospital_id) if pt_in.hospital_id else None
    if pt_in.hospital_id and hospital is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hospital not found.")
    system = pt_in.identifier_system or (hospital.facility_code if hospital else None)
    if not system:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Choose the registering hospital (its facility code issues the MRN).")
    allowed = settings.allowed_facility_codes
    if allowed and system not in allowed:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="This installation does not register patients for that facility.")
    if (await db.execute(select(Patient.id).where(Patient.display_code == pt_in.display_code))).scalar_one_or_none() or \
            (await db.execute(select(PatientIdentifier.id).where(
                PatientIdentifier.system == system, PatientIdentifier.value == pt_in.display_code))).scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"MRN {pt_in.display_code} is already registered.")
    doctor = None
    if pt_in.primary_doctor_id:
        doctor = await db.get(Doctor, pt_in.primary_doctor_id)
        if doctor is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Primary doctor not found.")

    patient = Patient(user_id=None, display_code=pt_in.display_code.strip(), date_of_birth=pt_in.date_of_birth, sex=pt_in.sex)
    db.add(patient)
    await db.flush()
    patient.set_name(pt_in.given_name, pt_in.family_name)
    db.add(PatientIdentifier(patient_id=patient.id, system=system, value=patient.display_code, identifier_type="MR"))
    if doctor:
        db.add(CareTeamAssignment(patient_id=patient.id, doctor_id=doctor.id, relationship_type="PRIMARY_CARE",
                                  source="ONBOARDING", created_by=current_user.id))
    code, expires = None, None
    if pt_in.issue_portal_invitation:
        invitation, code = await accounts.issue_invitation(db, "PATIENT_PORTAL", created_by=current_user.id,
                                                           patient_id=patient.id)
        expires = invitation.expires_at
    await record_access_event(db, current_user.id, patient.id, "PATIENT_ONBOARDING", patient.id, "CREATE_PATIENT",
                              commit=False)
    await db.commit()
    await db.refresh(patient)
    logger.info("Patient %s registered by %s", patient.id, current_user.id)
    EventBus.publish(ClinicalEvent("patient.registered", patient.id, {"source": "REGISTRATION"}))
    return PatientCreatedOut(**PatientOut.model_validate(patient).model_dump(),
                             portal_activation_code=code, portal_activation_expires_at=expires)


@router.patch("/{patient_id}", response_model=PatientOut)
async def update_patient_demographics(
    patient_id: str,
    body: PatientUpdate,
    current_user: AppUser = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db),
):
    await verify_patient_access(patient_id, current_user, db, action="UPDATE_PATIENT_DEMOGRAPHICS")
    patient = await db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")
    changed = []
    if body.date_of_birth and body.date_of_birth != patient.date_of_birth:
        patient.date_of_birth = body.date_of_birth
        changed.append("DOB")
    if body.sex and body.sex != patient.sex:
        patient.sex = body.sex
        changed.append("SEX")
    if body.given_name is not None or body.family_name is not None:
        current = patient.name_parts or {}
        patient.set_name(body.given_name if body.given_name is not None else current.get("given"),
                         body.family_name if body.family_name is not None else current.get("family"))
        changed.append("NAME")
    await record_access_event(db, current_user.id, patient.id, "PATIENT_RECORD", patient.id, "UPDATE_DEMOGRAPHICS",
                              "GRANTED", "CHANGED_" + "_".join(changed or ["NOTHING"]), commit=False)
    await db.commit()
    await db.refresh(patient)
    EventBus.publish(ClinicalEvent("patient.updated", patient.id, {"changed_fields": changed}))
    return patient


@router.post("/{patient_id}/portal-invitation")
async def issue_portal_invitation(
    patient_id: str,
    current_user: AppUser = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db),
):
    """Issue (or re-issue) the one-time code a patient uses to create their portal account."""
    patient = await db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")
    if patient.record_status != "ACTIVE":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Merged records cannot receive portal access.")
    if patient.user_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This patient already has a portal account.")
    invitation, code = await accounts.issue_invitation(db, "PATIENT_PORTAL", created_by=current_user.id, patient_id=patient.id)
    await record_access_event(db, current_user.id, patient.id, "PATIENT_PORTAL", patient.id, "ISSUE_PORTAL_CODE",
                              "GRANTED", "REGISTRATION_DESK", commit=False)
    await db.commit()
    return {"portal_activation_code": code, "expires_at": invitation.expires_at, "signup_path": "/signup",
            "note": "Give the code to the patient in person or by a verified channel; it is shown only once."}


@router.get("/{patient_id}/care-team")
async def get_care_team(
    patient_id: str,
    current_user: AppUser = Depends(require_role(["doctor", "admin"])),
    db: AsyncSession = Depends(get_db),
):
    await verify_patient_access(patient_id, current_user, db, action="READ_CARE_TEAM")
    now = datetime.now(timezone.utc)
    rows = (await db.execute(
        select(CareTeamAssignment, Doctor).join(Doctor, Doctor.id == CareTeamAssignment.doctor_id)
        .where(CareTeamAssignment.patient_id == patient_id)
        .order_by(CareTeamAssignment.active_from.desc())
    )).all()
    return [
        {"id": a.id, "doctor_id": d.id, "doctor_name": d.display_name, "specialty": d.specialty,
         "relationship_type": a.relationship_type, "source": a.source, "active_from": a.active_from,
         "active_until": a.active_until,
         "active": a.active_until is None or _aware(a.active_until) > now}
        for a, d in rows
    ]


@router.post("/{patient_id}/care-team")
async def add_care_team_member(
    patient_id: str,
    body: CareTeamCreate,
    current_user: AppUser = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db),
):
    await verify_patient_access(patient_id, current_user, db, action="UPDATE_CARE_TEAM")
    doctor = await db.get(Doctor, body.doctor_id)
    if doctor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found.")
    now = datetime.now(timezone.utc)
    existing = (await db.execute(select(CareTeamAssignment).where(
        CareTeamAssignment.patient_id == patient_id, CareTeamAssignment.doctor_id == doctor.id,
        CareTeamAssignment.relationship_type == body.relationship_type,
        or_(CareTeamAssignment.active_until.is_(None), CareTeamAssignment.active_until > now),
    ))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That doctor already has this role for the patient.")
    assignment = CareTeamAssignment(patient_id=patient_id, doctor_id=doctor.id, relationship_type=body.relationship_type,
                                    source="MANUAL", created_by=current_user.id,
                                    active_until=(now + timedelta(days=body.days)) if body.days else None)
    db.add(assignment)
    await db.flush()
    await record_access_event(db, current_user.id, patient_id, "CARE_TEAM", assignment.id, "ASSIGN_CARE_TEAM",
                              "GRANTED", body.relationship_type, commit=False)
    await db.commit()
    return {"id": assignment.id, "status": "ASSIGNED"}


@router.delete("/{patient_id}/care-team/{assignment_id}")
async def end_care_team_assignment(
    patient_id: str,
    assignment_id: str,
    current_user: AppUser = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db),
):
    assignment = await db.get(CareTeamAssignment, assignment_id)
    if assignment is None or assignment.patient_id != patient_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found.")
    now = datetime.now(timezone.utc)
    assignment.active_until = max(now, _aware(assignment.active_from) + timedelta(microseconds=1))
    await record_access_event(db, current_user.id, patient_id, "CARE_TEAM", assignment.id, "END_CARE_TEAM",
                              "GRANTED", "ADMIN_ACTION", commit=False)
    await db.commit()
    return {"id": assignment.id, "status": "ENDED"}


@router.get("/{patient_id}/allergies")
async def list_allergies(patient_id: str, current_user: AppUser = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    await verify_patient_access(patient_id, current_user, db, action="READ_ALLERGIES")
    rows = (await db.execute(select(PatientAllergy).where(PatientAllergy.patient_id == patient_id)
                             .order_by(PatientAllergy.recorded_at.desc()))).scalars().all()
    return [_allergy_out(a) for a in rows]


@router.post("/{patient_id}/allergies")
async def add_allergy(patient_id: str, body: AllergyCreate,
                      current_user: AppUser = Depends(require_role(["doctor", "admin"])),
                      db: AsyncSession = Depends(get_db)):
    await verify_patient_access(patient_id, current_user, db, action="RECORD_ALLERGY")
    allergy = PatientAllergy(patient_id=patient_id, substance=body.substance.strip(), reaction=body.reaction,
                             severity=body.severity, recorded_by=current_user.id)
    db.add(allergy)
    await db.flush()
    await record_access_event(db, current_user.id, patient_id, "ALLERGY", allergy.id, "RECORD_ALLERGY", "GRANTED",
                              body.severity, commit=False)
    await db.commit()
    EventBus.publish(ClinicalEvent("allergy.recorded", patient_id, {"allergy_id": allergy.id, "severity": body.severity}))
    return _allergy_out(allergy)


@router.patch("/{patient_id}/allergies/{allergy_id}")
async def update_allergy_status(patient_id: str, allergy_id: str, body: AllergyStatusUpdate,
                                current_user: AppUser = Depends(require_role(["doctor", "admin"])),
                                db: AsyncSession = Depends(get_db)):
    await verify_patient_access(patient_id, current_user, db, action="UPDATE_ALLERGY")
    allergy = await db.get(PatientAllergy, allergy_id)
    if allergy is None or allergy.patient_id != patient_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Allergy not found.")
    allergy.status = body.status
    await record_access_event(db, current_user.id, patient_id, "ALLERGY", allergy.id, "UPDATE_ALLERGY", "GRANTED",
                              body.status, commit=False)
    await db.commit()
    return _allergy_out(allergy)


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
