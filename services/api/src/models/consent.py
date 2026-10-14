from sqlalchemy import Column, String, Integer, DateTime, BigInteger, ForeignKey, JSON, CheckConstraint
from sqlalchemy.orm import relationship
from src.models.base import BaseModel, get_utc_now

class Consent(BaseModel):
    __tablename__ = "consent"

    patient_id = Column(String(36), ForeignKey("patient.id"), nullable=False, index=True)
    requester_project_id = Column(String(36), ForeignKey("research_project.id"), nullable=False, index=True)
    purpose = Column(String, nullable=False)
    scope_json = Column(JSON, nullable=False)
    access_mode = Column(String(50), default="DE_IDENTIFIED", nullable=False)
    valid_from = Column(DateTime(timezone=True), default=get_utc_now, nullable=False)
    valid_until = Column(DateTime(timezone=True), nullable=False, index=True)
    status = Column(String(50), default="GRANTED", nullable=False, index=True)
    granted_at = Column(DateTime(timezone=True), default=get_utc_now, nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    chain_tx_hash = Column(String(66), nullable=True)

    __table_args__ = (
        CheckConstraint("valid_until > valid_from", name="check_consent_validity_window"),
    )

    patient = relationship("Patient", back_populates="consents")
    project = relationship("ResearchProject", back_populates="consents")

class AccessRequest(BaseModel):
    __tablename__ = "access_request"

    patient_id = Column(String(36), ForeignKey("patient.id"), nullable=False, index=True)
    requester_project_id = Column(String(36), ForeignKey("research_project.id"), nullable=False, index=True)
    requested_scope_json = Column(JSON, nullable=False)
    purpose = Column(String, nullable=False)
    status = Column(String(50), default="PENDING", nullable=False, index=True)
    requested_at = Column(DateTime(timezone=True), default=get_utc_now, nullable=False)
    decided_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("status IN ('PENDING', 'APPROVED', 'REJECTED')", name="check_access_request_status"),
    )

    patient = relationship("Patient", back_populates="access_requests")
    project = relationship("ResearchProject", back_populates="access_requests")

class AccessEvent(BaseModel):
    __tablename__ = "access_event"

    actor_user_id = Column(String(36), ForeignKey("app_user.id"), nullable=False, index=True)
    patient_id = Column(String(36), ForeignKey("patient.id"), nullable=True, index=True)
    resource_type = Column(String(100), nullable=False)
    resource_reference = Column(String(150), nullable=False)
    action = Column(String(50), nullable=False)
    decision = Column(String(20), nullable=False, index=True) # GRANTED or DENIED
    reason_code = Column(String(100), nullable=False)
    occurred_at = Column(DateTime(timezone=True), default=get_utc_now, nullable=False, index=True)
    request_id = Column(String(100), nullable=True)
    chain_tx_hash = Column(String(66), nullable=True)

    __table_args__ = (
        CheckConstraint("decision IN ('GRANTED', 'DENIED')", name="check_access_event_decision"),
    )

    actor = relationship("AppUser")

class BlockchainEvent(BaseModel):
    __tablename__ = "blockchain_event"

    event_type = Column(String(100), nullable=False, index=True)
    opaque_reference = Column(String(100), nullable=False, index=True)
    commitment_hash = Column(String(66), nullable=False)
    transaction_hash = Column(String(66), nullable=True, index=True)
    block_number = Column(BigInteger, nullable=True)
    status = Column(String(50), default="PENDING", nullable=False, index=True)

    __table_args__ = (
        CheckConstraint("status IN ('PENDING', 'CONFIRMED', 'FAILED', 'UNANCHORED')", name="check_chain_event_status"),
    )

class OutboxEvent(BaseModel):
    __tablename__ = "outbox_event"

    event_type = Column(String(100), nullable=False, index=True)
    aggregate_id = Column(String(100), nullable=False, index=True)
    payload_json = Column(JSON, nullable=False)
    status = Column(String(50), default="PENDING", nullable=False, index=True)
    attempt_count = Column(Integer, default=0, nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)
