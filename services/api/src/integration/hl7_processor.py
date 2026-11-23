"""HL7 v2 message processing: ledger, idempotency, patient matching, and clinical upserts.

Supported events
- ADT^A01 (admit), ADT^A04 (register): match or create patient, upsert visit, assign attending doctor.
- ADT^A02 (transfer): update location and attending doctor.
- ADT^A03 (discharge): set the discharge time; admission care-team access ends after a grace period.
- ADT^A08 (update patient information): update demographics and name of an identifier-matched patient.
- ADT^A11 (cancel admit): cancel a visit entered in error (refused if clinical data is attached).
- ADT^A13 (cancel discharge): reopen the visit and its care-team access.
- ADT^A40 (merge): record a merge request for administrator approval; never merged automatically.
- ORU^R01 (observation result): upsert numeric lab results against an identified visit.

ACK semantics (what the interface engine should do)
- AA: processed, or durably stored and queued for manual review (do not resend).
- AR: rejected: unparseable, unsupported, or invalid content (fix and resend).
- AE: transient internal error, e.g. database unavailable (the engine should retry).

Every message is stored once in `inbound_message` keyed by (source system, MSH-10). Re-sent
messages are acknowledged without reprocessing. The raw payload is AES-GCM encrypted and an
HMAC commitment of it is anchored on-chain as provenance for the ingested data.
"""
import hashlib
import hmac
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import List, Optional, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src import database
from src.config import settings
from src.integration.hl7v2 import HL7Message, HL7ParseError, build_ack, parse_hl7_date, parse_hl7_datetime, parse_message
from src.models import (
    CareTeamAssignment, Diagnosis, Doctor, Hospital, InboundMessage, LabResult, LabTest, MedicalDocument,
    Patient, PatientMergeRequest, Visit,
)
from src.models.base import get_utc_now
from src.services.crypto import decrypt_text, encrypt_text, sha256_hex
from src.services.events import ClinicalEvent, EventBus
from src.services.outbox import OutboxService
from src.services.patient_matching import (
    PatientMatchError, SourceIdentifier, find_patient, match_or_create_patient, normalize_sex,
)

logger = logging.getLogger("medchain.integration.hl7")

SUPPORTED_TYPES = {
    "ADT^A01", "ADT^A02", "ADT^A03", "ADT^A04", "ADT^A08", "ADT^A11", "ADT^A13", "ADT^A40", "ORU^R01",
}
PATIENT_CLASS_TO_VISIT_TYPE = {
    "I": "Inpatient Admission", "O": "Outpatient Consultation", "E": "Emergency Evaluation",
    "P": "Pre-admission", "R": "Recurring Patient", "B": "Obstetrics",
}
ABNORMAL_FLAGS = {"H", "L", "HH", "LL", "A", "AA", ">", "<", "HU", "LU"}
CRITICAL_FLAGS = {"HH", "LL", "AA"}


class ReviewRequired(Exception):
    """Content is valid HL7 but cannot be applied safely without a human decision."""


class InvalidMessage(Exception):
    """Content violates the interface contract; the sender must fix and resend."""


class MergeQueued(Exception):
    """A merge request was stored (and must be committed); the message waits for approval."""


@dataclass
class ProcessingOutcome:
    ack_code: str
    status: str
    detail: str
    message_id: Optional[str] = None
    patient_id: Optional[str] = None
    ack: str = ""
    warnings: List[str] = field(default_factory=list)
    duplicate: bool = False


def _provenance_commitment(raw: str) -> str:
    digest = hmac.new(settings.CHAIN_PSEUDONYM_KEY.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256).hexdigest()
    return "0x" + digest


def _identifiers(message: HL7Message, pid, default_system: str) -> List[SourceIdentifier]:
    identifiers = []
    for rep in range(message.repetitions(pid, 3)):
        value = message.value(pid, 3, 1, rep)
        if not value:
            continue
        authority = message.value(pid, 3, 4, rep) or message.value(pid, 3, 4, rep, 2)
        id_type = message.value(pid, 3, 5, rep) or "MR"
        system = authority or default_system
        if system:
            identifiers.append(SourceIdentifier(system=system[:150], value=value[:100], identifier_type=id_type[:20]))
    return identifiers


async def _resolve_hospital(db: AsyncSession, message: HL7Message) -> Hospital:
    pv1 = message.first("PV1")
    candidates = [message.value(pv1, 3, 4), message.sending_facility, settings.INTEGRATION_DEFAULT_FACILITY]
    allowed = settings.allowed_facility_codes
    for code in candidates:
        if code:
            if allowed and code not in allowed:
                # Single-hospital boundary: this installation never stores another facility's data.
                raise InvalidMessage(f"Facility '{code}' is not served by this installation.")
            hospital = (await db.execute(select(Hospital).where(Hospital.facility_code == code))).scalar_one_or_none()
            if hospital:
                return hospital
    raise ReviewRequired(
        f"Unknown facility '{message.sending_facility}'. Register it as a hospital facility_code, then reprocess."
    )


async def _resolve_doctor(db: AsyncSession, message: HL7Message, field_no: int = 7) -> Optional[Doctor]:
    pv1 = message.first("PV1")
    provider_id = message.value(pv1, field_no, 1)
    if not provider_id:
        return None
    doctor = (await db.execute(select(Doctor).where(Doctor.external_provider_id == provider_id))).scalar_one_or_none()
    if doctor is None:
        raise ReviewRequired(
            f"Attending provider '{provider_id}' is not registered. Set the doctor's external_provider_id, then reprocess."
        )
    return doctor


async def _ensure_care_team(db: AsyncSession, patient_id: str, doctor_id: str, relationship_type: str = "ATTENDING") -> None:
    now = datetime.now(timezone.utc)
    existing = (await db.execute(
        select(CareTeamAssignment.id).where(
            CareTeamAssignment.patient_id == patient_id,
            CareTeamAssignment.doctor_id == doctor_id,
            CareTeamAssignment.relationship_type == relationship_type,
            or_(CareTeamAssignment.active_until.is_(None), CareTeamAssignment.active_until > now),
        )
    )).scalar_one_or_none()
    if existing is None:
        db.add(CareTeamAssignment(
            patient_id=patient_id, doctor_id=doctor_id, relationship_type=relationship_type, source="HL7_ADT",
        ))


def _event_time(message: HL7Message, *candidates: str) -> datetime:
    for candidate in candidates:
        parsed = parse_hl7_datetime(candidate)
        if parsed:
            return parsed
    parsed = parse_hl7_datetime(message.value(message.first("EVN"), 2)) or parse_hl7_datetime(message.value(message.msh, 7))
    if parsed is None:
        raise InvalidMessage("No usable event time in PV1, EVN-2, or MSH-7.")
    return parsed


async def _match_patient(db: AsyncSession, message: HL7Message, hospital: Hospital, allow_create: bool,
                         enforce_demographics: bool = True) -> Tuple[Patient, bool]:
    pid = message.first("PID")
    if pid is None:
        raise InvalidMessage("PID segment is required.")
    identifiers = _identifiers(message, pid, hospital.facility_code or "")
    dob_raw = message.value(pid, 7)
    dob = parse_hl7_date(dob_raw) if dob_raw else None
    if dob_raw and dob is None:
        raise InvalidMessage("PID-7 date of birth is not a valid HL7 date.")
    try:
        patient, created = await match_or_create_patient(
            db, identifiers, dob, normalize_sex(message.value(pid, 8)), allow_create, enforce_demographics
        )
    except PatientMatchError as exc:
        if exc.code in ("NO_IDENTIFIER", "INSUFFICIENT_DEMOGRAPHICS"):
            raise InvalidMessage(exc.message)
        raise ReviewRequired(exc.message)
    if patient.record_status == "MERGED":
        raise ReviewRequired("Identifier belongs to a record that was merged into another patient.")
    if created:
        given, family = _pid_name(message, pid)
        if given or family:
            patient.set_name(given, family)
    return patient, created


def _pid_name(message: HL7Message, pid) -> Tuple[str, str]:
    """PID-5 XPN: family^given (first repetition)."""
    return message.value(pid, 5, 2), message.value(pid, 5, 1)


async def _end_admission_care_team(db: AsyncSession, visit: Visit, until: datetime) -> None:
    """End HL7-created attending access for this visit's doctor at `until` (kept strictly after its start)."""
    assignments = (await db.execute(
        select(CareTeamAssignment).where(
            CareTeamAssignment.patient_id == visit.patient_id,
            CareTeamAssignment.doctor_id == visit.doctor_id,
            CareTeamAssignment.source == "HL7_ADT",
        )
    )).scalars().all()
    for assignment in assignments:
        start = assignment.active_from if assignment.active_from.tzinfo else assignment.active_from.replace(tzinfo=timezone.utc)
        assignment.active_until = max(until, start + timedelta(microseconds=1))


async def _find_visit(db: AsyncSession, message: HL7Message, hospital: Hospital, patient: Patient) -> Optional[Visit]:
    visit_number = message.value(message.first("PV1"), 19, 1)
    if not visit_number:
        return None
    visit = (await db.execute(
        select(Visit).where(Visit.hospital_id == hospital.id, Visit.external_visit_number == visit_number)
    )).scalar_one_or_none()
    if visit is not None and visit.patient_id != patient.id:
        raise ReviewRequired(f"Visit number {visit_number} belongs to a different patient.")
    return visit


async def _handle_admit_or_register(db: AsyncSession, message: HL7Message, events: List[ClinicalEvent]) -> Patient:
    hospital = await _resolve_hospital(db, message)
    patient, created = await _match_patient(db, message, hospital, allow_create=True)
    pv1 = message.first("PV1")
    visit_number = message.value(pv1, 19, 1)
    if visit_number:
        doctor = await _resolve_doctor(db, message)
        visit = await _find_visit(db, message, hospital, patient)
        visit_at = _event_time(message, message.value(pv1, 44))
        if visit is None:
            if doctor is None:
                raise ReviewRequired("PV1-7 attending doctor is required to create a visit.")
            visit = Visit(
                patient_id=patient.id, doctor_id=doctor.id, hospital_id=hospital.id, visit_at=visit_at,
                visit_type=PATIENT_CLASS_TO_VISIT_TYPE.get(message.value(pv1, 2).upper(), "Clinical Encounter"),
                summary_code=message.value(pv1, 3, 1)[:50] or None, external_visit_number=visit_number[:64],
            )
            db.add(visit)
        elif doctor is not None:
            visit.doctor_id = doctor.id
        if doctor is not None:
            await _ensure_care_team(db, patient.id, doctor.id)
        await db.flush()
        events.append(ClinicalEvent("encounter.admitted", patient.id, {
            "visit_id": visit.id, "hospital": hospital.facility_code, "visit_type": visit.visit_type,
        }))
    events.append(ClinicalEvent("patient.registered" if created else "patient.updated", patient.id, {}))
    return patient


async def _handle_update(db: AsyncSession, message: HL7Message, events: List[ClinicalEvent]) -> Patient:
    hospital = await _resolve_hospital(db, message)
    # A08 is the sanctioned way to correct demographics, so a DOB/sex difference is applied, not rejected.
    patient, _ = await _match_patient(db, message, hospital, allow_create=False, enforce_demographics=False)
    pid = message.first("PID")
    new_dob = parse_hl7_date(message.value(pid, 7)) if message.value(pid, 7) else None
    new_sex = normalize_sex(message.value(pid, 8))
    changed = []
    if new_dob and new_dob != patient.date_of_birth:
        patient.date_of_birth = new_dob
        changed.append("date_of_birth")
    if new_sex and new_sex != patient.sex:
        patient.sex = new_sex
        changed.append("sex")
    given, family = _pid_name(message, pid)
    if (given or family) and patient.name_parts != {"given": given, "family": family}:
        patient.set_name(given, family)
        changed.append("name")
    events.append(ClinicalEvent("patient.updated", patient.id, {"changed_fields": changed}))
    return patient


async def _require_visit(db: AsyncSession, message: HL7Message, hospital: Hospital, patient: Patient, event: str) -> Visit:
    visit = await _find_visit(db, message, hospital, patient)
    if visit is None:
        raise ReviewRequired(f"{event} references an unknown or missing PV1-19 visit number.")
    return visit


async def _handle_discharge(db: AsyncSession, message: HL7Message, events: List[ClinicalEvent]) -> Patient:
    hospital = await _resolve_hospital(db, message)
    patient, _ = await _match_patient(db, message, hospital, allow_create=False)
    visit = await _require_visit(db, message, hospital, patient, "Discharge")
    visit.discharged_at = _event_time(message, message.value(message.first("PV1"), 45))
    discharged = visit.discharged_at if visit.discharged_at.tzinfo else visit.discharged_at.replace(tzinfo=timezone.utc)
    # Admission-based care-team access ends a fixed period after discharge (least privilege).
    await _end_admission_care_team(db, visit, discharged + timedelta(days=settings.CARE_TEAM_POST_DISCHARGE_DAYS))
    events.append(ClinicalEvent("encounter.discharged", patient.id, {"visit_id": visit.id}))
    return patient


async def _handle_transfer(db: AsyncSession, message: HL7Message, events: List[ClinicalEvent]) -> Patient:
    """A02: new location and, if PV1-7 changed, a new attending doctor on the care team."""
    hospital = await _resolve_hospital(db, message)
    patient, _ = await _match_patient(db, message, hospital, allow_create=False)
    visit = await _require_visit(db, message, hospital, patient, "Transfer")
    pv1 = message.first("PV1")
    if message.value(pv1, 3, 1):
        visit.summary_code = message.value(pv1, 3, 1)[:50]
    doctor = await _resolve_doctor(db, message)
    if doctor is not None and doctor.id != visit.doctor_id:
        visit.doctor_id = doctor.id
        await _ensure_care_team(db, patient.id, doctor.id)
    events.append(ClinicalEvent("encounter.transferred", patient.id, {"visit_id": visit.id, "location": visit.summary_code}))
    return patient


async def _handle_cancel_admit(db: AsyncSession, message: HL7Message, events: List[ClinicalEvent]) -> Patient:
    """A11: cancel an admission entered in error. Refused if clinical data is already attached."""
    hospital = await _resolve_hospital(db, message)
    patient, _ = await _match_patient(db, message, hospital, allow_create=False)
    visit = await _require_visit(db, message, hospital, patient, "Cancel admit")
    attached = sum([
        (await db.execute(select(func.count(LabResult.id)).where(LabResult.visit_id == visit.id))).scalar() or 0,
        (await db.execute(select(func.count(Diagnosis.id)).where(Diagnosis.visit_id == visit.id))).scalar() or 0,
        (await db.execute(select(func.count(MedicalDocument.id)).where(MedicalDocument.visit_id == visit.id))).scalar() or 0,
    ])
    if attached:
        raise ReviewRequired("Cancel admit refused: results, diagnoses, or documents are already attached to this visit.")
    visit.status = "CANCELLED"
    await _end_admission_care_team(db, visit, datetime.now(timezone.utc))
    events.append(ClinicalEvent("encounter.cancelled", patient.id, {"visit_id": visit.id}))
    return patient


async def _handle_cancel_discharge(db: AsyncSession, message: HL7Message, events: List[ClinicalEvent]) -> Patient:
    """A13: the patient was not actually discharged; reopen the visit and its care-team access."""
    hospital = await _resolve_hospital(db, message)
    patient, _ = await _match_patient(db, message, hospital, allow_create=False)
    visit = await _require_visit(db, message, hospital, patient, "Cancel discharge")
    visit.discharged_at = None
    for assignment in (await db.execute(
        select(CareTeamAssignment).where(
            CareTeamAssignment.patient_id == patient.id, CareTeamAssignment.doctor_id == visit.doctor_id,
            CareTeamAssignment.source == "HL7_ADT",
        )
    )).scalars().all():
        assignment.active_until = None
    events.append(ClinicalEvent("encounter.discharge_cancelled", patient.id, {"visit_id": visit.id}))
    return patient


async def _handle_merge(db: AsyncSession, message: HL7Message, inbound_id: str) -> Patient:
    """A40: record a merge request. Records are never merged automatically; an administrator approves."""
    hospital = await _resolve_hospital(db, message)
    surviving, _ = await _match_patient(db, message, hospital, allow_create=False, enforce_demographics=False)
    mrg = message.first("MRG")
    prior = []
    for rep in range(message.repetitions(mrg, 1)):
        value = message.value(mrg, 1, 1, rep)
        if value:
            prior.append(SourceIdentifier(system=(message.value(mrg, 1, 4, rep) or hospital.facility_code or "")[:150],
                                          value=value[:100]))
    if not prior:
        raise InvalidMessage("MRG-1 prior patient identifier is required for A40.")
    try:
        retiring = await find_patient(db, prior)
    except PatientMatchError as exc:
        raise ReviewRequired(exc.message)
    if retiring is None:
        raise ReviewRequired("A40 prior identifier does not match a registered patient; nothing to merge.")
    if retiring.id == surviving.id:
        return surviving  # already the same record
    pending = (await db.execute(
        select(PatientMergeRequest.id).where(
            PatientMergeRequest.surviving_patient_id == surviving.id,
            PatientMergeRequest.retiring_patient_id == retiring.id,
            PatientMergeRequest.status == "PENDING",
        )
    )).scalar_one_or_none()
    if pending is None:
        db.add(PatientMergeRequest(surviving_patient_id=surviving.id, retiring_patient_id=retiring.id,
                                   source_message_id=inbound_id, reason="ADT^A40 merge from the hospital ADT system"))
        await db.flush()
    raise MergeQueued("Merge request recorded; an administrator must approve it before records are combined.")


async def _handle_results(db: AsyncSession, message: HL7Message, inbound_id: str,
                          events: List[ClinicalEvent], warnings: List[str]) -> Patient:
    hospital = await _resolve_hospital(db, message)
    patient, _ = await _match_patient(db, message, hospital, allow_create=False)
    visit = await _find_visit(db, message, hospital, patient)
    if visit is None:
        raise ReviewRequired("Results must reference a known visit (PV1-19) so they attach to the correct encounter.")
    if visit.status == "CANCELLED":
        raise ReviewRequired("Results reference a visit that was cancelled (A11).")

    obr = message.first("OBR")
    applied = 0
    for obx in message.segments_named("OBX"):
        set_id = message.value(obx, 1) or "?"
        value_type = message.value(obx, 2).upper()
        status = message.value(obx, 11).upper() or "F"
        if status not in ("F", "C", "P"):
            warnings.append(f"OBX-{set_id}: result status '{status}' skipped.")
            continue
        if value_type not in ("NM", "SN"):
            warnings.append(f"OBX-{set_id}: value type '{value_type}' is not numeric; stored narrative results arrive as documents.")
            continue
        raw_value = message.value(obx, 5, 2) if value_type == "SN" else message.value(obx, 5)
        try:
            numeric = Decimal(raw_value)
        except (InvalidOperation, TypeError):
            raise InvalidMessage(f"OBX-{set_id}: OBX-5 value '{raw_value[:20]}' is not numeric.")

        code = message.value(obx, 3, 1)
        if not code:
            raise InvalidMessage(f"OBX-{set_id}: OBX-3 observation code is required.")
        lab_test = (await db.execute(select(LabTest).where(LabTest.code == code[:50]))).scalar_one_or_none()
        if lab_test is None:
            lab_test = LabTest(
                code=code[:50],
                name=(message.value(obx, 3, 2) or code)[:150],
                unit=(message.value(obx, 6, 1) or "unitless")[:50],
                reference_range_text=(message.value(obx, 7) or "not supplied")[:100],
            )
            db.add(lab_test)
            await db.flush()

        flag = message.value(obx, 8).upper()
        measured_at = _event_time(message, message.value(obx, 14), message.value(obr, 7))
        existing = (await db.execute(
            select(LabResult).where(
                LabResult.visit_id == visit.id, LabResult.lab_test_id == lab_test.id, LabResult.measured_at == measured_at,
            )
        )).scalar_one_or_none()
        if existing is not None:
            existing.result_value = numeric
            existing.is_abnormal = flag in ABNORMAL_FLAGS
            existing.result_status = status
            existing.source_message_id = inbound_id
            result = existing
        else:
            result = LabResult(
                visit_id=visit.id, lab_test_id=lab_test.id, result_value=numeric, measured_at=measured_at,
                is_abnormal=flag in ABNORMAL_FLAGS, result_status=status, source_message_id=inbound_id,
            )
            db.add(result)
        await db.flush()
        applied += 1
        events.append(ClinicalEvent("lab_result.corrected" if existing else "lab_result.created", patient.id, {
            "lab_result_id": result.id, "visit_id": visit.id, "test_code": lab_test.code,
            "abnormal": flag in ABNORMAL_FLAGS, "critical": flag in CRITICAL_FLAGS, "result_status": status,
        }))

    if applied == 0:
        raise ReviewRequired("No numeric results could be applied from this message.")
    return patient


async def _apply(db: AsyncSession, message: HL7Message, inbound_id: str,
                 events: List[ClinicalEvent], warnings: List[str]) -> Patient:
    message_type = message.message_type
    if message_type in ("ADT^A01", "ADT^A04"):
        return await _handle_admit_or_register(db, message, events)
    if message_type == "ADT^A08":
        return await _handle_update(db, message, events)
    if message_type == "ADT^A03":
        return await _handle_discharge(db, message, events)
    if message_type == "ADT^A02":
        return await _handle_transfer(db, message, events)
    if message_type == "ADT^A11":
        return await _handle_cancel_admit(db, message, events)
    if message_type == "ADT^A13":
        return await _handle_cancel_discharge(db, message, events)
    if message_type == "ADT^A40":
        return await _handle_merge(db, message, inbound_id)
    if message_type == "ORU^R01":
        return await _handle_results(db, message, inbound_id, events, warnings)
    raise InvalidMessage(f"Unsupported message type {message_type}.")


async def _set_status(message_id: str, status: str, detail: Optional[str], patient_id: Optional[str] = None) -> None:
    async with database.AsyncSessionLocal() as db:
        row = await db.get(InboundMessage, message_id)
        if row:
            row.status = status
            row.error_detail = detail[:2000] if detail else None
            row.processed_at = get_utc_now()
            if patient_id:
                row.patient_id = patient_id
            await db.commit()


async def _run(message: HL7Message, message_id: str) -> ProcessingOutcome:
    events: List[ClinicalEvent] = []
    warnings: List[str] = []
    try:
        async with database.AsyncSessionLocal() as db:
            row = await db.get(InboundMessage, message_id)
            row.attempt_count += 1
            try:
                patient = await _apply(db, message, message_id, events, warnings)
            except MergeQueued as queued:
                # Keep the merge request; the message itself waits for the approval decision.
                row.status = "NEEDS_REVIEW"
                row.error_detail = str(queued)
                row.processed_at = get_utc_now()
                await db.commit()
                EventBus.publish(ClinicalEvent("integration.needs_review", None, {
                    "message_id": message_id, "message_type": message.message_type, "reason": "Patient merge awaiting approval",
                }, admin_only=True))
                return ProcessingOutcome("AA", "NEEDS_REVIEW", f"Accepted; {queued}", message_id)
            row.status = "PROCESSED"
            row.processed_at = get_utc_now()
            row.patient_id = patient.id
            row.error_detail = "; ".join(warnings)[:2000] if warnings else None
            await OutboxService.enqueue_record_anchor(db, f"inbound:{message_id}", _provenance_commitment(message.raw), 1)
            await db.commit()
    except InvalidMessage as exc:
        await _set_status(message_id, "REJECTED", str(exc))
        return ProcessingOutcome("AR", "REJECTED", str(exc), message_id)
    except ReviewRequired as exc:
        await _set_status(message_id, "NEEDS_REVIEW", str(exc))
        EventBus.publish(ClinicalEvent("integration.needs_review", None, {
            "message_id": message_id, "message_type": message.message_type, "reason": str(exc)[:200],
        }, admin_only=True))
        return ProcessingOutcome("AA", "NEEDS_REVIEW", f"Accepted; queued for manual review: {exc}", message_id)
    except Exception:
        logger.exception("HL7 message %s failed with an internal error.", message_id)
        await _set_status(message_id, "RECEIVED", "Internal processing error; the sender should retry.")
        return ProcessingOutcome("AE", "RECEIVED", "Internal processing error; retry later.", message_id)

    for event in events:
        EventBus.publish(event)
    return ProcessingOutcome("AA", "PROCESSED", "Message processed.", message_id, patient.id, warnings=warnings)


async def process_hl7_message(raw: str, source_system: str) -> ProcessingOutcome:
    """Ledger, de-duplicate, and process one inbound HL7 v2 message. Never raises for bad input."""
    try:
        message = parse_message(raw)
    except HL7ParseError as exc:
        outcome = ProcessingOutcome("AR", "REJECTED", f"Unparseable message: {exc}")
        outcome.ack = build_ack(None, "AR", outcome.detail)
        return outcome

    if message.message_type not in SUPPORTED_TYPES:
        outcome = ProcessingOutcome("AR", "REJECTED", f"Unsupported message type {message.message_type}.")
        outcome.ack = build_ack(message, "AR", outcome.detail)
        return outcome

    source = (source_system or message.sending_application or "unknown")[:100]
    raw_hash = sha256_hex(message.raw)
    try:
        async with database.AsyncSessionLocal() as db:
            existing = (await db.execute(
                select(InboundMessage).where(
                    InboundMessage.source_system == source,
                    InboundMessage.message_control_id == message.control_id[:100],
                )
            )).scalar_one_or_none()
            if existing is not None:
                if existing.raw_sha256 != raw_hash:
                    outcome = ProcessingOutcome("AR", existing.status, "Control ID reused with different content.", existing.id)
                elif existing.status == "RECEIVED":
                    message_id = existing.id  # earlier attempt hit an internal error: retry it
                    outcome = None
                else:
                    outcome = ProcessingOutcome("AA", existing.status, "Duplicate message; already received.",
                                                existing.id, existing.patient_id, duplicate=True)
                if outcome is not None:
                    outcome.ack = build_ack(message, outcome.ack_code, outcome.detail)
                    return outcome
            else:
                row = InboundMessage(
                    source_system=source,
                    message_control_id=message.control_id[:100],
                    protocol="HL7V2",
                    message_type=message.message_type,
                    status="RECEIVED",
                    raw_sha256=raw_hash,
                    raw_encrypted="pending",
                )
                db.add(row)
                await db.flush()
                row.raw_encrypted = encrypt_text(message.raw, f"inbound:{row.id}")
                await db.commit()
                message_id = row.id
    except IntegrityError:
        # A concurrent delivery of the same message won the insert.
        outcome = ProcessingOutcome("AA", "RECEIVED", "Duplicate message; already received.", duplicate=True)
        outcome.ack = build_ack(message, "AA", outcome.detail)
        return outcome
    except Exception:
        logger.exception("Could not record inbound HL7 message.")
        outcome = ProcessingOutcome("AE", "RECEIVED", "Message store unavailable; retry later.")
        outcome.ack = build_ack(message, "AE", outcome.detail)
        return outcome

    outcome = await _run(message, message_id)
    outcome.ack = build_ack(message, outcome.ack_code, outcome.detail)
    return outcome


async def reprocess_message(message_id: str) -> ProcessingOutcome:
    """Re-run a stored message after its blocking issue (unknown doctor, facility, ...) is fixed."""
    async with database.AsyncSessionLocal() as db:
        row = await db.get(InboundMessage, message_id)
        if row is None:
            raise LookupError("Inbound message not found.")
        if row.status == "PROCESSED":
            return ProcessingOutcome("AA", "PROCESSED", "Message was already processed.", row.id, row.patient_id)
        raw = decrypt_text(row.raw_encrypted, f"inbound:{row.id}")
        row.status = "RECEIVED"
        await db.commit()
    message = parse_message(raw)
    outcome = await _run(message, message_id)
    outcome.ack = build_ack(message, outcome.ack_code, outcome.detail)
    return outcome
