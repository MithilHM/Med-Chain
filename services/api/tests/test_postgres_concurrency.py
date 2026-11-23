"""PostgreSQL-only guarantees that SQLite cannot exercise (row locks, advisory locks, LISTEN/NOTIFY).

Runs when TEST_POSTGRES_URL is set (CI provides a PostgreSQL service), e.g.
TEST_POSTGRES_URL=postgresql+asyncpg://user:pass@localhost:5432/db
"""
import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src import database
from src.database import Base
import src.models  # noqa: F401
from src.models import AppUser, Consent, Patient, ResearchOrganization, ResearchProject
from src.services.consent_engine import ConsentPolicyEngine
from src.services.events import CHANNEL, ClinicalEvent, EventBus, EventRelay, Subscriber
from src.services.outbox import OutboxWorker, _ADVISORY_LOCK_KEY

PG_URL = os.environ.get("TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not PG_URL, reason="TEST_POSTGRES_URL not set; PostgreSQL-only checks skipped.")


@pytest_asyncio.fixture
async def pg_engine():
    engine = create_async_engine(PG_URL)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


async def _seed_consent(engine) -> dict:
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSession(engine, expire_on_commit=False) as db:
        researcher = AppUser(email=f"pg-researcher-{suffix}@test", password_hash="!", role="researcher")
        org = ResearchOrganization(name=f"PG Org {suffix}", organization_type="Test")
        db.add_all([researcher, org])
        await db.flush()
        project = ResearchProject(organization_id=org.id, title="PG concurrency", purpose="test",
                                  status="ACTIVE", created_by=researcher.id)
        patient = Patient(display_code=f"PG-{suffix}", date_of_birth=datetime(1980, 1, 1).date(), sex="F")
        db.add_all([project, patient])
        await db.flush()
        now = datetime.now(timezone.utc)
        consent = Consent(patient_id=patient.id, requester_project_id=project.id, purpose="test",
                          scope_json=["aggregate_diagnoses"], valid_from=now - timedelta(days=1),
                          valid_until=now + timedelta(days=30), status="GRANTED", granted_at=now)
        db.add(consent)
        await db.commit()
        return {"researcher_id": researcher.id, "project_id": project.id, "patient_id": patient.id, "consent_id": consent.id}


@pytest.mark.asyncio
async def test_revocation_waits_for_in_flight_authorized_query(pg_engine):
    ids = await _seed_consent(pg_engine)
    async with AsyncSession(pg_engine) as query_session, AsyncSession(pg_engine) as revoke_session:
        actor = await query_session.get(AppUser, ids["researcher_id"])
        allowed, _, _ = await ConsentPolicyEngine.evaluate_research_access(
            query_session, actor, ids["project_id"], "aggregate_diagnoses", target_patient_id=ids["patient_id"]
        )
        assert allowed  # the query transaction now holds FOR SHARE on the consent row

        with pytest.raises(DBAPIError):  # revocation cannot take FOR UPDATE while the query is in flight
            await revoke_session.execute(
                select(Consent).where(Consent.id == ids["consent_id"]).with_for_update(nowait=True)
            )
        await revoke_session.rollback()

        await query_session.commit()  # query finishes; its locks are released

        consent = (await revoke_session.execute(
            select(Consent).where(Consent.id == ids["consent_id"]).with_for_update(nowait=True)
        )).scalar_one()
        consent.status, consent.revoked_at = "REVOKED", datetime.now(timezone.utc)
        await revoke_session.commit()

    async with AsyncSession(pg_engine) as later:
        actor = await later.get(AppUser, ids["researcher_id"])
        allowed, _, _ = await ConsentPolicyEngine.evaluate_research_access(
            later, actor, ids["project_id"], "aggregate_diagnoses", target_patient_id=ids["patient_id"]
        )
        assert not allowed  # every query after the revocation is denied


async def _wait_for(predicate, timeout=10.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_events_fan_out_through_listen_notify(pg_engine):
    assert EventRelay.start(pg_engine)
    subscriber = EventBus.subscribe(Subscriber(user_id="pg-admin", role="admin"))
    try:
        await _wait_for(lambda: EventRelay.active)
        published = ClinicalEvent("lab_result.created", "PG-PATIENT", {"critical": True})
        EventBus.publish(published)
        received = await asyncio.wait_for(subscriber.queue.get(), timeout=10)
        assert received.id == published.id and received.data["critical"] is True

        # A NOTIFY from another process (e.g. the MLLP listener) reaches this process's subscribers.
        foreign = ClinicalEvent("encounter.admitted", "PG-PATIENT-2", {})
        async with pg_engine.connect() as other_process:
            await other_process.execute(text("SELECT pg_notify(:c, :p)"), {"c": CHANNEL, "p": foreign.to_wire()})
            await other_process.commit()
        received = await asyncio.wait_for(subscriber.queue.get(), timeout=10)
        assert received.id == foreign.id
    finally:
        EventBus.unsubscribe(subscriber)
        await EventRelay.stop()


@pytest.mark.asyncio
async def test_outbox_has_a_single_sender_across_replicas(pg_engine, monkeypatch):
    monkeypatch.setattr(database, "async_engine", pg_engine)
    monkeypatch.setattr(database, "AsyncSessionLocal", async_sessionmaker(pg_engine, expire_on_commit=False))
    monkeypatch.setattr(database, "is_fallback_active", False)
    async with pg_engine.connect() as other_replica:
        assert (await other_replica.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _ADVISORY_LOCK_KEY})).scalar()
        summary = await OutboxWorker.run_once(limit=5)
        assert summary["skipped_not_leader"] == 1 and summary["claimed"] == 0
        await other_replica.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _ADVISORY_LOCK_KEY})
    summary = await OutboxWorker.run_once(limit=5)
    assert summary["skipped_not_leader"] == 0
