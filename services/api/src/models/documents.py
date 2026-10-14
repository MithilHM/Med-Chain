from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from src.models.base import BaseModel

class MedicalDocument(BaseModel):
    __tablename__ = "medical_document"

    patient_id = Column(String(36), ForeignKey("patient.id"), nullable=False, index=True)
    visit_id = Column(String(36), ForeignKey("visit.id"), nullable=True, index=True)
    document_type = Column(String(50), nullable=False, index=True)
    mongo_document_id = Column(String(100), nullable=False, index=True)
    storage_status = Column(String(50), default="STORED", nullable=False)
    created_by = Column(String(36), ForeignKey("app_user.id"), nullable=False)

    patient = relationship("Patient", back_populates="documents")
    visit = relationship("Visit", back_populates="documents")
    creator = relationship("AppUser")
    integrity = relationship("RecordIntegrity", back_populates="document", uselist=False, cascade="all, delete-orphan")

class RecordIntegrity(BaseModel):
    __tablename__ = "record_integrity"

    medical_document_id = Column(String(36), ForeignKey("medical_document.id", ondelete="CASCADE"), unique=True, nullable=False)
    record_version = Column(Integer, default=1, nullable=False)
    commitment_hash = Column(String(66), nullable=False)
    algorithm = Column(String(50), default="SHA256_SALTED", nullable=False)
    salt = Column(String(64), nullable=False) # Off-chain salt, strictly hidden from research APIs
    verified_at = Column(DateTime(timezone=True), nullable=True)
    verification_status = Column(String(50), default="UNVERIFIED", nullable=False)

    document = relationship("MedicalDocument", back_populates="integrity")
