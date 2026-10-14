from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.models import AppUser, MedicalDocument, RecordIntegrity
from src.schemas.integrity import IntegrityVerificationOut, TamperDemoOut
from src.services.integrity import IntegrityService
from src.services.mongo import MongoDocumentService
from src.services.blockchain import BlockchainService
from src.routers.deps import get_current_user

router = APIRouter(prefix="/integrity", tags=["Record Cryptographic Integrity"])

@router.get("/verify/{document_id}", response_model=IntegrityVerificationOut)
async def verify_document_integrity(
    document_id: str,
    current_user: AppUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    med_doc = (await db.execute(select(MedicalDocument).where(MedicalDocument.id == document_id))).scalar_one_or_none()
    if not med_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Medical document not found.")

    integ = (await db.execute(select(RecordIntegrity).where(RecordIntegrity.medical_document_id == document_id))).scalar_one_or_none()
    if not integ:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integrity commitment record not found.")

    is_valid, computed_hash, msg = await IntegrityService.verify_record(
        doc_id=med_doc.mongo_document_id,
        expected_commitment=integ.commitment_hash,
        salt=integ.salt
    )

    now = datetime.now(timezone.utc)
    integ.verified_at = now
    integ.verification_status = "VERIFIED_MATCH" if is_valid else "TAMPER_DETECTED"
    await db.commit()

    chain_status_info = BlockchainService.get_status()
    chain_mode = "CONFIRMED" if chain_status_info["status"] == "connected" else "UNANCHORED"

    return IntegrityVerificationOut(
        document_id=document_id,
        expected_commitment=integ.commitment_hash,
        computed_commitment=computed_hash,
        verification_status=integ.verification_status,
        is_valid=is_valid,
        verified_at=now,
        record_version=integ.record_version,
        chain_status=chain_mode,
        chain_tx_hash=f"0x{integ.commitment_hash[2:34]}",
        chain_block_number=chain_status_info.get("latest_block", 42),
        explanation=msg
    )

@router.post("/tamper-demo/{document_id}", response_model=TamperDemoOut)
async def simulate_tampering(
    document_id: str,
    current_user: AppUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    DEMO ONLY: Simulates an unauthorized alteration inside MongoDB document store.
    Modifies clinical note content by adding a tampered sentence.
    """
    med_doc = (await db.execute(select(MedicalDocument).where(MedicalDocument.id == document_id))).scalar_one_or_none()
    if not med_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    doc = await MongoDocumentService.get_document(med_doc.mongo_document_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document payload not found in store.")

    original_content = doc.get("content", "")
    tampered_content = original_content + "\n[UNAUTHORIZED TAMPER ALTERATION: Patient dosage altered to 1000mg without clinical order.]"
    
    await MongoDocumentService.update_document_content(med_doc.mongo_document_id, tampered_content)

    return TamperDemoOut(
        document_id=document_id,
        message="Demo tampering applied to MongoDB document payload. Run verification to observe cryptographic failure detection.",
        original_snippet=original_content[:120] + "...",
        tampered_snippet=tampered_content[-140:]
    )
