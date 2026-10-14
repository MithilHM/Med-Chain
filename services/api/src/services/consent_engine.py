import logging
from typing import Tuple, Optional, Dict, Any, List
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models import (
    AppUser, ResearchProject, Consent, AccessEvent, Patient
)
from src.services.blockchain import BlockchainService

logger = logging.getLogger("medchain.consent_engine")

class ConsentPolicyEngine:
    @staticmethod
    async def evaluate_research_access(
        db: AsyncSession,
        actor: AppUser,
        project_id: str,
        requested_scope: str, # aggregate_diagnoses, medication_history, lab_summaries, deidentified_cohort
        target_patient_id: Optional[str] = None
    ) -> Tuple[bool, str, Optional[Consent]]:
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

        # 1. Actor check
        if not actor.is_active or actor.role not in ("researcher", "admin"):
            reason = "Actor inactive or does not possess research authorization role."
            await ConsentPolicyEngine._log_access(
                db, actor.id, target_patient_id, "RESEARCH_QUERY", project_id, "DENIED", reason
            )
            return False, reason, None

        # 2. Project check
        project = (await db.execute(select(ResearchProject).where(ResearchProject.id == project_id))).scalar_one_or_none()
        if not project or project.status != "ACTIVE":
            reason = f"Research project {project_id} not found or inactive."
            await ConsentPolicyEngine._log_access(
                db, actor.id, target_patient_id, "RESEARCH_QUERY", project_id, "DENIED", reason
            )
            return False, reason, None

        # 3. If patient-specific query or cohort evaluation
        if target_patient_id:
            from sqlalchemy import or_
            pt = (await db.execute(select(Patient).where(or_(Patient.id == target_patient_id, Patient.display_code == target_patient_id)))).scalar_one_or_none()
            effective_patient_id = pt.id if pt else target_patient_id

            consent = (await db.execute(
                select(Consent).where(
                    Consent.patient_id == effective_patient_id,
                    Consent.requester_project_id == project_id,
                    Consent.status == "GRANTED"
                )
            )).scalar_one_or_none()

            if not consent:
                reason = "No active consent granted by patient for this research project."
                await ConsentPolicyEngine._log_access(
                    db, actor.id, target_patient_id, "RESEARCH_QUERY", project_id, "DENIED", reason
                )
                return False, reason, None

            if consent.revoked_at is not None:
                reason = "Patient has explicitly revoked data sharing consent."
                await ConsentPolicyEngine._log_access(
                    db, actor.id, target_patient_id, "RESEARCH_QUERY", project_id, "DENIED", reason
                )
                return False, reason, None

            # Handle datetime comparison
            valid_until = consent.valid_until
            if valid_until.tzinfo is None:
                valid_until = valid_until.replace(tzinfo=timezone.utc)
            if valid_until <= now:
                reason = "Patient data sharing consent has expired."
                await ConsentPolicyEngine._log_access(
                    db, actor.id, target_patient_id, "RESEARCH_QUERY", project_id, "DENIED", reason
                )
                return False, reason, None

            # Check scope
            scopes = consent.scope_json if isinstance(consent.scope_json, list) else consent.scope_json.get("scopes", [])
            if requested_scope not in scopes and "*" not in scopes:
                reason = f"Requested scope '{requested_scope}' not included in patient's granted consent scopes ({scopes})."
                await ConsentPolicyEngine._log_access(
                    db, actor.id, target_patient_id, "RESEARCH_QUERY", project_id, "DENIED", reason
                )
                return False, reason, None

            # Access granted
            await ConsentPolicyEngine._log_access(
                db, actor.id, target_patient_id, "RESEARCH_QUERY", project_id, "GRANTED", "CONSENT_ACTIVE_AND_VERIFIED"
            )
            return True, "Consent verified successfully.", consent

        # 4. Project-level aggregate query across all consented patients
        active_consents = (await db.execute(
            select(Consent).where(
                Consent.requester_project_id == project_id,
                Consent.status == "GRANTED",
                Consent.revoked_at.is_(None)
            )
        )).scalars().all()

        valid_consents = []
        for c in active_consents:
            v_until = c.valid_until if c.valid_until.tzinfo else c.valid_until.replace(tzinfo=timezone.utc)
            if v_until > now:
                scopes = c.scope_json if isinstance(c.scope_json, list) else c.scope_json.get("scopes", [])
                if requested_scope in scopes or "*" in scopes:
                    valid_consents.append(c)

        if not valid_consents:
            reason = "No active patient consents exist for this project covering the requested scope."
            await ConsentPolicyEngine._log_access(
                db, actor.id, None, "RESEARCH_AGGREGATE_QUERY", project_id, "DENIED", reason
            )
            return False, reason, None

        await ConsentPolicyEngine._log_access(
            db, actor.id, None, "RESEARCH_AGGREGATE_QUERY", project_id, "GRANTED", f"{len(valid_consents)}_CONSENTS_ACTIVE"
        )
        return True, f"Authorized across {len(valid_consents)} consenting patients.", None

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
            reason_code=reason
        )
        db.add(event)
        await db.commit()

        # Try to mirror access log to blockchain (asynchronously, with unanchored fallback)
        try:
            status, tx_hash = await BlockchainService.log_access_event(
                event.id, actor_id, resource_ref, action, decision
            )
            if status == "CONFIRMED":
                event.chain_tx_hash = tx_hash
                await db.commit()
        except Exception as e:
            logger.warning(f"Failed to anchor access event to blockchain: {e}")
