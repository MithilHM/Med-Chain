"""Real-time clinical event bus (feeds the Server-Sent Events stream).

Rules:
- Publish only AFTER the database transaction that created the fact has committed.
- Events carry identifiers and minimal metadata, never narrative text or clinical values;
  clients fetch details through the normal access-checked API, which writes an audit event.
- Each subscriber receives only events for patients it is authorized to see.

Fan-out: with PostgreSQL (EVENT_BUS_BACKEND=auto) every process — API replicas and the MLLP
listener — publishes with NOTIFY and receives with LISTEN, so an HL7 result ingested by the MLLP
process reaches dashboards connected to any API replica. Without PostgreSQL, or while the relay
connection is down, delivery is in-process only.
"""
import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set

logger = logging.getLogger("medchain.events")

CHANNEL = "medchain_events"
_MAX_NOTIFY_BYTES = 7500  # PostgreSQL NOTIFY payloads are limited to 8000 bytes


@dataclass
class ClinicalEvent:
    event_type: str                      # e.g. lab_result.created, encounter.admitted, consent.revoked
    patient_id: Optional[str] = None     # None for operational (admin-only) events
    data: Dict[str, Any] = field(default_factory=dict)
    admin_only: bool = False
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    occurred_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def as_payload(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.event_type,
            "patient_id": self.patient_id,
            "occurred_at": self.occurred_at,
            "data": self.data,
        }

    def to_wire(self) -> str:
        return json.dumps({**self.as_payload(), "admin_only": self.admin_only}, separators=(",", ":"), default=str)

    @classmethod
    def from_wire(cls, raw: str) -> "ClinicalEvent":
        data = json.loads(raw)
        return cls(event_type=data["type"], patient_id=data.get("patient_id"), data=data.get("data") or {},
                   admin_only=bool(data.get("admin_only")), id=data["id"], occurred_at=data["occurred_at"])


@dataclass(eq=False)
class Subscriber:
    user_id: str
    role: str
    own_patient_id: Optional[str] = None
    authorized_patient_ids: Set[str] = field(default_factory=set)
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=500))

    def accepts(self, event: ClinicalEvent) -> bool:
        if self.role == "admin":
            return True
        if event.admin_only or event.patient_id is None:
            return False
        if self.role == "patient":
            return event.patient_id == self.own_patient_id
        if self.role == "doctor":
            return event.patient_id in self.authorized_patient_ids
        return False  # researchers and insurance analysts do not receive clinical events


class EventBus:
    _subscribers: Set[Subscriber] = set()

    @classmethod
    def subscribe(cls, subscriber: Subscriber) -> Subscriber:
        cls._subscribers.add(subscriber)
        return subscriber

    @classmethod
    def unsubscribe(cls, subscriber: Subscriber) -> None:
        cls._subscribers.discard(subscriber)

    @classmethod
    def subscriber_count(cls) -> int:
        return len(cls._subscribers)

    @classmethod
    def deliver_local(cls, event: ClinicalEvent) -> int:
        delivered = 0
        for subscriber in list(cls._subscribers):
            if not subscriber.accepts(event):
                continue
            if subscriber.queue.full():
                # Slow consumer: drop the oldest event rather than block producers.
                try:
                    subscriber.queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            subscriber.queue.put_nowait(event)
            delivered += 1
        return delivered

    @classmethod
    def publish(cls, event: ClinicalEvent) -> int:
        if EventRelay.active and EventRelay.enqueue(event):
            return 0  # delivered to every process (including this one) via LISTEN/NOTIFY
        return cls.deliver_local(event)


class EventRelay:
    """PostgreSQL LISTEN/NOTIFY fan-out across processes."""
    active: bool = False
    _outgoing: Optional[asyncio.Queue] = None
    _task: Optional[asyncio.Task] = None
    _engine = None

    @classmethod
    def enqueue(cls, event: ClinicalEvent) -> bool:
        wire = event.to_wire()
        if cls._outgoing is None or len(wire.encode("utf-8")) > _MAX_NOTIFY_BYTES:
            return False
        try:
            cls._outgoing.put_nowait(wire)
            return True
        except asyncio.QueueFull:
            return False

    @classmethod
    def _on_notification(cls, _connection, _pid, _channel, payload: str) -> None:
        try:
            EventBus.deliver_local(ClinicalEvent.from_wire(payload))
        except Exception:
            logger.exception("Discarding malformed event notification.")

    @classmethod
    async def _run(cls, engine) -> None:
        while True:
            sa_connection = None
            try:
                sa_connection = await engine.connect()
                raw = await sa_connection.get_raw_connection()
                pg = raw.driver_connection
                await pg.add_listener(CHANNEL, cls._on_notification)
                cls.active = True
                logger.info("Event relay listening on PostgreSQL channel %s.", CHANNEL)
                while True:
                    wire = await cls._outgoing.get()
                    await pg.execute("SELECT pg_notify($1, $2)", CHANNEL, wire)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Event relay connection lost (%s); delivering in-process until it reconnects.", exc)
            finally:
                cls.active = False
                if sa_connection is not None:
                    try:
                        await sa_connection.close()
                    except Exception:
                        pass
            # Anything queued while disconnected is still delivered to local subscribers.
            while cls._outgoing is not None and not cls._outgoing.empty():
                EventBus.deliver_local(ClinicalEvent.from_wire(cls._outgoing.get_nowait()))
            await asyncio.sleep(5)

    @classmethod
    def start(cls, engine) -> bool:
        from src.config import settings
        if settings.EVENT_BUS_BACKEND != "auto" or engine.dialect.name != "postgresql" or cls._task is not None:
            return False
        cls._engine = engine
        cls._outgoing = asyncio.Queue(maxsize=10000)
        cls._task = asyncio.create_task(cls._run(engine), name="medchain-event-relay")
        return True

    @classmethod
    async def stop(cls) -> None:
        if cls._task is not None:
            cls._task.cancel()
            try:
                await cls._task
            except asyncio.CancelledError:
                pass
        cls._task, cls._outgoing, cls.active = None, None, False
