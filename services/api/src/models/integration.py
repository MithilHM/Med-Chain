"""Hospital integration, identity matching, and access-relationship models.

These tables support real clinical feeds:
- PatientIdentifier: identifiers issued by an assigning authority (MRN, national ID).
  Patient matching uses (system, value), never a bare display code.
- CareTeamAssignment: explicit clinician-to-patient relationships, created by ADT feeds
  or onboarding. Doctor access no longer depends only on a historical visit row.
- EmergencyAccessGrant: time-boxed break-the-glass access that the access check honors,
  with a mandatory post-hoc compliance review.
- InboundMessage: an idempotent ledger of every inbound HL7/FHIR message, with an
  encrypted copy of the raw payload for replay and investigation.
"""
from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, Text, JSON, ForeignKey, CheckConstraint, UniqueConstraint, Index,
)
from sqlalchemy.orm import relationship
from src.models.base import BaseModel, get_utc_now


class PatientIdentifier(BaseModel):
    __tablename__ = "patient_identifier"

    patient_id = Column(String(36), ForeignKey("patient.id", ondelete="CASCADE"), nullable=False, index=True)
    system = Column(String(150), nullable=False)  # assigning authority, e.g. "urn:oid:1.2.3" or "CITYHOSP"
    value = Column(String(100), nullable=False)
    identifier_type = Column(String(20), nullable=False, default="MR")

    __table_args__ = (
        UniqueConstraint("system", "value", name="uq_patient_identifier_system_value"),
    )

    patient = relationship("Patient")


class CareTeamAssignment(BaseModel):
    __tablename__ = "care_team_assignment"

    patient_id = Column(String(36), ForeignKey("patient.id", ondelete="CASCADE"), nullable=False, index=True)
    doctor_id = Column(String(36), ForeignKey("doctor.id", ondelete="CASCADE"), nullable=False, index=True)
    relationship_type = Column(String(30), nullable=False, default="ATTENDING")
    source = Column(String(30), nullable=False, default="MANUAL")
    active_from = Column(DateTime(timezone=True), default=get_utc_now, nullable=False)
    active_until = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(String(36), ForeignKey("app_user.id"), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "relationship_type IN ('ATTENDING', 'CONSULTING', 'REFERRING', 'ADMITTING', 'PRIMARY_CARE')",
            name="check_care_team_relationship",
        ),
        CheckConstraint("source IN ('MANUAL', 'HL7_ADT', 'FHIR', 'ONBOARDING')", name="check_care_team_source"),
        CheckConstraint("active_until IS NULL OR active_until > active_from", name="check_care_team_window"),
        Index("ix_care_team_patient_doctor", "patient_id", "doctor_id"),
    )


class EmergencyAccessGrant(BaseModel):
    __tablename__ = "emergency_access_grant"

    user_id = Column(String(36), ForeignKey("app_user.id"), nullable=False, index=True)
    patient_id = Column(String(36), ForeignKey("patient.id"), nullable=False, index=True)
    justification = Column(String(2000), nullable=False)
    granted_at = Column(DateTime(timezone=True), default=get_utc_now, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    review_status = Column(String(30), nullable=False, default="PENDING_REVIEW", index=True)
    reviewed_by = Column(String(36), ForeignKey("app_user.id"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_note = Column(String(2000), nullable=True)

    __table_args__ = (
        CheckConstraint("expires_at > granted_at", name="check_emergency_window"),
        CheckConstraint(
            "review_status IN ('PENDING_REVIEW', 'APPROPRIATE', 'INAPPROPRIATE')",
            name="check_emergency_review_status",
        ),
    )


class InboundMessage(BaseModel):
    __tablename__ = "inbound_message"

    source_system = Column(String(100), nullable=False)
    message_control_id = Column(String(100), nullable=False)
    protocol = Column(String(20), nullable=False, default="HL7V2")
    message_type = Column(String(30), nullable=False, index=True)  # e.g. ADT^A01, ORU^R01
    received_at = Column(DateTime(timezone=True), default=get_utc_now, nullable=False, index=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(30), nullable=False, default="RECEIVED", index=True)
    error_detail = Column(String(2000), nullable=True)
    raw_sha256 = Column(String(64), nullable=False)
    raw_encrypted = Column(Text, nullable=False)
    patient_id = Column(String(36), ForeignKey("patient.id"), nullable=True, index=True)
    attempt_count = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("source_system", "message_control_id", name="uq_inbound_message_control_id"),
        CheckConstraint(
            "status IN ('RECEIVED', 'PROCESSED', 'REJECTED', 'NEEDS_REVIEW')",
            name="check_inbound_message_status",
        ),
        CheckConstraint("protocol IN ('HL7V2', 'FHIR')", name="check_inbound_message_protocol"),
    )


class LoginAttempt(BaseModel):
    """Sign-in attempts per client, shared by every API replica (rate limiting)."""
    __tablename__ = "login_attempt"

    client_key = Column(String(100), nullable=False)
    attempted_at = Column(DateTime(timezone=True), default=get_utc_now, nullable=False)
    succeeded = Column(Boolean, nullable=False, default=False)

    __table_args__ = (Index("ix_login_attempt_client_time", "client_key", "attempted_at"),)


class PatientMergeRequest(BaseModel):
    """A duplicate-record merge proposed by ADT^A40 or an operator. Merges always need human approval."""
    __tablename__ = "patient_merge_request"

    surviving_patient_id = Column(String(36), ForeignKey("patient.id"), nullable=False, index=True)
    retiring_patient_id = Column(String(36), ForeignKey("patient.id"), nullable=False, index=True)
    source_message_id = Column(String(36), ForeignKey("inbound_message.id"), nullable=True)
    reason = Column(String(500), nullable=False)
    status = Column(String(20), nullable=False, default="PENDING", index=True)
    requested_by = Column(String(36), ForeignKey("app_user.id"), nullable=True)
    decided_by = Column(String(36), ForeignKey("app_user.id"), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    decision_note = Column(String(2000), nullable=True)
    moved_counts = Column(JSON, nullable=True)

    __table_args__ = (
        CheckConstraint("status IN ('PENDING', 'APPROVED', 'REJECTED')", name="check_merge_request_status"),
        CheckConstraint("surviving_patient_id <> retiring_patient_id", name="check_merge_distinct_patients"),
    )


class OperationalAlert(BaseModel):
    """Alert lifecycle (open -> resolved). Alert text never contains patient data."""
    __tablename__ = "operational_alert"

    alert_key = Column(String(100), nullable=False, index=True)
    severity = Column(String(20), nullable=False)
    summary = Column(String(500), nullable=False)
    status = Column(String(20), nullable=False, default="OPEN", index=True)
    first_seen_at = Column(DateTime(timezone=True), default=get_utc_now, nullable=False)
    last_seen_at = Column(DateTime(timezone=True), default=get_utc_now, nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    notified_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("severity IN ('critical', 'warning', 'info')", name="check_alert_severity"),
        CheckConstraint("status IN ('OPEN', 'RESOLVED')", name="check_alert_status"),
    )
