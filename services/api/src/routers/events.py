"""Server-Sent Events stream of real-time clinical events for authorized users."""
import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src import database
from src.database import get_db
from src.models import AppUser, Doctor, Patient
from src.routers.deps import doctor_accessible_patient_ids, get_current_user, security
from src.services.auth import decode_access_token, get_active_session
from src.services.events import EventBus, Subscriber

router = APIRouter(prefix="/events", tags=["Real-time Events"])

HEARTBEAT_SECONDS = 15
REVALIDATE_SECONDS = 30


async def _refresh_authorization(subscriber: Subscriber, user_id: str, token_jti: Optional[str]) -> bool:
    """Re-check the session and refresh the doctor's patient set. False ends the stream."""
    async with database.AsyncSessionLocal() as db:
        session = await get_active_session(db, token_jti) if token_jti else None
        user = await db.get(AppUser, user_id)
        if session is None or user is None or not user.is_active:
            return False
        if user.role == "doctor":
            doctor = (await db.execute(select(Doctor).where(Doctor.user_id == user.id))).scalar_one_or_none()
            subscriber.authorized_patient_ids = await doctor_accessible_patient_ids(db, doctor, user) if doctor else set()
    return True


@router.get("/stream")
async def stream_events(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    current_user: AppUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stream `text/event-stream` events. Payloads carry IDs and flags only; fetch details via the API."""
    if current_user.role not in ("admin", "doctor", "patient"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Real-time clinical events are limited to care roles.")

    token = credentials.credentials if credentials else request.cookies.get("medchain_session")
    token_jti = (decode_access_token(token) or {}).get("jti") if token else None

    subscriber = Subscriber(user_id=current_user.id, role=current_user.role)
    if current_user.role == "patient":
        patient = (await db.execute(select(Patient).where(Patient.user_id == current_user.id))).scalar_one_or_none()
        subscriber.own_patient_id = patient.id if patient else None
    elif current_user.role == "doctor":
        doctor = (await db.execute(select(Doctor).where(Doctor.user_id == current_user.id))).scalar_one_or_none()
        subscriber.authorized_patient_ids = (
            await doctor_accessible_patient_ids(db, doctor, current_user) if doctor else set()
        )
    await db.commit()  # return the pooled connection; the stream may stay open for a long time
    EventBus.subscribe(subscriber)

    async def event_source():
        loop = asyncio.get_running_loop()
        last_check = loop.time()
        try:
            yield "retry: 5000\n\n"
            while True:
                if await request.is_disconnected():
                    break
                if loop.time() - last_check >= REVALIDATE_SECONDS:
                    last_check = loop.time()
                    if not await _refresh_authorization(subscriber, current_user.id, token_jti):
                        yield "event: session_expired\ndata: {}\n\n"
                        break
                try:
                    event = await asyncio.wait_for(subscriber.queue.get(), timeout=HEARTBEAT_SECONDS)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield f"id: {event.id}\nevent: {event.event_type}\ndata: {json.dumps(event.as_payload())}\n\n"
        finally:
            EventBus.unsubscribe(subscriber)

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-store", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
