from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.models import AppUser, BlockchainEvent, MedicalDocument, RecordIntegrity
from src.schemas.integrity import IntegrityVerificationOut, TamperDemoOut
from src.services.integrity import IntegrityService
from src.services.mongo import MongoDocumentService
from src.services.blockchain import BlockchainService
from src.routers.deps import get_current_user, require_role, verify_patient_access
from src.config import settings

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
    await verify_patient_access(med_doc.patient_id, current_user, db, action="VERIFY_DOCUMENT_INTEGRITY")

    integ = (await db.execute(select(RecordIntegrity).where(RecordIntegrity.medical_document_id == document_id))).scalar_one_or_none()
    if not integ:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integrity commitment record not found.")

    is_valid, computed_hash, msg = await IntegrityService.verify_record(
        doc_id=med_doc.mongo_document_id,
        expected_commitment=integ.commitment_hash,
        salt=integ.salt
    )

    chain_event = (await db.execute(
        select(BlockchainEvent)
        .where(
            BlockchainEvent.event_type == "RECORD_COMMITMENT",
            BlockchainEvent.opaque_reference == document_id,
        )
        .order_by(BlockchainEvent.created_at.desc())
    )).scalars().first()
    chain_status, chain_commitment, chain_version = await BlockchainService.get_record_commitment(document_id)
    if chain_status == "CONFIRMED" and (
        not chain_commitment
        or chain_commitment.lower() != integ.commitment_hash.lower()
        or chain_version != integ.record_version
    ):
        is_valid = False
        msg = "Integrity metadata does not match the immutable blockchain commitment."

    now = datetime.now(timezone.utc)
    integ.verified_at = now
    if not computed_hash:
        integ.verification_status = "DOCUMENT_NOT_FOUND"
    elif not is_valid:
        integ.verification_status = "TAMPER_DETECTED"
    elif chain_status == "CONFIRMED":
        integ.verification_status = "VERIFIED_MATCH"
    else:
        integ.verification_status = f"LOCAL_MATCH_{chain_status}"
        msg = f"{msg} Blockchain commitment status: {chain_status}."
    await db.commit()

    confirmed = chain_status == "CONFIRMED"

    return IntegrityVerificationOut(
        document_id=document_id,
        expected_commitment=integ.commitment_hash,
        computed_commitment=computed_hash,
        verification_status=integ.verification_status,
        is_valid=is_valid,
        verified_at=now,
        record_version=integ.record_version,
        chain_status=chain_status,
        chain_tx_hash=chain_event.transaction_hash if confirmed and chain_event else None,
        chain_block_number=chain_event.block_number if confirmed and chain_event else None,
        explanation=msg
    )

@router.post("/tamper-demo/{document_id}", response_model=TamperDemoOut)
async def simulate_tampering(
    document_id: str,
    current_user: AppUser = Depends(require_role(["doctor", "admin"])),
    db: AsyncSession = Depends(get_db)
):
    """
    DEMO ONLY: Simulates an unauthorized alteration inside MongoDB document store.
    Modifies clinical note content by adding a tampered sentence.
    """
    if not settings.DEMO_MODE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")

    med_doc = (await db.execute(select(MedicalDocument).where(MedicalDocument.id == document_id))).scalar_one_or_none()
    if not med_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    await verify_patient_access(med_doc.patient_id, current_user, db, action="DEMO_TAMPER_DOCUMENT")

    doc = await MongoDocumentService.get_document(med_doc.mongo_document_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document payload not found in store.")

    integrity = (await db.execute(
        select(RecordIntegrity).where(RecordIntegrity.medical_document_id == document_id)
    )).scalar_one_or_none()
    if integrity:
        integrity.verification_status = "UNVERIFIED"
        integrity.verified_at = None
        await db.commit()

    original_content = doc.get("content", "")
    tampered_content = original_content + "\n[UNAUTHORIZED TAMPER ALTERATION: Patient dosage altered to 1000mg without clinical order.]"
    
    updated = await MongoDocumentService.update_document_content(med_doc.mongo_document_id, tampered_content)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document store could not apply the demo alteration.",
        )

    return TamperDemoOut(
        document_id=document_id,
        message="Demo tampering applied to MongoDB document payload. Run verification to observe cryptographic failure detection.",
        original_snippet=original_content[:120] + "...",
        tampered_snippet=tampered_content[-140:]
    )
