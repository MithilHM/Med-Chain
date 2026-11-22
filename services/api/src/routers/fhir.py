import json
import uuid
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone, date
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from src.config import settings
from src.database import get_db
from src.models import (
    AppUser, Patient, Visit, Doctor, Hospital, Disease, Diagnosis, Medication, Prescription,
    MedicalDocument, RecordIntegrity, InboundMessage, PatientIdentifier, CareTeamAssignment,
)
from src.models.base import get_utc_now
from src.services.crypto import encrypt_text, sha256_hex
from src.services.events import ClinicalEvent, EventBus
from src.services.mongo import MongoDocumentService
from src.services.integrity import IntegrityService
from src.services.outbox import OutboxService
from src.services.patient_matching import PatientMatchError, SourceIdentifier, match_or_create_patient, normalize_sex
from src.routers.deps import (
    doctor_access_reason, get_current_user, record_access_event, require_role, verify_patient_access,
)

router = APIRouter(prefix="/fhir", tags=["HL7 FHIR R4 Interoperability Gateway"])

ICD10_SYSTEMS = {
    "http://hl7.org/fhir/sid/icd-10",
    "http://hl7.org/fhir/sid/icd-10-cm",
    "http://www.who.int/classifications/icd10",
}
SNOMED_SEVERITY = {"255604002": "Mild", "6736007": "Moderate", "24484000": "Severe", "442452003": "Critical"}
ENCOUNTER_CLASS_TO_VISIT_TYPE = {
    "AMB": "Outpatient Consultation",
    "IMP": "Inpatient Admission",
    "EMER": "Emergency Evaluation",
    "VR": "Telehealth Review",
}
VISIT_TYPE_TO_ENCOUNTER_CLASS = {v: k for k, v in ENCOUNTER_CLASS_TO_VISIT_TYPE.items()}


class BundleRejected(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def _parse_fhir_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.combine(date.fromisoformat(value[:10]), datetime.min.time())
        except ValueError:
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _first_identifier_value(resource: Dict[str, Any]) -> Optional[str]:
    for ident in resource.get("identifier", []) or []:
        if ident.get("value"):
            return str(ident["value"]).strip()
    return None


def _reference(obj: Optional[Dict[str, Any]]) -> Optional[str]:
    return (obj or {}).get("reference")


@router.get("/metadata")
async def fhir_capability_statement():
    """
    HL7 FHIR R4 CapabilityStatement declaring hospital EHR interoperability interfaces.
    """
    return {
        "resourceType": "CapabilityStatement",
        "status": "draft",
        "date": datetime.now(timezone.utc).isoformat(),
        "publisher": "MedChain project",
        "kind": "instance",
        "software": {
            "name": "MedChain prototype",
            "version": "1.1.0"
        },
        "implementation": {
            "description": "Experimental FHIR interoperability endpoints for the MedChain prototype. Validate against your integration requirements before use."
        },
        "fhirVersion": "4.0.1",
        "format": ["application/json", "application/fhir+json"],
        "rest": [
            {
                "mode": "server",
                "security": {
                    "cors": True,
                    "service": [
                        {
                            "coding": [
                                {
                                    "system": "http://terminology.hl7.org/CodeSystem/restful-security-service",
                                    "code": "OAuth",
                                    "display": "OAuth2 / JWT Enterprise Hospital Bearer"
                                }
                            ]
                        }
                    ]
                },
                "resource": [
                    {"type": "Patient", "interaction": [{"code": "read"}, {"code": "create"}]},
                    {"type": "Encounter", "interaction": [{"code": "read"}, {"code": "create"}]},
                    {"type": "Condition", "interaction": [{"code": "read"}, {"code": "create"}]},
                    {"type": "MedicationRequest", "interaction": [{"code": "read"}]},
                    {"type": "DocumentReference", "interaction": [{"code": "read"}, {"code": "create"}]},
                    {"type": "Bundle", "interaction": [{"code": "transaction"}]}
                ]
            }
        ]
    }


async def _resolve_encounter_doctor(
    db: AsyncSession, encounter: Dict[str, Any], importer_doctor: Optional[Doctor]
) -> Doctor:
    for participant in encounter.get("participant", []) or []:
        individual = participant.get("individual") or {}
        provider_id = (individual.get("identifier") or {}).get("value")
        if provider_id:
            doctor = (await db.execute(
                select(Doctor).where(Doctor.external_provider_id == str(provider_id))
            )).scalar_one_or_none()
            if doctor is None:
                raise BundleRejected(422, f"Encounter participant provider '{provider_id}' is not registered.")
            return doctor
    if importer_doctor is not None:
        return importer_doctor
    raise BundleRejected(
        422, "Encounter needs participant.individual.identifier matching a registered provider (external_provider_id)."
    )


async def _resolve_encounter_hospital(db: AsyncSession, encounter: Dict[str, Any], doctor: Doctor) -> Hospital:
    code = ((encounter.get("serviceProvider") or {}).get("identifier") or {}).get("value") or settings.INTEGRATION_DEFAULT_FACILITY
    if code:
        hospital = (await db.execute(select(Hospital).where(Hospital.facility_code == str(code)))).scalar_one_or_none()
        if hospital is None:
            raise BundleRejected(422, f"Encounter serviceProvider facility '{code}' is not registered.")
        return hospital
    hospital = await db.get(Hospital, doctor.hospital_id)
    if hospital is None:
        raise BundleRejected(422, "Could not resolve the encounter's hospital.")
    return hospital


async def _reconcile_bundle(
    db: AsyncSession, bundle: Dict[str, Any], current_user: AppUser, written_payloads: List[str],
    events: List[ClinicalEvent],
) -> Tuple[str, Dict[str, Any], List[str]]:
    entries = bundle.get("entry", [])
    stats = {
        "patients_matched": 0, "patients_created": 0, "encounters_recorded": 0, "encounters_matched": 0,
        "conditions_recorded": 0, "documents_indexed": 0, "total_resources_processed": len(entries),
    }
    warnings: List[str] = []
    ref_map: Dict[str, str] = {}
    now = datetime.now(timezone.utc)

    importer_doctor = None
    if current_user.role == "doctor":
        importer_doctor = (await db.execute(select(Doctor).where(Doctor.user_id == current_user.id))).scalar_one_or_none()

    # Pass 1: exactly one Patient, matched by assigning-authority identifier
    patient_entries = [e for e in entries if (e.get("resource") or {}).get("resourceType") == "Patient"]
    if len(patient_entries) != 1:
        raise BundleRejected(422, "A bundle must contain exactly one Patient resource; data is never attached to a default patient.")
    patient_entry = patient_entries[0]
    patient_res = patient_entry["resource"]
    identifiers = [
        SourceIdentifier(system=str(i["system"])[:150], value=str(i["value"]).strip()[:100],
                         identifier_type=(((i.get("type") or {}).get("coding") or [{}])[0].get("code") or "MR")[:20])
        for i in patient_res.get("identifier", []) or []
        if i.get("system") and i.get("value")
    ]
    birth_date = None
    if patient_res.get("birthDate"):
        try:
            birth_date = date.fromisoformat(patient_res["birthDate"])
        except ValueError:
            raise BundleRejected(422, "Patient.birthDate is not a valid FHIR date.")
    try:
        patient, created = await match_or_create_patient(
            db, identifiers, birth_date, normalize_sex(patient_res.get("gender")), allow_create=True
        )
    except PatientMatchError as exc:
        raise BundleRejected(409 if exc.code == "CONFLICT" else 422, exc.message)
    stats["patients_created" if created else "patients_matched"] += 1
    if patient.record_status == "MERGED":
        raise BundleRejected(409, "The identifier belongs to a record merged into another patient.")
    if created and patient_res.get("name"):
        name = (patient_res.get("name") or [{}])[0]
        patient.set_name(" ".join(name.get("given") or []), name.get("family"))
    for key in (patient_entry.get("fullUrl"), f"Patient/{patient_res.get('id')}" if patient_res.get("id") else None):
        if key:
            ref_map[key] = patient.id
    if importer_doctor is not None and not created:
        # A doctor may only add data to a chart they already have a relationship with.
        # (Checked without committing so the import stays all-or-nothing.)
        if await doctor_access_reason(db, importer_doctor, current_user, patient.id) is None:
            raise BundleRejected(403, "This patient is not assigned to your care; the bundle was not imported.")

    # Pass 2: Encounters, idempotent on (hospital, Encounter.identifier)
    encounter_ids: List[str] = []
    for item in entries:
        res = item.get("resource") or {}
        if res.get("resourceType") != "Encounter":
            continue
        subject = _reference(res.get("subject"))
        if subject and ref_map.get(subject) not in (None, patient.id):
            raise BundleRejected(422, "Encounter.subject references a different patient.")
        started = _parse_fhir_datetime((res.get("period") or {}).get("start"))
        if started is None:
            raise BundleRejected(422, f"Encounter {res.get('id', '')} needs period.start; encounter times are never invented.")
        doctor = await _resolve_encounter_doctor(db, res, importer_doctor)
        hospital = await _resolve_encounter_hospital(db, res, doctor)
        visit_number = _first_identifier_value(res)
        visit = None
        if visit_number:
            visit = (await db.execute(
                select(Visit).where(Visit.hospital_id == hospital.id, Visit.external_visit_number == visit_number[:64])
            )).scalar_one_or_none()
            if visit is not None and visit.patient_id != patient.id:
                raise BundleRejected(409, f"Encounter identifier {visit_number} already belongs to a different patient.")
        if visit is None:
            enc_class = ((res.get("class") or {}).get("code") or "AMB").upper()
            visit = Visit(
                patient_id=patient.id, doctor_id=doctor.id, hospital_id=hospital.id,
                visit_type=ENCOUNTER_CLASS_TO_VISIT_TYPE.get(enc_class, "Clinical Encounter"),
                summary_code=f"FHIR-ENC-{res.get('id') or uuid.uuid4().hex[:6]}"[:50],
                visit_at=started,
                discharged_at=_parse_fhir_datetime((res.get("period") or {}).get("end")),
                external_visit_number=visit_number[:64] if visit_number else None,
            )
            db.add(visit)
            await db.flush()
            stats["encounters_recorded"] += 1
            events.append(ClinicalEvent("encounter.recorded", patient.id, {"visit_id": visit.id}))
        else:
            stats["encounters_matched"] += 1
        already_on_team = (await db.execute(
            select(CareTeamAssignment.id).where(
                CareTeamAssignment.patient_id == patient.id, CareTeamAssignment.doctor_id == doctor.id
            ).limit(1)
        )).scalar_one_or_none()
        if already_on_team is None:
            db.add(CareTeamAssignment(
                patient_id=patient.id, doctor_id=doctor.id, relationship_type="ATTENDING",
                source="FHIR", created_by=current_user.id,
            ))
        encounter_ids.append(visit.id)
        for key in (item.get("fullUrl"), f"Encounter/{res.get('id')}" if res.get("id") else None):
            if key:
                ref_map[key] = visit.id

    def resolve_visit(res: Dict[str, Any], resource_label: str) -> Optional[str]:
        # Condition/Observation use `encounter`; DocumentReference uses `context.encounter` (a list).
        encounter_ref = _reference(res.get("encounter"))
        context_encounters = (res.get("context") or {}).get("encounter")
        if not encounter_ref and isinstance(context_encounters, list) and context_encounters:
            encounter_ref = _reference(context_encounters[0])
        if encounter_ref:
            if encounter_ref not in ref_map:
                raise BundleRejected(422, f"{resource_label} references encounter {encounter_ref}, which is not in the bundle.")
            return ref_map[encounter_ref]
        if len(encounter_ids) == 1:
            return encounter_ids[0]
        return None

    # Pass 3: Conditions and documents
    for item in entries:
        res = item.get("resource") or {}
        r_type = res.get("resourceType")
        if r_type == "Condition":
            visit_id = resolve_visit(res, "Condition")
            if visit_id is None:
                raise BundleRejected(422, "Condition must reference its Encounter when the bundle has zero or several encounters.")
            coding = next(
                (c for c in (res.get("code") or {}).get("coding", []) or [] if c.get("system") in ICD10_SYSTEMS and c.get("code")),
                None,
            )
            if coding is None:
                warnings.append(f"Condition {res.get('id', '')} skipped: no ICD-10 coding.")
                continue
            disease = (await db.execute(select(Disease).where(Disease.code == coding["code"]))).scalar_one_or_none()
            if not disease:
                disease = Disease(code=coding["code"][:50], name=(coding.get("display") or coding["code"])[:150],
                                  description="Imported via HL7 FHIR R4 Bundle")
                db.add(disease)
                await db.flush()
            severity_code = next(iter(((res.get("severity") or {}).get("coding") or [{}])), {}).get("code")
            severity = SNOMED_SEVERITY.get(severity_code)
            clinical_status = next(iter(((res.get("clinicalStatus") or {}).get("coding") or [{}])), {}).get("code") or "active"
            db.add(Diagnosis(
                visit_id=visit_id,
                disease_id=disease.id,
                diagnosed_at=_parse_fhir_datetime(res.get("recordedDate") or res.get("onsetDateTime")) or now,
                severity=severity or "Moderate",
                status=clinical_status.capitalize()[:50],
                notes_reference="FHIR Condition" if severity else "FHIR Condition; severity not stated",
            ))
            stats["conditions_recorded"] += 1

        elif r_type in ("DocumentReference", "Observation"):
            visit_id = resolve_visit(res, r_type)
            doc_text = "FHIR Resource Data Ingested"
            if isinstance(res.get("content"), list):
                for c in res["content"]:
                    attach = c.get("attachment", {})
                    if "data" in attach or "title" in attach:
                        doc_text = attach.get("title") or doc_text
            elif "valueString" in res:
                doc_text = res["valueString"]
            doc_id = str(uuid.uuid4())
            raw_doc = {
                "_id": doc_id, "patient_id": patient.id, "visit_id": visit_id, "document_type": f"FHIR_{r_type}",
                "title": res.get("description") or f"FHIR {r_type} Ingestion", "content": str(doc_text),
                "structured_extract": res, "created_at": now.isoformat(), "created_by": current_user.id, "version": 1,
            }
            await MongoDocumentService.insert_document(raw_doc)
            written_payloads.append(doc_id)
            commitment_hash, salt = IntegrityService.create_commitment_for_doc(raw_doc)
            med_doc = MedicalDocument(patient_id=patient.id, visit_id=visit_id, document_type=f"FHIR {r_type}",
                                      mongo_document_id=doc_id, storage_status="STORED", created_by=current_user.id)
            db.add(med_doc)
            await db.flush()
            db.add(RecordIntegrity(medical_document_id=med_doc.id, record_version=1, commitment_hash=commitment_hash,
                                   algorithm="SHA256_SALTED", salt=salt, verification_status="UNVERIFIED"))
            await OutboxService.enqueue_record_anchor(db, med_doc.id, commitment_hash, 1)
            stats["documents_indexed"] += 1
        elif r_type not in ("Patient", "Encounter", None):
            warnings.append(f"{r_type} resources are not imported yet.")

    events.append(ClinicalEvent("patient.registered" if created else "patient.updated", patient.id, {"source": "FHIR"}))
    return patient.id, stats, warnings


@router.post("/import")
async def import_fhir_bundle(
    bundle: Dict[str, Any],
    current_user: AppUser = Depends(require_role(["doctor", "admin"])),
    db: AsyncSession = Depends(get_db)
):
    """
    Ingest an HL7 FHIR R4 Bundle into the relational core and encrypted document store.

    The whole bundle is applied in one transaction (all or nothing). Re-submitting a bundle with
    the same Bundle.identifier is acknowledged without re-importing.
    """
    if bundle.get("resourceType") != "Bundle":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payload must be an HL7 FHIR R4 Bundle resource (resourceType='Bundle')."
        )
    if not bundle.get("entry"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="FHIR Bundle contains no entries to reconcile.")

    raw = json.dumps(bundle, sort_keys=True, separators=(",", ":"))
    source = f"fhir-api:{current_user.id[:8]}"
    control_id = str((bundle.get("identifier") or {}).get("value") or bundle.get("id") or f"sha256:{sha256_hex(raw)}")[:100]
    existing = (await db.execute(
        select(InboundMessage).where(InboundMessage.source_system == source, InboundMessage.message_control_id == control_id)
    )).scalar_one_or_none()
    if existing is not None and existing.status == "PROCESSED":
        return {"status": "DUPLICATE", "message": "This bundle was already imported.",
                "target_patient_id": existing.patient_id, "reconciliation_summary": {}}

    written_payloads: List[str] = []
    events: List[ClinicalEvent] = []
    try:
        target_patient_id, stats, warnings = await _reconcile_bundle(db, bundle, current_user, written_payloads, events)
        ledger = existing or InboundMessage(
            source_system=source, message_control_id=control_id, protocol="FHIR", message_type="Bundle",
            raw_sha256=sha256_hex(raw), raw_encrypted="pending",
        )
        if existing is None:
            db.add(ledger)
            await db.flush()
        ledger.raw_encrypted = encrypt_text(raw, f"inbound:{ledger.id}")
        ledger.status = "PROCESSED"
        ledger.processed_at = get_utc_now()
        ledger.patient_id = target_patient_id
        ledger.error_detail = "; ".join(warnings)[:2000] if warnings else None
        await record_access_event(
            db, current_user.id, target_patient_id, "FHIR_BUNDLE", ledger.id,
            "FHIR_IMPORT_RECONCILE", "GRANTED", "EHR_INTEROPERABILITY_IMPORT", commit=False,
        )
        await db.commit()
    except BundleRejected as exc:
        await db.rollback()
        for doc_id in written_payloads:
            await MongoDocumentService.delete_document(doc_id)
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    except Exception:
        await db.rollback()
        for doc_id in written_payloads:
            await MongoDocumentService.delete_document(doc_id)
        raise

    for event in events:
        EventBus.publish(event)
    return {
        "status": "RECONCILED",
        "message": "HL7 FHIR R4 Bundle ingested in a single transaction.",
        "target_patient_id": target_patient_id,
        "reconciliation_summary": stats,
        "warnings": warnings,
    }

@router.get("/patients/{patient_id}/export")
async def export_patient_fhir_bundle(
    patient_id: str,
    current_user: AppUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Generates an HL7 FHIR R4 Bundle (collection) for a patient (right of access / portability).
    """
    pt = (await db.execute(select(Patient).where(
        or_(Patient.id == patient_id, Patient.display_code == patient_id)
    ))).scalar_one_or_none()
    if not pt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")
    await verify_patient_access(pt.id, current_user, db, action="FHIR_EXPORT")

    effective_id = pt.id
    now_iso = datetime.now(timezone.utc).isoformat()
    identifiers = (await db.execute(select(PatientIdentifier).where(PatientIdentifier.patient_id == pt.id))).scalars().all()

    # 1. Patient Resource
    patient_res = {
        "fullUrl": f"urn:uuid:{pt.id}",
        "resource": {
            "resourceType": "Patient",
            "id": pt.id,
            "identifier": [
                {
                    "use": "usual",
                    "type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v2-0203", "code": ident.identifier_type}]},
                    "system": ident.system,
                    "value": ident.value,
                }
                for ident in identifiers
            ] or [
                {
                    "use": "usual",
                    "type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v2-0203", "code": "MR"}]},
                    "system": "urn:medchain:display-code",
                    "value": pt.display_code
                }
            ],
            "active": pt.record_status == "ACTIVE",
            "gender": "male" if pt.sex == "M" else ("female" if pt.sex == "F" else "other"),
            "birthDate": pt.date_of_birth.isoformat(),
            **({"name": [{"use": "official", "family": pt.name_parts.get("family") or None,
                          "given": [g for g in [pt.name_parts.get("given")] if g]}]} if pt.name_parts else {}),
            **({"link": [{"other": {"reference": f"Patient/{pt.merged_into_id}"}, "type": "replaced-by"}]}
               if pt.merged_into_id else {}),
        }
    }

    entries = [patient_res]

    # 2. Encounters & Diagnoses
    visits = (await db.execute(select(Visit).where(Visit.patient_id == effective_id).order_by(Visit.visit_at.desc()))).scalars().all()
    for v in visits:
        hosp = (await db.execute(select(Hospital).where(Hospital.id == v.hospital_id))).scalar_one_or_none()
        doc = (await db.execute(select(Doctor).where(Doctor.id == v.doctor_id))).scalar_one_or_none()

        encounter = {
            "resourceType": "Encounter",
            "id": v.id,
            "status": "finished" if v.discharged_at or v.visit_type != "Inpatient Admission" else "in-progress",
            "class": {
                "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
                "code": VISIT_TYPE_TO_ENCOUNTER_CLASS.get(v.visit_type, "AMB"),
                "display": v.visit_type
            },
            "subject": {"reference": f"urn:uuid:{pt.id}"},
            "participant": [
                {
                    "individual": {
                        "display": doc.display_name if doc else "Attending Physician",
                        **({"identifier": {"value": doc.external_provider_id}} if doc and doc.external_provider_id else {}),
                    }
                }
            ],
            "period": {"start": v.visit_at.isoformat(), **({"end": v.discharged_at.isoformat()} if v.discharged_at else {})},
            "serviceProvider": {
                "display": hosp.name if hosp else "Hospital",
                **({"identifier": {"value": hosp.facility_code}} if hosp and hosp.facility_code else {}),
            }
        }
        if v.external_visit_number:
            encounter["identifier"] = [{"value": v.external_visit_number}]
        entries.append({"fullUrl": f"urn:uuid:{v.id}", "resource": encounter})

        # Conditions
        diags = (await db.execute(select(Diagnosis).where(Diagnosis.visit_id == v.id))).scalars().all()
        for d in diags:
            dis = (await db.execute(select(Disease).where(Disease.id == d.disease_id))).scalar_one_or_none()
            entries.append({
                "fullUrl": f"urn:uuid:{d.id}",
                "resource": {
                    "resourceType": "Condition",
                    "id": d.id,
                    "clinicalStatus": {
                        "coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                                    "code": (d.status or "active").lower()}]
                    },
                    "verificationStatus": {
                        "coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-ver-status", "code": "confirmed"}]
                    },
                    "code": {
                        "coding": [{"system": "http://hl7.org/fhir/sid/icd-10", "code": dis.code if dis else "R69",
                                    "display": dis.name if dis else "Illness, unspecified"}],
                        "text": dis.name if dis else "Condition"
                    },
                    "subject": {"reference": f"urn:uuid:{pt.id}"},
                    "encounter": {"reference": f"urn:uuid:{v.id}"},
                    "recordedDate": d.diagnosed_at.isoformat()
                }
            })

        # Prescriptions -> MedicationRequest
        rxs = (await db.execute(select(Prescription).where(Prescription.visit_id == v.id))).scalars().all()
        for rx in rxs:
            med = (await db.execute(select(Medication).where(Medication.id == rx.medication_id))).scalar_one_or_none()
            entries.append({
                "fullUrl": f"urn:uuid:{rx.id}",
                "resource": {
                    "resourceType": "MedicationRequest",
                    "id": rx.id,
                    "status": "active" if rx.end_date is None or rx.end_date >= date.today() else "completed",
                    "intent": "order",
                    "medicationCodeableConcept": {
                        "coding": [{"system": "http://www.nlm.nih.gov/research/umls/rxnorm",
                                    "code": med.code if med else "MED-001", "display": med.name if med else "Medication"}],
                        "text": med.name if med else "Medication"
                    },
                    "subject": {"reference": f"urn:uuid:{pt.id}"},
                    "encounter": {"reference": f"urn:uuid:{v.id}"},
                    "authoredOn": rx.start_date.isoformat(),
                    "dosageInstruction": [{"text": f"{rx.dose_text} - {rx.frequency_text}"}]
                }
            })

    # 3. Clinical Documents -> DocumentReference
    docs = (await db.execute(select(MedicalDocument).where(MedicalDocument.patient_id == effective_id))).scalars().all()
    for d in docs:
        integ = (await db.execute(select(RecordIntegrity).where(RecordIntegrity.medical_document_id == d.id))).scalar_one_or_none()
        entries.append({
            "fullUrl": f"urn:uuid:{d.id}",
            "resource": {
                "resourceType": "DocumentReference",
                "id": d.id,
                "status": "current",
                "docStatus": "final",
                "type": {"coding": [{"system": "http://loinc.org", "code": "34117-2", "display": d.document_type}]},
                "subject": {"reference": f"urn:uuid:{pt.id}"},
                "date": d.created_at.isoformat(),
                "securityLabel": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v3-Confidentiality",
                                               "code": "R", "display": "Restricted Healthcare Record"}]}],
                "content": [{"attachment": {
                    "contentType": "application/json",
                    "title": f"Integrity commitment (salted SHA-256, version {integ.record_version if integ else 1})",
                    **({"hash": integ.commitment_hash} if integ else {}),
                }}]
            }
        })

    await record_access_event(
        db, current_user.id, effective_id, "FHIR_BUNDLE", effective_id,
        "FHIR_EXPORT", "GRANTED", "RIGHT_OF_ACCESS_PORTABILITY",
    )

    return {
        "resourceType": "Bundle",
        "type": "collection",
        "timestamp": now_iso,
        "total": len(entries),
        "entry": entries
    }
