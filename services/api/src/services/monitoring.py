"""Operational monitoring: alert evaluation, alert lifecycle, webhook notification, metrics.

Alerts open when a condition appears, update while it persists, and resolve when it clears.
Each transition is sent once to ALERT_WEBHOOK_URL (JSON with a `text` field, accepted by Teams,
Slack, and most incident tools). Alert text never contains patient identifiers or clinical data.
On PostgreSQL an advisory lock ensures one replica evaluates and notifies at a time.
"""
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import httpx
from sqlalchemy import func, select, text

from src import database
from src.config import settings
from src.models import (
    EmergencyAccessGrant, InboundMessage, OperationalAlert, OutboxEvent, PatientMergeRequest,
)
from src.services.events import EventBus, EventRelay

logger = logging.getLogger("medchain.monitoring")
_LOCK_KEY = 0x4D45444D4F  # "MEDMO"


@dataclass
class AlertCondition:
    key: str
    severity: str
    summary: str


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


async def collect_metrics(db) -> Dict[str, float]:
    now = datetime.now(timezone.utc)
    metrics: Dict[str, float] = {}
    for status, count in (await db.execute(
        select(OutboxEvent.status, func.count(OutboxEvent.id)).group_by(OutboxEvent.status)
    )).all():
        metrics[f'medchain_outbox_events{{status="{status}"}}'] = count
    oldest = _aware((await db.execute(
        select(func.min(OutboxEvent.created_at)).where(OutboxEvent.status.in_(["PENDING", "PROCESSING"]))
    )).scalar())
    metrics["medchain_outbox_oldest_undelivered_seconds"] = (now - oldest).total_seconds() if oldest else 0
    for status, count in (await db.execute(
        select(InboundMessage.status, func.count(InboundMessage.id)).group_by(InboundMessage.status)
    )).all():
        metrics[f'medchain_inbound_messages{{status="{status}"}}'] = count
    last_message = _aware((await db.execute(select(func.max(InboundMessage.received_at)))).scalar())
    metrics["medchain_inbound_last_message_age_seconds"] = (now - last_message).total_seconds() if last_message else -1
    metrics["medchain_break_glass_pending_review"] = (await db.execute(
        select(func.count(EmergencyAccessGrant.id)).where(EmergencyAccessGrant.review_status == "PENDING_REVIEW")
    )).scalar() or 0
    metrics["medchain_patient_merges_pending"] = (await db.execute(
        select(func.count(PatientMergeRequest.id)).where(PatientMergeRequest.status == "PENDING")
    )).scalar() or 0
    for severity, count in (await db.execute(
        select(OperationalAlert.severity, func.count(OperationalAlert.id))
        .where(OperationalAlert.status == "OPEN").group_by(OperationalAlert.severity)
    )).all():
        metrics[f'medchain_alerts_open{{severity="{severity}"}}'] = count
    metrics["medchain_event_subscribers"] = EventBus.subscriber_count()
    metrics["medchain_event_relay_active"] = 1 if EventRelay.active else 0
    return metrics


async def evaluate_conditions(db) -> List[AlertCondition]:
    from src.services.mongo import MongoDocumentService
    from src.services.neo4j_sync import GraphSyncService

    now = datetime.now(timezone.utc)
    conditions: List[AlertCondition] = []
    m = await collect_metrics(db)

    failed = m.get('medchain_outbox_events{status="FAILED"}', 0)
    if failed:
        conditions.append(AlertCondition("outbox.failed", "critical",
                                         f"{int(failed)} audit-evidence event(s) failed permanently and need operator action."))
    if m["medchain_outbox_oldest_undelivered_seconds"] > settings.OUTBOX_ALERT_AGE_SECONDS:
        minutes = int(m["medchain_outbox_oldest_undelivered_seconds"] // 60)
        conditions.append(AlertCondition("outbox.backlog", "warning",
                                         f"Audit evidence has been waiting {minutes} min for ledger delivery."))
    review = m.get('medchain_inbound_messages{status="NEEDS_REVIEW"}', 0)
    if review:
        conditions.append(AlertCondition("integration.review_backlog", "warning",
                                         f"{int(review)} inbound clinical message(s) are waiting for manual review."))
    if settings.INTEGRATION_SILENCE_ALERT_MINUTES > 0 and settings.integration_key_hashes:
        age = m["medchain_inbound_last_message_age_seconds"]
        if age < 0 or age > settings.INTEGRATION_SILENCE_ALERT_MINUTES * 60:
            conditions.append(AlertCondition("integration.feed_silent", "critical",
                                             "No inbound HL7 messages within the configured silence window."))
    overdue = (await db.execute(
        select(func.count(EmergencyAccessGrant.id)).where(
            EmergencyAccessGrant.review_status == "PENDING_REVIEW",
            EmergencyAccessGrant.granted_at < now - timedelta(hours=settings.BREAK_GLASS_REVIEW_SLA_HOURS),
        )
    )).scalar() or 0
    if overdue:
        conditions.append(AlertCondition("compliance.break_glass_overdue", "warning",
                                         f"{overdue} break-the-glass access(es) exceeded the review deadline."))
    if m["medchain_patient_merges_pending"]:
        conditions.append(AlertCondition("integration.merge_pending", "info",
                                         f"{int(m['medchain_patient_merges_pending'])} patient merge request(s) await approval."))
    mongo = await MongoDocumentService.is_healthy()
    if mongo.get("status") != "up":
        conditions.append(AlertCondition("store.documents_down", "critical", "The clinical document store is unavailable."))
    graph = await GraphSyncService.get_status_async()
    if graph.get("status") in ("SYNC_FAILED", "STALE", "UNREACHABLE"):
        conditions.append(AlertCondition("graph.unhealthy", "warning", f"Graph projection status: {graph['status']}."))
    return conditions


async def _notify(alert: OperationalAlert, transition: str) -> bool:
    if not settings.ALERT_WEBHOOK_URL:
        return False
    payload = {
        "text": f"[MedChain {alert.severity.upper()}] {transition}: {alert.summary}",
        "alert_key": alert.alert_key, "severity": alert.severity, "status": alert.status,
        "first_seen_at": alert.first_seen_at.isoformat() if alert.first_seen_at else None,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(settings.ALERT_WEBHOOK_URL, json=payload)
            response.raise_for_status()
        return True
    except Exception as exc:
        logger.warning("Alert webhook delivery failed for %s: %s", alert.alert_key, exc)
        return False


async def run_evaluation() -> Dict[str, int]:
    """Evaluate conditions and reconcile the alert table. Returns counts of transitions."""
    summary = {"opened": 0, "resolved": 0, "open": 0, "skipped_not_leader": 0}
    leader = None
    try:
        if not database.is_fallback_active:
            leader = await database.async_engine.connect()
            if not (await leader.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _LOCK_KEY})).scalar():
                summary["skipped_not_leader"] = 1
                return summary
        async with database.AsyncSessionLocal() as db:
            now = datetime.now(timezone.utc)
            conditions = {c.key: c for c in await evaluate_conditions(db)}
            open_alerts = {a.alert_key: a for a in (await db.execute(
                select(OperationalAlert).where(OperationalAlert.status == "OPEN")
            )).scalars().all()}
            transitions = []
            for key, condition in conditions.items():
                alert = open_alerts.get(key)
                if alert is None:
                    alert = OperationalAlert(alert_key=key, severity=condition.severity, summary=condition.summary,
                                             status="OPEN", first_seen_at=now, last_seen_at=now)
                    db.add(alert)
                    transitions.append((alert, "OPENED"))
                    summary["opened"] += 1
                else:
                    alert.last_seen_at, alert.summary, alert.severity = now, condition.summary, condition.severity
            for key, alert in open_alerts.items():
                if key not in conditions:
                    alert.status, alert.resolved_at = "RESOLVED", now
                    transitions.append((alert, "RESOLVED"))
                    summary["resolved"] += 1
            summary["open"] = len(conditions)
            await db.commit()
            for alert, transition in transitions:
                if await _notify(alert, transition):
                    alert.notified_at = datetime.now(timezone.utc)
            await db.commit()
        return summary
    finally:
        if leader is not None:
            try:
                await leader.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _LOCK_KEY})
            finally:
                await leader.close()


class Monitor:
    _task: Optional[asyncio.Task] = None

    @classmethod
    async def _loop(cls) -> None:
        while True:
            try:
                await run_evaluation()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Monitoring evaluation failed.")
            await asyncio.sleep(settings.MONITOR_INTERVAL_SECONDS)

    @classmethod
    def start(cls) -> None:
        if settings.MONITOR_ENABLED and cls._task is None:
            cls._task = asyncio.create_task(cls._loop(), name="medchain-monitor")

    @classmethod
    async def stop(cls) -> None:
        if cls._task is not None:
            cls._task.cancel()
            try:
                await cls._task
            except asyncio.CancelledError:
                pass
            cls._task = None


def render_prometheus(metrics: Dict[str, float]) -> str:
    lines = []
    seen = set()
    for name, value in sorted(metrics.items()):
        base = name.split("{", 1)[0]
        if base not in seen:
            lines.append(f"# TYPE {base} gauge")
            seen.add(base)
        lines.append(f"{name} {float(value)}")
    return "\n".join(lines) + "\n"
