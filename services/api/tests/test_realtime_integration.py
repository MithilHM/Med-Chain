"""Real-time clinical integration, event authorization, session safety, and outbox delivery semantics."""
import asyncio
import hashlib
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from src import database
from src.config import settings
from src.models import AppUser, Doctor, InboundMessage, LabResult, OutboxEvent, Patient, PatientIdentifier, Visit
from src.services.auth import create_access_token, hash_password
from src.services.events import ClinicalEvent, EventBus, Subscriber
from src.services.outbox import OutboxWorker


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def segment(name: str, values: dict) -> str:
    """Build a segment with each value at its exact HL7 field number (avoids miscounted pipes)."""
    fields = [""] * (max(values) + 1)
    fields[0] = name
    for number, value in values.items():
        fields[number] = value
    return "|".join(fields)


def adt_a01(control_id: str, mrn: str, visit_number: str, provider: str = "PRV-1001", dob: str = "19700101", sex: str = "F") -> str:
    return "\r".join([
        f"MSH|^~\\&|EPIC|MAMC|MEDCHAIN|MEDCHAIN|{_ts()}||ADT^A01^ADT_A01|{control_id}|P|2.5.1",
        f"EVN|A01|{_ts()}",
        f"PID|1||{mrn}^^^MAMC^MR||DOE^JANE||{dob}|{sex}",
        segment("PV1", {1: "1", 2: "I", 3: "ICU^101^A^MAMC", 7: f"{provider}^CHEN^SARAH", 19: visit_number,
                        44: "20261120083000"}),
    ])


def oru_r01(control_id: str, mrn: str, visit_number: str, value: str = "6.9", flag: str = "HH") -> str:
    return "\r".join([
        f"MSH|^~\\&|LAB|MAMC|MEDCHAIN|MEDCHAIN|{_ts()}||ORU^R01^ORU_R01|{control_id}|P|2.5.1",
        f"PID|1||{mrn}^^^MAMC^MR",
        segment("PV1", {1: "1", 2: "I", 3: "ICU^101^A^MAMC", 7: "PRV-1001", 19: visit_number}),
        "OBR|1|ORD123|FIL456|24323-8^Comprehensive metabolic panel^LN|||20261120090000",
        f"OBX|1|NM|2823-3^Potassium [Moles/volume] in Serum or Plasma^LN||{value}|mmol/L|3.5-5.1|{flag}|||F|||20261120091500",
        "OBX|2|ST|8251-1^Service comment^LN||Hemolyzed sample||||||F",
    ])


async def _post_hl7(client, headers, message: str) -> dict:
    res = await client.post("/api/v1/integration/hl7v2?format=json", content=message.encode("utf-8"),
                            headers={**headers, "Content-Type": "x-application/hl7-v2+er7"})
    assert res.status_code == 200, res.text
    return res.json()


@pytest.mark.asyncio
async def test_hl7_admission_and_critical_lab_flow(client):
    admin = (await client.post("/api/v1/auth/demo-switch?role=admin")).json()
    headers = {"Authorization": f"Bearer {admin['access_token']}"}
    mrn, visit_number = f"MRN-{uuid.uuid4().hex[:6]}", f"V-{uuid.uuid4().hex[:6]}"

    admit = await _post_hl7(client, headers, adt_a01(f"CTRL-{uuid.uuid4().hex[:8]}", mrn, visit_number))
    assert admit["ack_code"] == "AA" and admit["status"] == "PROCESSED", admit
    assert "MSA|AA|" in admit["ack"]
    patient_id = admit["patient_id"]

    # The attending doctor from PV1-7 was put on the care team, so the chart opens for them.
    doctor = (await client.post("/api/v1/auth/demo-switch?role=doctor")).json()
    doctor_headers = {"Authorization": f"Bearer {doctor['access_token']}"}
    assert (await client.get(f"/api/v1/patients/{patient_id}", headers=doctor_headers)).status_code == 200

    # Real-time delivery: the doctor sees the critical result; a researcher subscriber sees nothing.
    doctor_sub = EventBus.subscribe(Subscriber(user_id="doc", role="doctor", authorized_patient_ids={patient_id}))
    researcher_sub = EventBus.subscribe(Subscriber(user_id="res", role="researcher"))
    try:
        result = await _post_hl7(client, headers, oru_r01(f"LAB-{uuid.uuid4().hex[:8]}", mrn, visit_number))
        assert result["status"] == "PROCESSED", result
        assert any("not numeric" in w for w in result["warnings"])  # ST result reported, not silently dropped
        event = await asyncio.wait_for(doctor_sub.queue.get(), timeout=2)
        while event.event_type != "lab_result.created":
            event = await asyncio.wait_for(doctor_sub.queue.get(), timeout=2)
        assert event.patient_id == patient_id
        assert event.data["critical"] is True and event.data["test_code"] == "2823-3"
        assert "value" not in event.data  # events carry flags, not clinical values
        assert researcher_sub.queue.empty()
    finally:
        EventBus.unsubscribe(doctor_sub)
        EventBus.unsubscribe(researcher_sub)

    async with database.AsyncSessionLocal() as db:
        visit = (await db.execute(select(Visit).where(Visit.external_visit_number == visit_number))).scalar_one()
        labs = (await db.execute(select(LabResult).where(LabResult.visit_id == visit.id))).scalars().all()
        assert len(labs) == 1 and labs[0].is_abnormal and float(labs[0].result_value) == 6.9
        # The raw HL7 payload is stored encrypted, never in plaintext.
        ledger = (await db.execute(select(InboundMessage).where(InboundMessage.patient_id == patient_id))).scalars().all()
        assert ledger and all(mrn not in row.raw_encrypted for row in ledger)


@pytest.mark.asyncio
async def test_hl7_duplicates_rejections_and_review_queue(client):
    admin = (await client.post("/api/v1/auth/demo-switch?role=admin")).json()
    headers = {"Authorization": f"Bearer {admin['access_token']}"}
    control_id = f"DUP-{uuid.uuid4().hex[:8]}"
    message = adt_a01(control_id, f"MRN-{uuid.uuid4().hex[:6]}", f"V-{uuid.uuid4().hex[:6]}")

    first = await _post_hl7(client, headers, message)
    second = await _post_hl7(client, headers, message)
    assert first["status"] == "PROCESSED"
    assert second["duplicate"] is True and second["ack_code"] == "AA"

    # Same control ID with different content is refused (prevents silent overwrites).
    altered = await _post_hl7(client, headers, message.replace("DOE^JANE", "DOE^JOHN"))
    assert altered["ack_code"] == "AR"

    # Unparseable input is rejected with an HL7 ACK rather than an exception.
    garbage = await _post_hl7(client, headers, "this is not hl7")
    assert garbage["ack_code"] == "AR"

    # Results for an unknown patient are never attached by guesswork: they go to manual review.
    orphan = await _post_hl7(client, headers, oru_r01(f"ORPH-{uuid.uuid4().hex[:8]}", "MRN-DOES-NOT-EXIST", "V-NONE"))
    assert orphan["status"] == "NEEDS_REVIEW" and orphan["ack_code"] == "AA"
    queue = (await client.get("/api/v1/integration/messages?status=NEEDS_REVIEW", headers=headers)).json()
    assert any(item["id"] == orphan["message_id"] for item in queue)
    assert all("raw_encrypted" not in item for item in queue)


@pytest.mark.asyncio
async def test_hl7_unknown_provider_review_then_reprocess(client):
    admin = (await client.post("/api/v1/auth/demo-switch?role=admin")).json()
    headers = {"Authorization": f"Bearer {admin['access_token']}"}
    provider = f"PRV-NEW-{uuid.uuid4().hex[:4]}"
    pending = await _post_hl7(client, headers, adt_a01(f"PRV-{uuid.uuid4().hex[:8]}", f"MRN-{uuid.uuid4().hex[:6]}",
                                                       f"V-{uuid.uuid4().hex[:6]}", provider=provider))
    assert pending["status"] == "NEEDS_REVIEW"
    assert provider in pending["detail"]

    # Operator fixes the mapping, then reprocesses the stored message.
    async with database.AsyncSessionLocal() as db:
        doctor = (await db.execute(select(Doctor))).scalars().first()
        doctor.external_provider_id = provider
        await db.commit()
    try:
        res = await client.post(f"/api/v1/integration/messages/{pending['message_id']}/reprocess", headers=headers)
        assert res.status_code == 200 and res.json()["status"] == "PROCESSED", res.text
    finally:
        async with database.AsyncSessionLocal() as db:
            doctor = (await db.execute(select(Doctor).where(Doctor.external_provider_id == provider))).scalar_one()
            doctor.external_provider_id = "PRV-1001"
            await db.commit()


@pytest.mark.asyncio
async def test_hl7_conflicting_demographics_go_to_review(client):
    admin = (await client.post("/api/v1/auth/demo-switch?role=admin")).json()
    headers = {"Authorization": f"Bearer {admin['access_token']}"}
    # PT-100201 is a seeded MAMC MRN (DOB 1975-06-15, M). A different DOB must not be merged.
    res = await _post_hl7(client, headers, adt_a01(f"CONF-{uuid.uuid4().hex[:8]}", "PT-100201",
                                                   f"V-{uuid.uuid4().hex[:6]}", dob="19990101", sex="M"))
    assert res["status"] == "NEEDS_REVIEW"
    async with database.AsyncSessionLocal() as db:
        patient = (await db.execute(select(Patient).where(Patient.display_code == "PT-100201"))).scalar_one()
        assert patient.date_of_birth.isoformat() == "1975-06-15"


@pytest.mark.asyncio
async def test_integration_key_authentication(client, monkeypatch):
    key = "test-interface-engine-key-123456789"
    monkeypatch.setattr(settings, "INTEGRATION_API_KEYS", f"mirth-test:{hashlib.sha256(key.encode()).hexdigest()}")
    message = adt_a01(f"KEY-{uuid.uuid4().hex[:8]}", f"MRN-{uuid.uuid4().hex[:6]}", f"V-{uuid.uuid4().hex[:6]}")

    ok = await client.post("/api/v1/integration/hl7v2", content=message.encode(), headers={"X-Integration-Key": key})
    assert ok.status_code == 200 and ok.headers["X-MedChain-Ack-Code"] == "AA"
    assert ok.text.startswith("MSH|")

    bad = await client.post("/api/v1/integration/hl7v2", content=message.encode(), headers={"X-Integration-Key": "wrong"})
    assert bad.status_code == 401

    doctor = (await client.post("/api/v1/auth/demo-switch?role=doctor")).json()
    forbidden = await client.post("/api/v1/integration/hl7v2", content=message.encode(),
                                  headers={"Authorization": f"Bearer {doctor['access_token']}"})
    assert forbidden.status_code == 403


@pytest.mark.asyncio
async def test_event_bus_authorization_rules():
    patient_sub = Subscriber(user_id="p", role="patient", own_patient_id="P1")
    doctor_sub = Subscriber(user_id="d", role="doctor", authorized_patient_ids={"P1"})
    analyst_sub = Subscriber(user_id="a", role="insurance_analyst")
    admin_sub = Subscriber(user_id="x", role="admin")
    own, other, ops = ClinicalEvent("lab_result.created", "P1"), ClinicalEvent("lab_result.created", "P2"), \
        ClinicalEvent("integration.needs_review", None, admin_only=True)
    assert patient_sub.accepts(own) and not patient_sub.accepts(other) and not patient_sub.accepts(ops)
    assert doctor_sub.accepts(own) and not doctor_sub.accepts(other) and not doctor_sub.accepts(ops)
    assert not analyst_sub.accepts(own)
    assert admin_sub.accepts(own) and admin_sub.accepts(ops)


@pytest.mark.asyncio
async def test_events_stream_rejects_non_care_roles(client):
    researcher = (await client.post("/api/v1/auth/demo-switch?role=researcher")).json()
    res = await client.get("/api/v1/events/stream", headers={"Authorization": f"Bearer {researcher['access_token']}"})
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_unregistered_session_tokens_are_rejected(client):
    async with database.AsyncSessionLocal() as db:
        admin = (await db.execute(select(AppUser).where(AppUser.email == "admin@medchain.local"))).scalar_one()
    # Correctly signed, unexpired, but never registered as a session: previously accepted (fail-open).
    token, _, _ = create_access_token({"sub": admin.id, "role": "admin"})
    res = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_account_lockout_after_repeated_failures(client):
    email = f"lockout-{uuid.uuid4().hex[:6]}@medchain.local"
    async with database.AsyncSessionLocal() as db:
        db.add(AppUser(email=email, password_hash=hash_password("Correct-Horse-1"), role="researcher"))
        await db.commit()
    for _ in range(settings.LOGIN_MAX_FAILED_ATTEMPTS):
        assert (await client.post("/api/v1/auth/login", json={"email": email, "password": "wrong"})).status_code == 401
    # Correct password is refused while locked, with the same generic message.
    locked = await client.post("/api/v1/auth/login", json={"email": email, "password": "Correct-Horse-1"})
    assert locked.status_code == 401
    assert locked.json()["detail"] == "Incorrect email or password."


@pytest.mark.asyncio
async def test_outbox_keeps_events_queued_while_chain_is_unavailable(client):
    admin = (await client.post("/api/v1/auth/demo-switch?role=admin")).json()
    headers = {"Authorization": f"Bearer {admin['access_token']}"}
    doc = await client.post("/api/v1/documents", json={
        "patient_id": "PT-100201", "document_type": "Progress Note",
        "title": "Outbox semantics", "content": "Evidence must not be dropped while the chain is offline.",
    }, headers=headers)
    assert doc.status_code == 200
    document_id = doc.json()["id"]

    summary = await OutboxWorker.run_once(limit=500)
    assert summary["claimed"] >= 1

    async with database.AsyncSessionLocal() as db:
        event = (await db.execute(
            select(OutboxEvent).where(OutboxEvent.aggregate_id == document_id,
                                      OutboxEvent.event_type == "BLOCKCHAIN_ANCHOR_RECORD")
        )).scalar_one()
        # No chain in the test environment: the event must stay queued with a scheduled retry,
        # not be marked COMPLETED (the previous behavior silently discarded the evidence).
        assert event.status == "PENDING"
        assert event.attempt_count == 1
        assert event.next_attempt_at is not None
        assert event.last_error
