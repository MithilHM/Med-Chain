from typing import List, Optional
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.models import (
    AppUser, InsuranceAnalyst, InsurancePolicy, InsuranceClaim, ClaimItem, InsuranceProvider, Visit, Diagnosis, Disease, Treatment
)
from src.schemas.insurance import (
    PolicyOut, ClaimOut, ClaimCreate, ClaimReviewRequest,
    ExpenditureSummaryOut, ClaimItemOut, AnomalyResolutionRequest,
)
from src.services.anomaly import InsuranceAnomalyService
from src.routers.deps import get_current_user, require_role, record_access_event

router = APIRouter(prefix="/insurance", tags=["Insurance Database & Analytics"])

async def _insurance_provider_scope(current_user: AppUser, db: AsyncSession) -> Optional[str]:
    if current_user.role != "insurance_analyst":
        return None
    provider_id = (await db.execute(
        select(InsuranceAnalyst.provider_id).where(InsuranceAnalyst.user_id == current_user.id)
    )).scalar_one_or_none()
    if not provider_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insurance analyst is not assigned to an insurance provider.",
        )
    return provider_id

async def _require_policy_provider_scope(policy: InsurancePolicy, current_user: AppUser, db: AsyncSession) -> None:
    provider_id = await _insurance_provider_scope(current_user, db)
    if provider_id and policy.provider_id != provider_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Insurance record not found.")

async def _require_claim_provider_scope(claim: InsuranceClaim, current_user: AppUser, db: AsyncSession) -> InsurancePolicy:
    policy = (await db.execute(select(InsurancePolicy).where(InsurancePolicy.id == claim.policy_id))).scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found.")
    await _require_policy_provider_scope(policy, current_user, db)
    return policy

@router.get("/policies", response_model=List[PolicyOut])
async def list_policies(
    patient_id: Optional[str] = None,
    current_user: AppUser = Depends(require_role(["insurance_analyst", "patient", "admin"])),
    db: AsyncSession = Depends(get_db)
):
    query = select(InsurancePolicy)
    provider_id = await _insurance_provider_scope(current_user, db)
    if provider_id:
        query = query.where(InsurancePolicy.provider_id == provider_id)
    if current_user.role == "patient":
        from src.models import Patient
        pt = (await db.execute(select(Patient).where(Patient.user_id == current_user.id))).scalar_one_or_none()
        if not pt:
            return []
        query = query.where(InsurancePolicy.patient_id == pt.id)
    elif patient_id:
        query = query.where(InsurancePolicy.patient_id == patient_id)

    policies = (await db.execute(query)).scalars().all()
    out = []
    for p in policies:
        await record_access_event(
            db, current_user.id, p.patient_id, "INSURANCE_POLICY", f"policy:{p.id}", "READ_INSURANCE_POLICY"
        )
        prov = (await db.execute(select(InsuranceProvider).where(InsuranceProvider.id == p.provider_id))).scalar_one_or_none()
        out.append(PolicyOut(
            id=p.id,
            patient_id=p.patient_id,
            provider_name=prov.name if prov else "",
            policy_reference=p.policy_reference,
            coverage_type=p.coverage_type,
            valid_from=p.valid_from,
            valid_until=p.valid_until,
            status=p.status
        ))
    return out

@router.get("/claims", response_model=List[ClaimOut])
async def list_claims(
    flagged_only: bool = False,
    current_user: AppUser = Depends(require_role(["insurance_analyst", "patient", "admin"])),
    db: AsyncSession = Depends(get_db)
):
    query = select(InsuranceClaim)
    provider_id = await _insurance_provider_scope(current_user, db)
    if current_user.role == "patient":
        from src.models import Patient
        pt = (await db.execute(select(Patient).where(Patient.user_id == current_user.id))).scalar_one_or_none()
        if not pt:
            return []
        # Join with policy to filter by patient
        query = query.join(InsurancePolicy).where(InsurancePolicy.patient_id == pt.id)
    elif provider_id:
        query = query.join(InsurancePolicy).where(InsurancePolicy.provider_id == provider_id)

    if flagged_only:
        query = query.where(InsuranceClaim.review_flag == True)

    claims = (await db.execute(query.order_by(InsuranceClaim.submitted_at.desc()))).scalars().all()

    out = []
    for c in claims:
        policy = (await db.execute(select(InsurancePolicy).where(InsurancePolicy.id == c.policy_id))).scalar_one_or_none()
        items = (await db.execute(select(ClaimItem).where(ClaimItem.claim_id == c.id))).scalars().all()
        await record_access_event(
            db,
            current_user.id,
            policy.patient_id if policy else None,
            "INSURANCE_CLAIM",
            f"claim:{c.id}",
            "READ_INSURANCE_CLAIM",
        )
        out.append(ClaimOut(
            id=c.id,
            policy_id=c.policy_id,
            policy_reference=policy.policy_reference if policy else None,
            patient_id=policy.patient_id if policy else None,
            visit_id=c.visit_id,
            submitted_at=c.submitted_at,
            claimed_amount=c.claimed_amount,
            approved_amount=c.approved_amount,
            status=c.status,
            review_flag=c.review_flag,
            review_reason=c.review_reason,
            items=[
                ClaimItemOut(
                    id=it.id,
                    item_code=it.item_code,
                    description=it.description,
                    quantity=it.quantity,
                    unit_cost=it.unit_cost,
                    line_amount=it.line_amount
                )
                for it in items
            ]
        ))
    return out

@router.post("/claims", response_model=ClaimOut)
async def create_claim_transactional(
    claim_in: ClaimCreate,
    current_user: AppUser = Depends(require_role(["insurance_analyst", "admin"])),
    db: AsyncSession = Depends(get_db)
):
    """
    Demonstrates transactional integrity with rollback:
    Inserts claim and line items atomically. If any item is invalid, rolls back entirely.
    """
    policy = (await db.execute(select(InsurancePolicy).where(InsurancePolicy.id == claim_in.policy_id))).scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Insurance policy not found.")
    await _require_policy_provider_scope(policy, current_user, db)

    visit = (await db.execute(select(Visit).where(Visit.id == claim_in.visit_id))).scalar_one_or_none()
    if not visit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Visit not found.")

    if policy.patient_id != visit.patient_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The selected insurance policy and visit must belong to the same patient.",
        )
    service_date = visit.visit_at.date()
    if policy.status != "ACTIVE" or not (policy.valid_from <= service_date <= policy.valid_until):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The selected policy was not active on the visit date.",
        )

    # Validate items first to ensure transactional consistency
    for it in claim_in.items:
        if it.quantity <= 0 or it.unit_cost < 0:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Transaction aborted and rolled back: item quantity must be positive and unit cost cannot be negative."
            )
        if it.treatment_id:
            treatment = (await db.execute(select(Treatment).where(Treatment.id == it.treatment_id))).scalar_one_or_none()
            if not treatment or treatment.visit_id != visit.id:
                await db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Each claim treatment reference must belong to the selected visit.",
                )

    total_claimed = sum(item.quantity * item.unit_cost for item in claim_in.items)
    if total_claimed > Decimal("9999999999.99"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Total claim amount exceeds the supported maximum.",
        )

    claim = InsuranceClaim(
        policy_id=claim_in.policy_id,
        visit_id=claim_in.visit_id,
        claimed_amount=total_claimed,
        approved_amount=Decimal("0.00"),
        status="SUBMITTED",
        review_flag=False
    )
    db.add(claim)
    await db.flush()

    claim_items = []
    for it in claim_in.items:
        line_amt = it.quantity * it.unit_cost
        ci = ClaimItem(
            claim_id=claim.id,
            treatment_id=it.treatment_id,
            item_code=it.item_code,
            description=it.description,
            quantity=it.quantity,
            unit_cost=it.unit_cost,
            line_amount=line_amt
        )
        claim_items.append(ci)
        db.add(ci)

    # Evaluate for explainable anomalies
    is_anomaly, reason = await InsuranceAnomalyService.evaluate_claim_for_anomalies(db, claim, claim_items)
    if is_anomaly:
        claim.review_flag = True
        claim.review_reason = reason
        claim.status = "UNDER_REVIEW"

    await db.commit()
    await db.refresh(claim)
    await record_access_event(
        db, current_user.id, policy.patient_id, "INSURANCE_CLAIM", f"claim:{claim.id}", "CREATE_INSURANCE_CLAIM"
    )

    return ClaimOut(
        id=claim.id,
        policy_id=claim.policy_id,
        policy_reference=policy.policy_reference,
        patient_id=policy.patient_id,
        visit_id=claim.visit_id,
        submitted_at=claim.submitted_at,
        claimed_amount=claim.claimed_amount,
        approved_amount=claim.approved_amount,
        status=claim.status,
        review_flag=claim.review_flag,
        review_reason=claim.review_reason,
        items=[
            ClaimItemOut(
                id=ci.id,
                item_code=ci.item_code,
                description=ci.description,
                quantity=ci.quantity,
                unit_cost=ci.unit_cost,
                line_amount=ci.line_amount
            )
            for ci in claim_items
        ]
    )

@router.post("/claims/{claim_id}/review", response_model=ClaimOut)
async def review_claim(
    claim_id: str,
    review_in: ClaimReviewRequest,
    current_user: AppUser = Depends(require_role(["insurance_analyst", "admin"])),
    db: AsyncSession = Depends(get_db)
):
    claim = (await db.execute(select(InsuranceClaim).where(InsuranceClaim.id == claim_id))).scalar_one_or_none()
    if not claim:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found.")
    policy = await _require_claim_provider_scope(claim, current_user, db)

    if review_in.approved_amount is not None and review_in.approved_amount > claim.claimed_amount:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Approved amount cannot exceed the amount claimed.",
        )

    claim.status = review_in.decision
    if review_in.decision == "APPROVED":
        claim.approved_amount = review_in.approved_amount if review_in.approved_amount is not None else claim.claimed_amount
    else:
        claim.approved_amount = Decimal("0.00")

    claim.review_reason = f"Analyst Review ({current_user.email}): {review_in.reason.strip()}"
    claim.review_flag = review_in.decision == "UNDER_REVIEW"
    await db.commit()
    await db.refresh(claim)

    items = (await db.execute(select(ClaimItem).where(ClaimItem.claim_id == claim.id))).scalars().all()
    await record_access_event(
        db, current_user.id, policy.patient_id, "INSURANCE_CLAIM", f"claim:{claim.id}", "REVIEW_INSURANCE_CLAIM"
    )

    return ClaimOut(
        id=claim.id,
        policy_id=claim.policy_id,
        policy_reference=policy.policy_reference if policy else None,
        patient_id=policy.patient_id if policy else None,
        visit_id=claim.visit_id,
        submitted_at=claim.submitted_at,
        claimed_amount=claim.claimed_amount,
        approved_amount=claim.approved_amount,
        status=claim.status,
        review_flag=claim.review_flag,
        review_reason=claim.review_reason,
        items=[
            ClaimItemOut(
                id=it.id,
                item_code=it.item_code,
                description=it.description,
                quantity=it.quantity,
                unit_cost=it.unit_cost,
                line_amount=it.line_amount
            )
            for it in items
        ]
    )

@router.get("/anomalies")
async def list_anomalies(
    current_user: AppUser = Depends(require_role(["insurance_analyst", "admin"])),
    db: AsyncSession = Depends(get_db)
):
    query = select(InsuranceClaim).where(InsuranceClaim.review_flag == True)
    provider_id = await _insurance_provider_scope(current_user, db)
    if provider_id:
        query = query.join(InsurancePolicy).where(InsurancePolicy.provider_id == provider_id)
    claims = (await db.execute(query)).scalars().all()
    out = []
    for c in claims:
        policy = (await db.execute(select(InsurancePolicy).where(InsurancePolicy.id == c.policy_id))).scalar_one_or_none()
        await record_access_event(
            db,
            current_user.id,
            policy.patient_id if policy else None,
            "INSURANCE_CLAIM",
            f"claim:{c.id}",
            "READ_INSURANCE_ANOMALY",
        )
        out.append({
            "id": c.id,
            "claim_id": c.id,
            "review_reason": c.review_reason,
            "status": c.status,
            "claimed_amount": float(c.claimed_amount),
            "submitted_at": c.submitted_at
        })
    return out

@router.post("/anomalies/{claim_id}/resolve")
async def resolve_anomaly(
    claim_id: str,
    body: AnomalyResolutionRequest,
    current_user: AppUser = Depends(require_role(["insurance_analyst", "admin"])),
    db: AsyncSession = Depends(get_db)
):
    claim = (await db.execute(select(InsuranceClaim).where(InsuranceClaim.id == claim_id))).scalar_one_or_none()
    if not claim:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found.")
    policy = await _require_claim_provider_scope(claim, current_user, db)
    status_val = body.resolution_status
    notes = body.notes.strip()
    claim.status = "REJECTED" if status_val in ("REJECTED", "CONFIRMED_FRAUD") else status_val
    claim.approved_amount = claim.claimed_amount if status_val == "APPROVED" else Decimal("0.00")
    claim.review_flag = False
    claim.review_reason = f"Adjudicated ({status_val}): {notes}"
    await db.commit()
    await record_access_event(
        db, current_user.id, policy.patient_id, "INSURANCE_CLAIM", f"claim:{claim.id}", "RESOLVE_INSURANCE_ANOMALY"
    )
    return {
        "claim_id": claim.id,
        "resolution_status": status_val,
        "message": "Anomaly flag resolved successfully."
    }

@router.get("/analytics/expenditure", response_model=ExpenditureSummaryOut)
async def get_insurance_expenditures(
    current_user: AppUser = Depends(require_role(["insurance_analyst", "admin"])),
    db: AsyncSession = Depends(get_db)
):
    provider_id = await _insurance_provider_scope(current_user, db)
    claims_query = select(InsuranceClaim)
    if provider_id:
        claims_query = claims_query.join(InsurancePolicy).where(InsurancePolicy.provider_id == provider_id)
    claims = (await db.execute(claims_query)).scalars().all()
    total_claimed = sum((c.claimed_amount for c in claims), Decimal("0.00"))
    total_approved = sum((c.approved_amount for c in claims), Decimal("0.00"))
    flagged_count = sum(1 for c in claims if c.review_flag)

    # Disease cost breakdown
    from sqlalchemy import text
    provider_filter = "WHERE p.provider_id = :provider_id" if provider_id else ""
    disease_costs_q = text(f"""
        WITH disease_claims AS (
            SELECT DISTINCT
                d.name AS disease_name,
                d.code AS disease_code,
                c.id AS claim_id,
                c.claimed_amount
            FROM disease d
            JOIN diagnosis diag ON diag.disease_id = d.id
            JOIN visit v ON v.id = diag.visit_id
            JOIN insurance_claim c ON c.visit_id = v.id
            JOIN insurance_policy p ON p.id = c.policy_id
            {provider_filter}
        )
        SELECT
            disease_name,
            disease_code,
            COUNT(claim_id) AS claim_count,
            COALESCE(SUM(claimed_amount), 0) AS total_claimed_amount
        FROM disease_claims
        GROUP BY disease_name, disease_code
        ORDER BY total_claimed_amount DESC;
    """)
    res = await db.execute(disease_costs_q, {"provider_id": provider_id} if provider_id else {})
    disease_costs = [
        {
            "disease_name": row["disease_name"],
            "disease_code": row["disease_code"],
            "claim_count": row["claim_count"],
            "total_claimed_amount": float(row["total_claimed_amount"])
        }
        for row in res.mappings()
    ]

    await record_access_event(
        db,
        current_user.id,
        None,
        "INSURANCE_ANALYTICS",
        f"provider:{provider_id}" if provider_id else "provider:all",
        "READ_INSURANCE_EXPENDITURE",
    )

    return ExpenditureSummaryOut(
        total_claims=len(claims),
        total_claimed=total_claimed,
        total_approved=total_approved,
        flagged_anomaly_count=flagged_count,
        disease_costs=disease_costs
    )
