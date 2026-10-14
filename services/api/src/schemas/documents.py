from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel

class DocumentCreate(BaseModel):
    patient_id: str
    visit_id: Optional[str] = None
    document_type: str # clinical_note, diagnostic_report
    title: str
    content: str
    structured_extract: Optional[Dict[str, Any]] = None

class DocumentOut(BaseModel):
    id: str
    patient_id: str
    visit_id: Optional[str] = None
    document_type: str
    storage_status: str
    created_at: datetime
    created_by: str
    verification_status: Optional[str] = None
    commitment_hash: Optional[str] = None

    class Config:
        from_attributes = True

class DocumentDetail(DocumentOut):
    title: str
    content: str
    structured_extract: Optional[Dict[str, Any]] = None
    version: int = 1
