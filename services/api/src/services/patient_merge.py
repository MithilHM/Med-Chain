"""Approved duplicate-record merges.

A merge moves the retiring record's clinical, consent, coverage, and identity rows to the
surviving record in one transaction, then marks the retiring record MERGED (kept read-only,
pointing at the survivor). Audit history (access events, inbound-message ledger, cohort
results) is deliberately left untouched so it still shows what happened under which record.
"""
from datetime import datetime, timezone
from typing import Dict

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import (
    AccessRequest, AppUser, CareTeamAssignment, Consent, EmergencyAccessGrant, InsurancePolicy, MedicalDocument,
    ObservedAdverseEvent, Patient, PatientIdentifier, PatientMergeRequest, Visit,
)

_MOVED_TABLES = (
    ("visits", Visit), ("documents", MedicalDocument), ("adverse_events", ObservedAdverseEvent),
    ("insurance_policies", InsurancePolicy), ("consents", Consent), ("access_requests", AccessRequest),
    ("identifiers", PatientIdentifier), ("care_team", CareTeamAssignment), ("emergency_grants", EmergencyAccessGrant),
)


class MergeError(Exception):
    pass


async def approve_merge(db: AsyncSession, request: PatientMergeRequest, actor: AppUser, note: str | None) -> Dict[str, int]:
    if request.status != "PENDING":
        raise MergeError("This merge request was already decided.")
    if request.requested_by and request.requested_by == actor.id:
        raise MergeError("The requester cannot approve their own merge.")
    surviving = await db.get(Patient, request.surviving_patient_id, with_for_update=True)
    retiring = await db.get(Patient, request.retiring_patient_id, with_for_update=True)
    if surviving is None or retiring is None:
        raise MergeError("A patient in this request no longer exists.")
    if surviving.record_status != "ACTIVE" or retiring.record_status != "ACTIVE":
        raise MergeError("Both records must be active to merge.")
    if surviving.date_of_birth != retiring.date_of_birth:
        raise MergeError("Dates of birth differ; correct the demographics in the source system before merging.")

    moved: Dict[str, int] = {}
    for label, model in _MOVED_TABLES:
        result = await db.execute(
            update(model).where(model.patient_id == retiring.id).values(patient_id=surviving.id)
        )
        moved[label] = result.rowcount or 0

    if retiring.user_id:
        if surviving.user_id is None:
            portal_user_id = retiring.user_id
            retiring.user_id = None
            await db.flush()  # free the unique user_id before assigning it to the survivor
            surviving.user_id = portal_user_id
        else:
            retiring.user_id = None  # the surviving record keeps its portal account
            moved["portal_accounts_unlinked"] = 1
    if not surviving.name_encrypted and retiring.name_parts:
        parts = retiring.name_parts
        surviving.set_name(parts.get("given"), parts.get("family"))

    retiring.record_status = "MERGED"
    retiring.merged_into_id = surviving.id
    request.status = "APPROVED"
    request.decided_by = actor.id
    request.decided_at = datetime.now(timezone.utc)
    request.decision_note = note
    request.moved_counts = moved
    return moved
