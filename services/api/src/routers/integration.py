"""Real-time clinical integration endpoints (HL7 v2 over HTTPS) and the manual review queue."""
import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.database import get_db
from src.integration.hl7_processor import process_hl7_message, reprocess_message
from src.models import AppUser, InboundMessage, Patient, PatientMergeRequest
from src.routers.deps import get_current_user, record_access_event, require_role, security
from src.services.crypto import constant_time_lookup, sha256_hex
from src.services.events import ClinicalEvent, EventBus
from src.services.patient_merge import MergeError, approve_merge

router = APIRouter(prefix="/integration", tags=["Real-time Clinical Integration"])

HL7_MEDIA_TYPE = "x-application/hl7-v2+er7"
MAX_MESSAGE_BYTES = 1_000_000


async def _integration_source(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> str:
    """Authenticate an interface engine by API key, or an admin by session (manual uploads)."""
    api_key = request.headers.get("x-integration-key")
    if api_key:
        source = constant_time_lookup(sha256_hex(api_key), settings.integration_key_hashes)
        if source is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid integration key.")
        return source
    user = await get_current_user(request, credentials, db)
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Integration feeds require an integration key.")
    return f"admin-upload:{user.id[:8]}"


@router.post("/hl7v2")
async def receive_hl7v2(
    request: Request,
    response_format: str = Query(default="hl7", alias="format", pattern="^(hl7|json)$"),
    source_system: str = Depends(_integration_source),
):
    """Accept one HL7 v2 message (ER7 text body) and return an HL7 ACK.

    Interface engines should POST each message and act on MSA-1: AA = done, AR = fix and resend,
    AE = retry later. Add `?format=json` for a JSON summary (useful for testing).
    """
    body = await request.body()
    if len(body) > MAX_MESSAGE_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="HL7 message is too large.")
    try:
        raw = body.decode("utf-8")
    except UnicodeDecodeError:
        raw = body.decode("latin-1")
    outcome = await process_hl7_message(raw, source_system)
    headers = {"X-MedChain-Ack-Code": outcome.ack_code, "X-MedChain-Message-Status": outcome.status}
    if outcome.message_id:
        headers["X-MedChain-Message-Id"] = outcome.message_id
    if response_format == "json":
        return Response(
            content=json.dumps({
                "ack_code": outcome.ack_code,
                "status": outcome.status,
                "detail": outcome.detail,
                "message_id": outcome.message_id,
                "patient_id": outcome.patient_id,
                "duplicate": outcome.duplicate,
                "warnings": outcome.warnings,
                "ack": outcome.ack,
            }),
            media_type="application/json",
            headers=headers,
        )
    return Response(content=outcome.ack, media_type=HL7_MEDIA_TYPE, headers=headers)


@router.get("/messages")
async def list_inbound_messages(
    message_status: Optional[str] = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=500),
    current_user: AppUser = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db),
):
    """Ledger metadata for operators. Raw payloads (PHI) are never returned here."""
    query = select(InboundMessage).order_by(InboundMessage.received_at.desc()).limit(limit)
    if message_status:
        query = query.where(InboundMessage.status == message_status.upper())
    rows = (await db.execute(query)).scalars().all()
    return [
        {
            "id": row.id,
            "source_system": row.source_system,
            "message_control_id": row.message_control_id,
            "message_type": row.message_type,
            "status": row.status,
            "error_detail": row.error_detail,
            "patient_id": row.patient_id,
            "attempt_count": row.attempt_count,
            "received_at": row.received_at,
            "processed_at": row.processed_at,
        }
        for row in rows
    ]


@router.get("/status")
async def integration_status(
    current_user: AppUser = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db),
):
    counts = dict((await db.execute(
        select(InboundMessage.status, func.count(InboundMessage.id)).group_by(InboundMessage.status)
    )).all())
    last_received = (await db.execute(select(func.max(InboundMessage.received_at)))).scalar()
    return {
        "counts": {name: counts.get(name, 0) for name in ("RECEIVED", "PROCESSED", "NEEDS_REVIEW", "REJECTED")},
        "last_message_received_at": last_received,
        "configured_sources": sorted(set(settings.integration_key_hashes.values())),
        "mllp_listener": f"{settings.MLLP_HOST}:{settings.MLLP_PORT} (run `python -m src.integration.mllp_server`)",
    }


class MergeProposal(BaseModel):
    surviving_patient_id: str
    retiring_patient_id: str
    reason: str = Field(..., min_length=5, max_length=500)


class MergeDecision(BaseModel):
    note: Optional[str] = Field(default=None, max_length=2000)


def _merge_out(request: PatientMergeRequest) -> dict:
    return {
        "id": request.id, "surviving_patient_id": request.surviving_patient_id,
        "retiring_patient_id": request.retiring_patient_id, "reason": request.reason, "status": request.status,
        "source_message_id": request.source_message_id, "requested_by": request.requested_by,
        "decided_by": request.decided_by, "decided_at": request.decided_at, "decision_note": request.decision_note,
        "moved_counts": request.moved_counts, "created_at": request.created_at,
    }


@router.get("/merges")
async def list_merge_requests(
    merge_status: Optional[str] = Query(default="PENDING", alias="status"),
    current_user: AppUser = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db),
):
    query = select(PatientMergeRequest).order_by(PatientMergeRequest.created_at.desc()).limit(200)
    if merge_status:
        query = query.where(PatientMergeRequest.status == merge_status.upper())
    return [_merge_out(r) for r in (await db.execute(query)).scalars().all()]


@router.post("/merges")
async def propose_merge(
    proposal: MergeProposal,
    current_user: AppUser = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db),
):
    if proposal.surviving_patient_id == proposal.retiring_patient_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Choose two different records.")
    for patient_id in (proposal.surviving_patient_id, proposal.retiring_patient_id):
        if await db.get(Patient, patient_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")
    request = PatientMergeRequest(
        surviving_patient_id=proposal.surviving_patient_id, retiring_patient_id=proposal.retiring_patient_id,
        reason=proposal.reason, requested_by=current_user.id,
    )
    db.add(request)
    await db.flush()
    await record_access_event(db, current_user.id, proposal.retiring_patient_id, "PATIENT_MERGE", request.id,
                              "PROPOSE_MERGE", "GRANTED", "AWAITING_SECOND_APPROVER")
    return _merge_out(request)


@router.post("/merges/{request_id}/approve")
async def approve_merge_request(
    request_id: str,
    decision: MergeDecision,
    current_user: AppUser = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db),
):
    request = await db.get(PatientMergeRequest, request_id, with_for_update=True)
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Merge request not found.")
    try:
        moved = await approve_merge(db, request, current_user, decision.note)
    except MergeError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if request.source_message_id:
        message = await db.get(InboundMessage, request.source_message_id)
        if message is not None:
            message.status, message.patient_id = "PROCESSED", request.surviving_patient_id
            message.error_detail = f"Merge approved by administrator ({request.id})."
    await record_access_event(db, current_user.id, request.surviving_patient_id, "PATIENT_MERGE", request.id,
                              "APPROVE_MERGE", "GRANTED", "RECORDS_MERGED", commit=False)
    await db.commit()
    EventBus.publish(ClinicalEvent("patient.merged", request.surviving_patient_id,
                                   {"retired_patient_id": request.retiring_patient_id}))
    return {**_merge_out(request), "moved_counts": moved}


@router.post("/merges/{request_id}/reject")
async def reject_merge_request(
    request_id: str,
    decision: MergeDecision,
    current_user: AppUser = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db),
):
    request = await db.get(PatientMergeRequest, request_id, with_for_update=True)
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Merge request not found.")
    if request.status != "PENDING":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This merge request was already decided.")
    request.status, request.decided_by = "REJECTED", current_user.id
    request.decided_at, request.decision_note = datetime.now(timezone.utc), decision.note
    if request.source_message_id:
        message = await db.get(InboundMessage, request.source_message_id)
        if message is not None:
            message.status, message.error_detail = "REJECTED", "Merge rejected by administrator."
    await record_access_event(db, current_user.id, request.retiring_patient_id, "PATIENT_MERGE", request.id,
                              "REJECT_MERGE", "GRANTED", "MERGE_REJECTED")
    return _merge_out(request)


@router.post("/messages/{message_id}/reprocess")
async def reprocess_inbound_message(
    message_id: str,
    current_user: AppUser = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db),
):
    try:
        outcome = await reprocess_message(message_id)
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inbound message not found.")
    await record_access_event(
        db, current_user.id, outcome.patient_id, "INBOUND_MESSAGE", message_id, "REPROCESS_HL7_MESSAGE",
        "GRANTED", f"RESULT_{outcome.status}",
    )
    return {"status": outcome.status, "ack_code": outcome.ack_code, "detail": outcome.detail, "warnings": outcome.warnings}
