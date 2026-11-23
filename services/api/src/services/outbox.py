"""Transactional outbox: durable, retried delivery of evidence events to the audit chain.

Producers call `OutboxService.enqueue` inside the same database transaction that changes
authoritative state (consent, access decision, document commitment). Either both commit or
neither does, so the chain can never record something the database rolled back, and no
committed event is lost when the chain is offline.

A background worker (`OutboxWorker`) claims due events, dispatches them, and records the
outcome. Delivery is at-least-once; dispatch handlers check on-chain state first so retries
do not duplicate state changes.
"""
import asyncio
import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from src import database
from src.config import settings
from src.models.base import get_utc_now
from src.models.consent import AccessEvent, BlockchainEvent, Consent, OutboxEvent
from src.services import blockchain as chain
from src.services.blockchain import BlockchainService, ChainResult

logger = logging.getLogger("medchain.outbox")

_ADVISORY_LOCK_KEY = 0x4D45444348  # "MEDCH": one chain sender across API instances


def _backoff_seconds(attempt: int) -> int:
    return min(5 * (2 ** max(attempt - 1, 0)), 3600)


class OutboxService:
    @staticmethod
    async def enqueue(
        db: AsyncSession,
        event_type: str,
        aggregate_id: str,
        payload_json: Dict[str, Any],
    ) -> OutboxEvent:
        """Add an event to the caller's open transaction. The caller commits."""
        event = OutboxEvent(
            event_type=event_type,
            aggregate_id=aggregate_id,
            payload_json=payload_json,
            status="PENDING",
            attempt_count=0,
            max_retries=settings.OUTBOX_MAX_RETRIES,
            next_attempt_at=None,
        )
        db.add(event)
        await db.flush()
        return event

    @staticmethod
    async def enqueue_access_event(db: AsyncSession, access_event: AccessEvent) -> OutboxEvent:
        return await OutboxService.enqueue(
            db,
            "BLOCKCHAIN_ACCESS_EVENT",
            access_event.id,
            {
                "access_event_id": access_event.id,
                "actor_id": access_event.actor_user_id,
                "resource_ref": access_event.resource_reference,
                "action": access_event.action,
                "decision": access_event.decision,
            },
        )

    @staticmethod
    async def enqueue_record_anchor(
        db: AsyncSession, document_id: str, commitment_hash: str, version: int
    ) -> BlockchainEvent:
        chain_event = BlockchainEvent(
            event_type="RECORD_COMMITMENT",
            opaque_reference=document_id,
            commitment_hash=commitment_hash,
            status="PENDING",
        )
        db.add(chain_event)
        await db.flush()
        await OutboxService.enqueue(
            db,
            "BLOCKCHAIN_ANCHOR_RECORD",
            document_id,
            {
                "record_ref": document_id,
                "commitment_hash": commitment_hash,
                "version": version,
                "blockchain_event_id": chain_event.id,
            },
        )
        return chain_event

    @staticmethod
    async def dispatch(event_type: str, aggregate_id: str, payload: Dict[str, Any]) -> ChainResult:
        if event_type == "BLOCKCHAIN_ANCHOR_RECORD":
            return await BlockchainService.anchor_record(
                payload.get("record_ref", aggregate_id), payload["commitment_hash"], int(payload.get("version", 1))
            )
        if event_type == "BLOCKCHAIN_CONSENT_GRANTED":
            return await BlockchainService.record_consent_granted(
                payload.get("consent_id", aggregate_id),
                payload["patient_id"],
                payload["project_id"],
                int(payload["valid_until_ts"]),
            )
        if event_type == "BLOCKCHAIN_CONSENT_REVOKED":
            return await BlockchainService.record_consent_revoked(
                payload.get("consent_id", aggregate_id), payload["patient_id"]
            )
        if event_type == "BLOCKCHAIN_ACCESS_EVENT":
            return await BlockchainService.log_access_event(
                payload.get("access_event_id", aggregate_id),
                payload["actor_id"],
                payload["resource_ref"],
                payload["action"],
                payload["decision"],
            )
        if event_type == "GRAPH_SYNC_NOTICE":
            return ChainResult(chain.CONFIRMED, detail="Graph projection is rebuilt by the admin rebuild action.")
        return ChainResult(chain.PERMANENT_FAILURE, detail=f"Unknown outbox event type: {event_type}")

    @staticmethod
    async def _apply_success(db: AsyncSession, event: OutboxEvent, result: ChainResult) -> None:
        payload = event.payload_json or {}
        if event.event_type == "BLOCKCHAIN_ANCHOR_RECORD" and payload.get("blockchain_event_id"):
            chain_event = await db.get(BlockchainEvent, payload["blockchain_event_id"])
            if chain_event:
                chain_event.status = "CONFIRMED"
                chain_event.transaction_hash = result.tx_hash or chain_event.transaction_hash
                chain_event.block_number = result.block_number or chain_event.block_number
        elif event.event_type in ("BLOCKCHAIN_CONSENT_GRANTED", "BLOCKCHAIN_CONSENT_REVOKED") and result.tx_hash:
            consent = await db.get(Consent, payload.get("consent_id", event.aggregate_id))
            if consent:
                consent.chain_tx_hash = result.tx_hash
        elif event.event_type == "BLOCKCHAIN_ACCESS_EVENT" and result.tx_hash:
            access_event = await db.get(AccessEvent, payload.get("access_event_id", event.aggregate_id))
            if access_event:
                access_event.chain_tx_hash = result.tx_hash

    @staticmethod
    async def _apply_terminal_failure(db: AsyncSession, event: OutboxEvent) -> None:
        payload = event.payload_json or {}
        if event.event_type == "BLOCKCHAIN_ANCHOR_RECORD" and payload.get("blockchain_event_id"):
            chain_event = await db.get(BlockchainEvent, payload["blockchain_event_id"])
            if chain_event:
                chain_event.status = "FAILED"

    @staticmethod
    async def process_pending_events(db: Optional[AsyncSession] = None, limit: int = 20) -> int:
        """Compatibility wrapper used by the admin endpoint; runs one worker iteration."""
        summary = await OutboxWorker.run_once(limit=limit)
        return summary["completed"]


class OutboxWorker:
    _task: Optional[asyncio.Task] = None

    @staticmethod
    async def _claim(limit: int) -> List[Dict[str, Any]]:
        now = get_utc_now()
        async with database.AsyncSessionLocal() as db:
            # Release events claimed by a worker that crashed mid-delivery.
            stale_before = now - timedelta(seconds=settings.OUTBOX_STALE_PROCESSING_SECONDS)
            await db.execute(
                update(OutboxEvent)
                .where(OutboxEvent.status == "PROCESSING", OutboxEvent.locked_at < stale_before)
                .values(status="PENDING", locked_at=None)
            )
            query = (
                select(OutboxEvent)
                .where(
                    OutboxEvent.status == "PENDING",
                    or_(OutboxEvent.next_attempt_at.is_(None), OutboxEvent.next_attempt_at <= now),
                )
                .order_by(OutboxEvent.created_at.asc())
                .limit(limit)
            )
            if not database.is_fallback_active:
                query = query.with_for_update(skip_locked=True)
            events = (await db.execute(query)).scalars().all()
            claimed = []
            for event in events:
                event.status = "PROCESSING"
                event.locked_at = now
                event.attempt_count += 1
                claimed.append({
                    "id": event.id,
                    "event_type": event.event_type,
                    "aggregate_id": event.aggregate_id,
                    "payload": dict(event.payload_json or {}),
                })
            await db.commit()
            return claimed

    @staticmethod
    async def _record_outcome(event_id: str, result: ChainResult) -> str:
        async with database.AsyncSessionLocal() as db:
            event = await db.get(OutboxEvent, event_id)
            if not event:
                return "MISSING"
            event.locked_at = None
            if result.status == chain.CONFIRMED:
                event.status = "COMPLETED"
                event.processed_at = get_utc_now()
                event.last_error = None
                await OutboxService._apply_success(db, event, result)
            elif result.status == chain.PERMANENT_FAILURE or event.attempt_count >= event.max_retries:
                event.status = "FAILED"
                event.last_error = (result.detail or "Delivery failed.")[:500]
                await OutboxService._apply_terminal_failure(db, event)
                logger.error("[Outbox] Event %s (%s) failed permanently: %s", event.id, event.event_type, event.last_error)
            else:
                event.status = "PENDING"
                event.last_error = (result.detail or "Retry scheduled.")[:500]
                event.next_attempt_at = get_utc_now() + timedelta(seconds=_backoff_seconds(event.attempt_count))
            status = event.status
            await db.commit()
            return status

    @staticmethod
    async def run_once(limit: Optional[int] = None) -> Dict[str, int]:
        """Claim and deliver one batch. Returns counts by outcome."""
        summary = {"claimed": 0, "completed": 0, "retry": 0, "failed": 0, "skipped_not_leader": 0}
        limit = limit or settings.OUTBOX_BATCH_SIZE
        leader_conn = None
        try:
            if not database.is_fallback_active:
                leader_conn = await database.async_engine.connect()
                got_lock = (await leader_conn.execute(
                    text("SELECT pg_try_advisory_lock(:key)"), {"key": _ADVISORY_LOCK_KEY}
                )).scalar()
                if not got_lock:
                    summary["skipped_not_leader"] = 1
                    return summary

            events = await OutboxWorker._claim(limit)
            summary["claimed"] = len(events)
            for item in events:
                try:
                    result = await OutboxService.dispatch(item["event_type"], item["aggregate_id"], item["payload"])
                except Exception as exc:  # defensive: a handler bug must not stall the queue
                    logger.exception("[Outbox] Dispatch raised for event %s", item["id"])
                    result = ChainResult(chain.RETRY, detail=str(exc)[:300])
                outcome = await OutboxWorker._record_outcome(item["id"], result)
                if outcome == "COMPLETED":
                    summary["completed"] += 1
                elif outcome == "FAILED":
                    summary["failed"] += 1
                else:
                    summary["retry"] += 1
            return summary
        finally:
            if leader_conn is not None:
                try:
                    await leader_conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": _ADVISORY_LOCK_KEY})
                finally:
                    await leader_conn.close()

    @staticmethod
    async def _loop() -> None:
        logger.info("Outbox worker started (poll every %ss).", settings.OUTBOX_POLL_SECONDS)
        while True:
            try:
                summary = await OutboxWorker.run_once()
                if summary["claimed"]:
                    logger.info("[Outbox] %s", summary)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("[Outbox] Worker iteration failed; retrying after poll interval.")
            await asyncio.sleep(settings.OUTBOX_POLL_SECONDS)

    @classmethod
    def start(cls) -> None:
        if settings.OUTBOX_WORKER_ENABLED and cls._task is None:
            cls._task = asyncio.create_task(cls._loop(), name="medchain-outbox-worker")

    @classmethod
    async def stop(cls) -> None:
        if cls._task is not None:
            cls._task.cancel()
            try:
                await cls._task
            except asyncio.CancelledError:
                pass
            cls._task = None
