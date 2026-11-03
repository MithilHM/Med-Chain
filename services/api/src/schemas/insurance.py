from typing import List, Optional, Literal
from datetime import datetime, date
from decimal import Decimal
from pydantic import BaseModel, Field

class ClaimItemCreate(BaseModel):
    treatment_id: Optional[str] = None
    item_code: str = Field(min_length=1, max_length=50)
    description: str = Field(min_length=1, max_length=200)
    quantity: int = Field(gt=0)
    unit_cost: Decimal = Field(ge=0, max_digits=12, decimal_places=2)

class ClaimCreate(BaseModel):
    policy_id: str
    visit_id: str
    items: List[ClaimItemCreate] = Field(min_length=1)

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
    decision: Literal["APPROVED", "REJECTED", "UNDER_REVIEW"]
    approved_amount: Optional[Decimal] = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    reason: str = Field(min_length=1, max_length=2000)

class AnomalyResolutionRequest(BaseModel):
    resolution_status: Literal["APPROVED", "REJECTED"]
    notes: str = Field(default="", max_length=2000)

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
