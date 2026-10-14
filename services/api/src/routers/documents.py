import uuid
from typing import List
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.models import (
    AppUser, MedicalDocument, RecordIntegrity, Patient, Visit, Doctor
)
from src.schemas.documents import DocumentCreate, DocumentOut, DocumentDetail
from src.services.mongo import MongoDocumentService
from src.services.integrity import IntegrityService
from src.services.blockchain import BlockchainService
from src.routers.deps import get_current_user, require_role, verify_patient_access

router = APIRouter(prefix="/documents", tags=["Medical Documents"])

@router.get("", response_model=List[DocumentOut])
async def list_documents(
    patient_id: str = None,
    current_user: AppUser = Depends(require_role(["doctor", "patient", "admin"])),
    db: AsyncSession = Depends(get_db)
):
    query = select(MedicalDocument)
    if current_user.role == "patient":
        pt = (await db.execute(select(Patient).where(Patient.user_id == current_user.id))).scalar_one_or_none()
        if not pt:
            return []
        query = query.where(MedicalDocument.patient_id == pt.id)
    elif patient_id:
        await verify_patient_access(patient_id, current_user, db)
        query = query.where(MedicalDocument.patient_id == patient_id)

    docs = (await db.execute(query.order_by(MedicalDocument.created_at.desc()))).scalars().all()

    out = []
    for d in docs:
        integ = (await db.execute(select(RecordIntegrity).where(RecordIntegrity.medical_document_id == d.id))).scalar_one_or_none()
        out.append(DocumentOut(
            id=d.id,
            patient_id=d.patient_id,
            visit_id=d.visit_id,
            document_type=d.document_type,
            storage_status=d.storage_status,
            created_at=d.created_at,
            created_by=d.created_by,
            verification_status=integ.verification_status if integ else "UNVERIFIED",
            commitment_hash=integ.commitment_hash if integ else None
        ))
    return out

@router.post("", response_model=DocumentOut)
async def create_document(
    doc_in: DocumentCreate,
    current_user: AppUser = Depends(require_role(["doctor", "admin"])),
    db: AsyncSession = Depends(get_db)
):
    patient = (await db.execute(select(Patient).where(Patient.id == doc_in.patient_id))).scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")

    mongo_doc_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()

    # 1. Write narrative text to MongoDB
    raw_doc = {
        "_id": mongo_doc_id,
        "patient_id": doc_in.patient_id,
        "visit_id": doc_in.visit_id,
        "document_type": doc_in.document_type,
        "title": doc_in.title,
        "content": doc_in.content,
        "structured_extract": doc_in.structured_extract or {},
        "created_at": now_iso,
        "created_by": current_user.id,
        "version": 1
    }
    await MongoDocumentService.insert_document(raw_doc)

    # 2. Compute cryptographic commitment (SHA-256 with off-chain salt)
    commitment_hash, salt = IntegrityService.create_commitment_for_doc(raw_doc)

    # 3. Store relational metadata in PostgreSQL
    med_doc = MedicalDocument(
        patient_id=doc_in.patient_id,
        visit_id=doc_in.visit_id,
        document_type=doc_in.document_type,
        mongo_document_id=mongo_doc_id,
        storage_status="STORED",
        created_by=current_user.id
    )
    db.add(med_doc)
    await db.flush()

    rec_integrity = RecordIntegrity(
        medical_document_id=med_doc.id,
        record_version=1,
        commitment_hash=commitment_hash,
        algorithm="SHA256_SALTED",
        salt=salt,
        verified_at=datetime.now(timezone.utc),
        verification_status="VERIFIED_MATCH"
    )
    db.add(rec_integrity)
    await db.commit()
    await db.refresh(med_doc)

    # 4. Asynchronously anchor commitment to blockchain (or unanchored mode)
    try:
        await BlockchainService.anchor_record(med_doc.id, commitment_hash, 1)
    except Exception:
        pass

    return DocumentOut(
        id=med_doc.id,
        patient_id=med_doc.patient_id,
        visit_id=med_doc.visit_id,
        document_type=med_doc.document_type,
        storage_status=med_doc.storage_status,
        created_at=med_doc.created_at,
        created_by=med_doc.created_by,
        verification_status=rec_integrity.verification_status,
        commitment_hash=rec_integrity.commitment_hash
    )

@router.get("/{document_id}", response_model=DocumentDetail)
async def get_document_detail(
    document_id: str,
    current_user: AppUser = Depends(require_role(["doctor", "patient", "admin"])),
    db: AsyncSession = Depends(get_db)
):
    med_doc = (await db.execute(select(MedicalDocument).where(MedicalDocument.id == document_id))).scalar_one_or_none()
    if not med_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Medical document not found.")

    await verify_patient_access(med_doc.patient_id, current_user, db)

    # Fetch narrative content from MongoDB
    mongo_doc = await MongoDocumentService.get_document(med_doc.mongo_document_id)
    if not mongo_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document payload not found in document store.")

    integ = (await db.execute(select(RecordIntegrity).where(RecordIntegrity.medical_document_id == med_doc.id))).scalar_one_or_none()

    return DocumentDetail(
        id=med_doc.id,
        patient_id=med_doc.patient_id,
        visit_id=med_doc.visit_id,
        document_type=med_doc.document_type,
        storage_status=med_doc.storage_status,
        created_at=med_doc.created_at,
        created_by=med_doc.created_by,
        verification_status=integ.verification_status if integ else "UNVERIFIED",
        commitment_hash=integ.commitment_hash if integ else None,
        title=mongo_doc.get("title", "Clinical Document"),
        content=mongo_doc.get("content", ""),
        structured_extract=mongo_doc.get("structured_extract"),
        version=mongo_doc.get("version", 1)
    )
