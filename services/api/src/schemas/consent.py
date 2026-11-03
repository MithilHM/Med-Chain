from typing import List, Optional, Dict, Any, Literal
from datetime import datetime
from pydantic import BaseModel, Field, field_validator

ConsentScope = Literal[
    "aggregate_diagnoses",
    "deidentified_cohort",
    "medication_history",
    "lab_summaries",
]

class AccessRequestCreate(BaseModel):
    patient_id: str
    project_id: str
    purpose: str
    requested_scopes: List[ConsentScope] = Field(min_length=1)

    @field_validator("requested_scopes")
    @classmethod
    def scopes_must_be_unique(cls, scopes: List[ConsentScope]) -> List[ConsentScope]:
        if len(scopes) != len(set(scopes)):
            raise ValueError("Requested consent scopes must be unique.")
        return scopes

class AccessRequestDecision(BaseModel):
    decision: Literal["APPROVED", "REJECTED"]
    approved_scopes: Optional[List[ConsentScope]] = Field(default=None, min_length=1)
    valid_days: int = Field(default=30, ge=1, le=365)

class AccessRequestOut(BaseModel):
    id: str
    patient_id: str
    patient_display_code: Optional[str] = None
    project_id: str
    project_title: Optional[str] = None
    purpose: str
    requested_scopes: List[str]
    status: str
    requested_at: datetime
    decided_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class ConsentOut(BaseModel):
    id: str
    patient_id: str
    patient_display_code: Optional[str] = None
    project_id: str
    project_title: Optional[str] = None
    purpose: str
    scope_json: Dict[str, Any]
    access_mode: str
    valid_from: datetime
    valid_until: datetime
    status: str
    granted_at: datetime
    revoked_at: Optional[datetime] = None
    chain_tx_hash: Optional[str] = None

    class Config:
        from_attributes = True

class ResearchQueryRequest(BaseModel):
    project_id: str
    query_type: Literal["cohort_summary", "disease_distribution", "medication_utilization", "lab_summary"]
    disease_code: Optional[str] = Field(default=None, max_length=50)
    filters: Optional[Dict[str, Any]] = None

    @field_validator("disease_code")
    @classmethod
    def normalize_disease_code(cls, value: Optional[str]) -> Optional[str]:
        normalized = value.strip().upper() if value else None
        return normalized or None

class AccessEventOut(BaseModel):
    id: str
    actor_user_id: str
    actor_email: Optional[str] = None
    patient_id: Optional[str] = None
    resource_type: str
    resource_reference: str
    action: str
    decision: str
    reason_code: str
    occurred_at: datetime
    chain_tx_hash: Optional[str] = None

    class Config:
        from_attributes = True
