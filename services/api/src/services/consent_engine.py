import logging
from typing import Tuple, Optional, Dict, Any, List
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models import (
    AppUser, ResearchProject, Consent, AccessEvent, Patient
)
from src.request_context import current_request_id
from src.services.outbox import OutboxService

logger = logging.getLogger("medchain.consent_engine")

class ConsentPolicyEngine:
    """Deny-by-default research authorization.

    Concurrency contract (closes the revoke-during-query race):
    - On GRANTED, the matching consent rows are read with FOR SHARE and the transaction is left
      OPEN. The caller must run its data query in the same session and then commit.
    - Revocation reads the consent row FOR UPDATE, so it blocks until in-flight authorized queries
      commit, and any query that starts afterwards sees the revocation.
    - On DENIED, the decision is committed immediately so it survives the 403 response.
    SQLite (development only) ignores row locks; PostgreSQL enforces them.
    """

    @staticmethod
    def _consent_is_current(consent: Consent, now: datetime) -> tuple[bool, str]:
        valid_from = consent.valid_from
        valid_until = consent.valid_until
        if valid_from.tzinfo is None:
            valid_from = valid_from.replace(tzinfo=timezone.utc)
        if valid_until.tzinfo is None:
            valid_until = valid_until.replace(tzinfo=timezone.utc)
        if valid_from > now:
            return False, "NOT_YET_VALID"
        if valid_until <= now:
            return False, "EXPIRED"
        return True, "ACTIVE"

    @staticmethod
    async def evaluate_research_access(
        db: AsyncSession,
        actor: AppUser,
        project_id: str,
        requested_scope: str, # aggregate_diagnoses, medication_history, lab_summaries, deidentified_cohort
        target_patient_id: Optional[str] = None
    ) -> Tuple[bool, str, List[Consent]]:
        """
        Deny-by-default evaluation:
        1. Actor must be active and have role 'researcher' or 'admin'.
        2. Project must exist and be ACTIVE.
        3. For target_patient_id: must have an active Consent record where:
           - status == 'GRANTED'
           - revoked_at IS NULL
           - valid_until > now (UTC)
           - requested_scope in consent.scope_json
        4. Logs access attempt (GRANTED or DENIED) to access_event table.
        """
        now = datetime.now(timezone.utc)
        target_patient = None
        if target_patient_id:
            from sqlalchemy import or_
            target_patient = (await db.execute(
                select(Patient).where(
                    or_(Patient.id == target_patient_id, Patient.display_code == target_patient_id)
                )
            )).scalar_one_or_none()
        target_event_patient_id = target_patient.id if target_patient else None

        # 1. Actor check
        if not actor.is_active or actor.role not in ("researcher", "admin"):
            reason = "Actor inactive or does not possess research authorization role."
            await ConsentPolicyEngine._log_access(
                db, actor.id, target_event_patient_id, "RESEARCH_QUERY", project_id, "DENIED", reason
            )
            return False, reason, []

        # 2. Project check
        project = (await db.execute(select(ResearchProject).where(ResearchProject.id == project_id))).scalar_one_or_none()
        if (
            not project
            or project.status != "ACTIVE"
            or (actor.role == "researcher" and project.created_by != actor.id)
        ):
            reason = "Research project was not found, is inactive, or is not owned by this researcher."
            await ConsentPolicyEngine._log_access(
                db, actor.id, target_event_patient_id, "RESEARCH_QUERY", project_id, "DENIED", reason
            )
            return False, reason, []

        # 3. If patient-specific query or cohort evaluation
        if target_patient_id:
            pt = target_patient
            if not pt:
                reason = "Target patient was not found."
                await ConsentPolicyEngine._log_access(
                    db, actor.id, None, "RESEARCH_QUERY", project_id, "DENIED", reason
                )
                return False, reason, []

            patient_consents = (await db.execute(
                select(Consent).where(
                    Consent.patient_id == pt.id,
                    Consent.requester_project_id == project_id,
                    Consent.status == "GRANTED",
                    Consent.revoked_at.is_(None),
                ).with_for_update(read=True)
            )).scalars().all()

            if not patient_consents:
                reason = "No active consent granted by patient for this research project."
                await ConsentPolicyEngine._log_access(
                    db, actor.id, pt.id, "RESEARCH_QUERY", project_id, "DENIED", reason
                )
                return False, reason, []

            consent = None
            saw_unexpired = False
            saw_future = False
            for candidate in patient_consents:
                is_current, window_status = ConsentPolicyEngine._consent_is_current(candidate, now)
                if window_status == "NOT_YET_VALID":
                    saw_future = True
                    continue
                if not is_current:
                    continue
                saw_unexpired = True
                scopes = candidate.scope_json if isinstance(candidate.scope_json, list) else candidate.scope_json.get("scopes", [])
                if requested_scope in scopes or "*" in scopes:
                    consent = candidate
                    break

            if not consent:
                if not saw_unexpired:
                    reason = (
                        "Patient data sharing consent has not started yet."
                        if saw_future
                        else "Patient data sharing consent has expired."
                    )
                else:
                    reason = f"Requested scope '{requested_scope}' is not included in the patient's active consent scopes."
                await ConsentPolicyEngine._log_access(
                    db, actor.id, pt.id, "RESEARCH_QUERY", project_id, "DENIED", reason
                )
                return False, reason, []

            # Access granted
            await ConsentPolicyEngine._log_access(
                db, actor.id, pt.id, "RESEARCH_QUERY", project_id, "GRANTED", "CONSENT_ACTIVE_AND_VERIFIED"
            )
            return True, "Consent verified successfully.", [consent]

        # 4. Project-level aggregate query across all consented patients
        active_consents = (await db.execute(
            select(Consent).where(
                Consent.requester_project_id == project_id,
                Consent.status == "GRANTED",
                Consent.revoked_at.is_(None)
            ).with_for_update(read=True)
        )).scalars().all()

        valid_consents = []
        for c in active_consents:
            is_current, _ = ConsentPolicyEngine._consent_is_current(c, now)
            if is_current:
                scopes = c.scope_json if isinstance(c.scope_json, list) else c.scope_json.get("scopes", [])
                if requested_scope in scopes or "*" in scopes:
                    valid_consents.append(c)

        if not valid_consents:
            reason = "No active patient consents exist for this project covering the requested scope."
            await ConsentPolicyEngine._log_access(
                db, actor.id, None, "RESEARCH_AGGREGATE_QUERY", project_id, "DENIED", reason
            )
            return False, reason, []

        authorized_patient_count = len({consent.patient_id for consent in valid_consents})
        await ConsentPolicyEngine._log_access(
            db, actor.id, None, "RESEARCH_AGGREGATE_QUERY", project_id, "GRANTED", f"{authorized_patient_count}_PATIENTS_ACTIVE"
        )
        return True, f"Authorized across {authorized_patient_count} consenting patients.", valid_consents

    @staticmethod
    async def _log_access(
        db: AsyncSession,
        actor_id: str,
        patient_id: Optional[str],
        action: str,
        resource_ref: str,
        decision: str,
        reason: str
    ):
        event = AccessEvent(
            actor_user_id=actor_id,
            patient_id=patient_id,
            resource_type="RESEARCH_DATA",
            resource_reference=resource_ref,
            action=action,
            decision=decision,
            reason_code=reason[:100],
            request_id=current_request_id(),
        )
        db.add(event)
        await db.flush()
        await OutboxService.enqueue_access_event(db, event)
        if decision == "DENIED":
            await db.commit()
        # GRANTED: keep the transaction (and FOR SHARE consent locks) open for the caller's query.
