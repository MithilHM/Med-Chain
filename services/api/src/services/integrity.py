import hashlib
import json
import secrets
from typing import Dict, Any, Tuple
from datetime import datetime, timezone
from src.services.mongo import MongoDocumentService

def canonicalize_document(doc_dict: Dict[str, Any]) -> str:
    """Produces a deterministic sorted-key, compact JSON representation."""
    # We canonicalize the core medical payload: patient_id, visit_id, document_type, title, content, structured_extract
    payload = {
        "patient_id": str(doc_dict.get("patient_id", "")),
        "visit_id": str(doc_dict.get("visit_id") or ""),
        "document_type": str(doc_dict.get("document_type", "")),
        "title": str(doc_dict.get("title", "")),
        "content": str(doc_dict.get("content", "")),
        "structured_extract": doc_dict.get("structured_extract") or {}
    }
    return json.dumps(payload, sort_keys=True, separators=(',', ':'))

def generate_salt() -> str:
    return secrets.token_hex(32)

def generate_record_hash(record_dict: dict) -> str:
    """Generates a deterministic SHA-256 string for off-chain payloads."""
    canonical_json = json.dumps(record_dict, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()

def compute_commitment(canonical_json: str, salt: str) -> str:
    hasher = hashlib.sha256()
    hasher.update((canonical_json + salt).encode('utf-8'))
    return "0x" + hasher.hexdigest()

class IntegrityService:
    @staticmethod
    def create_commitment_for_doc(doc_dict: Dict[str, Any]) -> Tuple[str, str]:
        """Returns (commitment_hash, salt)"""
        canonical = canonicalize_document(doc_dict)
        salt = generate_salt()
        commitment = compute_commitment(canonical, salt)
        return commitment, salt

    @staticmethod
    async def verify_record(doc_id: str, expected_commitment: str, salt: str) -> Tuple[bool, str, str]:
        """
        Returns (is_valid, computed_commitment, message)
        """
        doc = await MongoDocumentService.get_document(doc_id)
        if not doc:
            return False, "", "Document payload not found in document store."
        
        canonical = canonicalize_document(doc)
        computed = compute_commitment(canonical, salt)
        is_valid = (computed.lower() == expected_commitment.lower())
        message = "Verification succeeded: cryptographic hash matches the stored integrity commitment." if is_valid else "Tamper detected: document content does not match the stored integrity commitment."
        return is_valid, computed, message
