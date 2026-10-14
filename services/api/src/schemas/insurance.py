from typing import List, Optional
from datetime import datetime, date
from decimal import Decimal
from pydantic import BaseModel

class ClaimItemCreate(BaseModel):
    treatment_id: Optional[str] = None
    item_code: str
    description: str
    quantity: int
    unit_cost: Decimal

class ClaimCreate(BaseModel):
    policy_id: str
    visit_id: str
    items: List[ClaimItemCreate]

class ClaimItemOut(BaseModel):
    id: str
    item_code: str
    description: str
    quantity: int
    unit_cost: Decimal
    line_amount: Decimal

    class Config:
        from_attributes = True

class ClaimOut(BaseModel):
    id: str
    policy_id: str
    policy_reference: Optional[str] = None
    patient_id: Optional[str] = None
    visit_id: str
    submitted_at: datetime
    claimed_amount: Decimal
    approved_amount: Decimal
    status: str
    review_flag: bool
    review_reason: Optional[str] = None
    items: List[ClaimItemOut] = []

    class Config:
        from_attributes = True

class ClaimReviewRequest(BaseModel):
    decision: str # APPROVED, REJECTED, FLAGGED_INVESTIGATION
    approved_amount: Optional[Decimal] = None
    reason: str

class PolicyOut(BaseModel):
    id: str
    patient_id: str
    provider_name: str
    policy_reference: str
    coverage_type: str
    valid_from: date
    valid_until: date
    status: str

    class Config:
        from_attributes = True

class ExpenditureSummaryOut(BaseModel):
    total_claims: int
    total_claimed: Decimal
    total_approved: Decimal
    flagged_anomaly_count: int
    disease_costs: List[dict]
