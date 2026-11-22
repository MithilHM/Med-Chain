import uuid
import logging
from typing import List
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.models import (
    AppUser, MedicalDocument, RecordIntegrity, BlockchainEvent, Patient, Visit, Doctor
)
from typing import Optional
from src.schemas.documents import DocumentCreate, DocumentOut, DocumentDetail
from pydantic import BaseModel as PydanticBaseModel, Field
from src.services.mongo import DocumentStoreUnavailable, MongoDocumentService
from src.services.integrity import IntegrityService, canonicalize_document, compute_commitment
from src.services.outbox import OutboxService
from src.services.events import ClinicalEvent, EventBus
from fastapi import Query
from src.routers.deps import doctor_accessible_patient_ids, get_current_user, require_role, verify_patient_access

router = APIRouter(prefix="/documents", tags=["Medical Documents"])
logger = logging.getLogger("medchain.documents")

@router.get("", response_model=List[DocumentOut])
async def list_documents(
    patient_id: str = None,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    current_user: AppUser = Depends(require_role(["doctor", "patient", "admin"])),
    db: AsyncSession = Depends(get_db)
):
    query = select(MedicalDocument)
    if current_user.role == "patient":
        pt = (await db.execute(select(Patient).where(Patient.user_id == current_user.id))).scalar_one_or_none()
        if not pt:
            return []
        query = query.where(MedicalDocument.patient_id == pt.id)
    else:
        if current_user.role == "doctor":
            doctor = (await db.execute(select(Doctor).where(Doctor.user_id == current_user.id))).scalar_one_or_none()
            if not doctor:
                return []
            assigned_patient_ids = await doctor_accessible_patient_ids(db, doctor, current_user)
            if not assigned_patient_ids:
                return []
            query = query.where(MedicalDocument.patient_id.in_(assigned_patient_ids))
        if patient_id:
            await verify_patient_access(patient_id, current_user, db, action="LIST_PATIENT_DOCUMENTS")
            query = query.where(MedicalDocument.patient_id == patient_id)

    docs = (await db.execute(
        query.order_by(MedicalDocument.created_at.desc()).offset(offset).limit(limit)
    )).scalars().all()

    if current_user.role == "patient" or (current_user.role in {"doctor", "admin"} and not patient_id):
        for accessible_patient_id in {document.patient_id for document in docs}:
            await verify_patient_access(
                accessible_patient_id,
                current_user,
                db,
                action="LIST_PATIENT_DOCUMENTS",
            )

    doc_ids = [d.id for d in docs]
    integrity_by_doc = {
        row.medical_document_id: row
        for row in (await db.execute(
            select(RecordIntegrity).where(RecordIntegrity.medical_document_id.in_(doc_ids))
        )).scalars().all()
    } if doc_ids else {}
    out = []
    for d in docs:
        integ = integrity_by_doc.get(d.id)
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
    patient = (await db.execute(select(Patient).where((Patient.id == doc_in.patient_id) | (Patient.display_code == doc_in.patient_id)))).scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")

    await verify_patient_access(patient.id, current_user, db, action="CREATE_CLINICAL_DOCUMENT")
    if doc_in.visit_id:
        visit = (await db.execute(select(Visit).where(Visit.id == doc_in.visit_id))).scalar_one_or_none()
        if not visit or visit.patient_id != patient.id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Visit must belong to the selected patient.")
        if current_user.role == "doctor":
            doctor = (await db.execute(select(Doctor).where(Doctor.user_id == current_user.id))).scalar_one_or_none()
            if not doctor or visit.doctor_id != doctor.id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Documents may only be attached to your own visit.")

    mongo_doc_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()

    # 1. Write narrative text to MongoDB
    raw_doc = {
        "_id": mongo_doc_id,
        "patient_id": patient.id,
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
        patient_id=patient.id,
        visit_id=doc_in.visit_id,
        document_type=doc_in.document_type,
        mongo_document_id=mongo_doc_id,
        storage_status="STORED",
        created_by=current_user.id
    )
    try:
        db.add(med_doc)
        await db.flush()

        rec_integrity = RecordIntegrity(
            medical_document_id=med_doc.id,
            record_version=1,
            commitment_hash=commitment_hash,
            algorithm="SHA256_SALTED",
            salt=salt,
            verification_status="UNVERIFIED"
        )
        db.add(rec_integrity)
        # The chain anchor commits atomically with the metadata; the outbox worker delivers it.
        await OutboxService.enqueue_record_anchor(db, med_doc.id, commitment_hash, 1)
        await db.commit()
    except Exception:
        await db.rollback()
        try:
            relational_record = await db.execute(
                select(MedicalDocument.id).where(MedicalDocument.mongo_document_id == mongo_doc_id)
            )
            commit_was_recorded = relational_record.scalar_one_or_none() is not None
        except Exception as status_error:
            await db.rollback()
            logger.error(
                "Could not determine whether document metadata committed for payload %s; preserving the encrypted payload: %s",
                mongo_doc_id,
                status_error,
            )
        else:
            if not commit_was_recorded and not await MongoDocumentService.delete_document(mongo_doc_id):
                logger.error("Could not clean up orphan document payload %s after relational commit failure.", mongo_doc_id)
        raise
    await db.refresh(med_doc)
    EventBus.publish(ClinicalEvent(
        "document.created",
        patient_id=med_doc.patient_id,
        data={"document_id": med_doc.id, "document_type": med_doc.document_type},
    ))

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

    await verify_patient_access(med_doc.patient_id, current_user, db, action="READ_CLINICAL_DOCUMENT")

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



class DocumentAmendRequest(PydanticBaseModel):
    amendment_text: str = Field(..., min_length=1, max_length=20000)
    reason: str = Field(..., min_length=3, max_length=500)
    # Optional free-text attestation. The recorded author always comes from the authenticated session.
    author_signature: Optional[str] = Field(default=None, max_length=200)


async def _author_display(db: AsyncSession, user: AppUser) -> str:
    if user.role == "doctor":
        doctor = (await db.execute(select(Doctor).where(Doctor.user_id == user.id))).scalar_one_or_none()
        if doctor:
            return f"{doctor.display_name} ({doctor.specialty})"
    return f"{user.email} ({user.role})"


@router.post("/{document_id}/amend")
async def amend_document(
    document_id: str,
    amend_in: DocumentAmendRequest,
    current_user: AppUser = Depends(require_role(["doctor", "admin"])),
    db: AsyncSession = Depends(get_db),
):
    """
    Append a clinical addendum as a new document version.

    - The prior version is preserved as an immutable encrypted snapshot.
    - Amending is refused if the current content already fails integrity verification.
    - The author is the authenticated user, not client-supplied text.
    - The new version's commitment is anchored on-chain through the outbox (versions only increase).
    """
    med_doc = (await db.execute(
        select(MedicalDocument).where(MedicalDocument.id == document_id)
    )).scalar_one_or_none()
    if not med_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Medical document not found.")

    await verify_patient_access(med_doc.patient_id, current_user, db, action="AMEND_CLINICAL_DOCUMENT")

    mongo_doc = await MongoDocumentService.get_document(med_doc.mongo_document_id)
    if not mongo_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document payload not found in document store.")

    integ = (await db.execute(
        select(RecordIntegrity).where(RecordIntegrity.medical_document_id == med_doc.id).with_for_update()
    )).scalar_one_or_none()
    if integ and compute_commitment(canonicalize_document(mongo_doc), integ.salt).lower() != integ.commitment_hash.lower():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The current document content fails integrity verification. Amendment is blocked pending investigation.",
        )

    current_version = integ.record_version if integ else int(mongo_doc.get("version", 1))
    new_version = current_version + 1
    now_iso = datetime.now(timezone.utc).isoformat()
    author = await _author_display(db, current_user)

    # 1. Preserve the prior version as an immutable snapshot.
    snapshot = dict(mongo_doc)
    snapshot["_id"] = f"{med_doc.mongo_document_id}::v{current_version}"
    snapshot["superseded_at"] = now_iso
    snapshot["superseded_by_version"] = new_version
    await MongoDocumentService.insert_document(snapshot)

    # 2. Write the amended current version.
    amendment_block = (
        f"\n\n--- AMENDMENT v{new_version} ---\n"
        f"Date: {now_iso}\n"
        f"Author: {author}\n"
        f"Reason: {amend_in.reason}\n"
        + (f"Attestation: {amend_in.author_signature}\n" if amend_in.author_signature else "")
        + f"Addendum:\n{amend_in.amendment_text}\n"
        f"--- END AMENDMENT v{new_version} ---"
    )
    updated_doc = {
        **mongo_doc,
        "content": mongo_doc.get("content", "") + amendment_block,
        "version": new_version,
        "last_amended_at": now_iso,
        "last_amended_by": current_user.id,
    }
    if not await MongoDocumentService.update_document(med_doc.mongo_document_id, updated_doc):
        raise DocumentStoreUnavailable("The document store could not apply the amendment.")

    # 3. Commit the new commitment and its chain anchor atomically; restore the payload on failure.
    commitment_hash, salt = IntegrityService.create_commitment_for_doc(updated_doc)
    try:
        if integ:
            integ.commitment_hash = commitment_hash
            integ.salt = salt
            integ.record_version = new_version
            integ.verification_status = "UNVERIFIED"
            integ.verified_at = None
        else:
            db.add(RecordIntegrity(
                medical_document_id=med_doc.id,
                record_version=new_version,
                commitment_hash=commitment_hash,
                algorithm="SHA256_SALTED",
                salt=salt,
                verification_status="UNVERIFIED",
            ))
        await OutboxService.enqueue_record_anchor(db, med_doc.id, commitment_hash, new_version)
        await db.commit()
    except Exception:
        await db.rollback()
        logger.error("Amendment commit failed for document %s; restoring version %d payload.", document_id, current_version)
        await MongoDocumentService.insert_document(mongo_doc)
        raise

    logger.info("Document %s amended to version %d by %s", document_id, new_version, current_user.id)
    EventBus.publish(ClinicalEvent(
        "document.amended",
        patient_id=med_doc.patient_id,
        data={"document_id": med_doc.id, "version": new_version},
    ))

    return {
        "status": "AMENDED",
        "document_id": document_id,
        "new_version": new_version,
        "previous_version_preserved": True,
        "amended_at": now_iso,
        "author": author,
        "chain_status": "QUEUED",
    }
