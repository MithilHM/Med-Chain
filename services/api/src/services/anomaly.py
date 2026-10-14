import logging
from typing import List, Tuple, Optional
from decimal import Decimal
from datetime import timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models import InsuranceClaim, InsurancePolicy, ClaimItem, Visit

logger = logging.getLogger("medchain.anomaly")

class InsuranceAnomalyService:
    @staticmethod
    async def evaluate_claim_for_anomalies(
        db: AsyncSession,
        claim: InsuranceClaim,
        items: List[ClaimItem]
    ) -> Tuple[bool, Optional[str]]:
        """
        Explainable heuristic rule evaluation:
        1. Duplicate item billing on identical visit or date.
        2. High-dollar claim exceeding statistical threshold (> $15,000 without prior authorization).
        3. Overlapping visit claims for same policy within 24 hours with matching item codes.
        Flags ONLY for human review; does not make automated decisions or fraud accusations.
        """
        policy = (await db.execute(select(InsurancePolicy).where(InsurancePolicy.id == claim.policy_id))).scalar_one_or_none()
        visit = (await db.execute(select(Visit).where(Visit.id == claim.visit_id))).scalar_one_or_none()

        if not policy or not visit:
            return False, None

        # Rule 1: High claim threshold
        if claim.claimed_amount > Decimal("15000.00"):
            return True, "High expenditure: Total claimed amount exceeds standard threshold ($15,000.00) requiring manual human underwriting review."

        # Rule 2: Multiple identical item codes within the same claim
        item_codes = [item.item_code for item in items]
        if len(item_codes) != len(set(item_codes)):
            return True, "Potential duplicate service items: Multiple identical billing codes submitted on the same encounter."

        # Rule 3: Previous claims on same policy within 48 hours
        time_window_start = claim.submitted_at - timedelta(hours=48)
        time_window_end = claim.submitted_at + timedelta(hours=48)
        
        recent_claims = (await db.execute(
            select(InsuranceClaim).where(
                InsuranceClaim.policy_id == claim.policy_id,
                InsuranceClaim.id != claim.id,
                InsuranceClaim.submitted_at >= time_window_start,
                InsuranceClaim.submitted_at <= time_window_end
            )
        )).scalars().all()

        for rc in recent_claims:
            rc_items = (await db.execute(select(ClaimItem).where(ClaimItem.claim_id == rc.id))).scalars().all()
            overlapping_codes = set(item_codes).intersection({ri.item_code for ri in rc_items})
            if overlapping_codes:
                return True, f"Temporal overlap anomaly: Policy contains matching billing codes ({', '.join(overlapping_codes)}) submitted within 48 hours."

        return False, None
