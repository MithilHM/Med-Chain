from typing import Optional
from datetime import datetime
from pydantic import BaseModel

class IntegrityVerificationOut(BaseModel):
    document_id: str
    expected_commitment: str
    computed_commitment: str
    verification_status: str # VERIFIED_MATCH requires both the local commitment and confirmed chain anchor to match.
    is_valid: bool
    verified_at: datetime
    record_version: int
    chain_status: str # CONFIRMED, UNANCHORED, UNAVAILABLE
    chain_tx_hash: Optional[str] = None
    chain_block_number: Optional[int] = None
    explanation: str

class TamperDemoOut(BaseModel):
    document_id: str
    message: str
    original_snippet: str
    tampered_snippet: str
