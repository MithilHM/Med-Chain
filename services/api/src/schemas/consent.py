from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel

class AccessRequestCreate(BaseModel):
    patient_id: str
    project_id: str
    purpose: str
    requested_scopes: List[str] # e.g. ["aggregate_diagnoses", "medication_history", "lab_summaries"]

class AccessRequestDecision(BaseModel):
    decision: str # APPROVED, REJECTED
    approved_scopes: Optional[List[str]] = None
    valid_days: Optional[int] = 30

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
    query_type: str # cohort_summary, disease_distribution, medication_utilization
    disease_code: Optional[str] = None
    filters: Optional[Dict[str, Any]] = None

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
