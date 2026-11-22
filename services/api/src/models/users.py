import json
import logging

from sqlalchemy import (
    Column, String, Boolean, Date, DateTime, Integer, BigInteger, Text, JSON, ForeignKey, CheckConstraint, false,
)
from sqlalchemy.orm import relationship
from src.models.base import BaseModel, get_utc_now

_logger = logging.getLogger("medchain.models")

class AppUser(BaseModel):
    __tablename__ = "app_user"

    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=get_utc_now, onupdate=get_utc_now, nullable=False)
    failed_login_count = Column(Integer, default=0, server_default="0", nullable=False)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    # Where the identity is managed: LOCAL password, hospital OIDC SSO, or SCIM-provisioned.
    auth_source = Column(String(20), default="LOCAL", server_default="LOCAL", nullable=False)
    # "<issuer>|<sub>" for SSO identities; stable even if the email changes.
    external_subject = Column(String(255), unique=True, nullable=True)
    # TOTP multi-factor authentication (secret encrypted at rest; recovery codes stored as hashes).
    mfa_enabled = Column(Boolean, default=False, server_default=false(), nullable=False)
    mfa_secret_encrypted = Column(Text, nullable=True)
    mfa_last_timestep = Column(BigInteger, nullable=True)
    mfa_recovery_hashes = Column(JSON, nullable=True)

    __table_args__ = (
        CheckConstraint("role IN ('patient', 'doctor', 'researcher', 'insurance_analyst', 'admin')", name="check_user_role"),
        CheckConstraint("auth_source IN ('LOCAL', 'OIDC', 'SCIM')", name="check_user_auth_source"),
    )

    patient_profile = relationship("Patient", back_populates="user", uselist=False)
    doctor_profile = relationship("Doctor", back_populates="user", uselist=False)
    insurance_analyst_profile = relationship("InsuranceAnalyst", back_populates="user", uselist=False, cascade="all, delete-orphan")
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")


class UserSession(BaseModel):
    __tablename__ = "user_session"

    user_id = Column(String(36), ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False, index=True)
    token_jti = Column(String(64), unique=True, nullable=False, index=True)
    is_revoked = Column(Boolean, default=False, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    user_agent = Column(String(255), nullable=True)
    ip_address = Column(String(45), nullable=True)

    user = relationship("AppUser", back_populates="sessions")

class Hospital(BaseModel):
    __tablename__ = "hospital"

    name = Column(String(150), nullable=False)
    region = Column(String(100), nullable=False)
    # Sending-facility code used by HL7 MSH-4 / PV1-3 to resolve the hospital.
    facility_code = Column(String(64), unique=True, nullable=True)

    doctors = relationship("Doctor", back_populates="hospital")
    visits = relationship("Visit", back_populates="hospital")

class Doctor(BaseModel):
    __tablename__ = "doctor"

    user_id = Column(String(36), ForeignKey("app_user.id", ondelete="CASCADE"), unique=True, nullable=False)
    hospital_id = Column(String(36), ForeignKey("hospital.id"), nullable=False)
    display_name = Column(String(100), nullable=False)
    specialty = Column(String(100), nullable=False)
    # Hospital provider number (e.g. NPI or staff ID) used by HL7 PV1-7 / FHIR Practitioner.
    external_provider_id = Column(String(64), unique=True, nullable=True)

    user = relationship("AppUser", back_populates="doctor_profile")
    hospital = relationship("Hospital", back_populates="doctors")
    visits = relationship("Visit", back_populates="doctor")

class Patient(BaseModel):
    __tablename__ = "patient"

    user_id = Column(String(36), ForeignKey("app_user.id", ondelete="SET NULL"), unique=True, nullable=True)
    display_code = Column(String(50), unique=True, nullable=False, index=True)
    date_of_birth = Column(Date, nullable=False)
    sex = Column(String(20), nullable=False)
    # Name is encrypted (AES-GCM, bound to the patient id). family_name_index is a keyed blind index
    # for exact-match search. Names are returned only to care roles and never to research APIs.
    name_encrypted = Column(Text, nullable=True)
    family_name_index = Column(String(64), nullable=True, index=True)
    # Duplicate-record reconciliation: a merged record is retained (read-only) and points at the survivor.
    record_status = Column(String(20), default="ACTIVE", server_default="ACTIVE", nullable=False)
    merged_into_id = Column(String(36), ForeignKey("patient.id"), nullable=True)

    __table_args__ = (
        CheckConstraint("sex IN ('M', 'F', 'O')", name="check_patient_sex"),
        CheckConstraint("record_status IN ('ACTIVE', 'MERGED')", name="check_patient_record_status"),
    )

    def set_name(self, given: str | None, family: str | None) -> None:
        from src.services.crypto import encrypt_text, name_blind_index
        given, family = (given or "").strip()[:100], (family or "").strip()[:100]
        if not given and not family:
            self.name_encrypted, self.family_name_index = None, None
            return
        if self.id is None:
            raise ValueError("Flush the patient before setting its name (the id binds the ciphertext).")
        self.name_encrypted = encrypt_text(json.dumps({"given": given, "family": family}), f"patient-name:{self.id}")
        self.family_name_index = name_blind_index(family)

    @property
    def name_parts(self) -> dict | None:
        if not self.name_encrypted:
            return None
        from src.services.crypto import decrypt_text
        try:
            return json.loads(decrypt_text(self.name_encrypted, f"patient-name:{self.id}"))
        except Exception:
            _logger.error("Could not decrypt name for patient %s", self.id)
            return None

    @property
    def display_name(self) -> str | None:
        parts = self.name_parts
        if not parts:
            return None
        family, given = parts.get("family", ""), parts.get("given", "")
        return f"{family.upper()}, {given}".strip(", ") if family else given or None

    user = relationship("AppUser", back_populates="patient_profile")
    visits = relationship("Visit", back_populates="patient")
    policies = relationship("InsurancePolicy", back_populates="patient")
    documents = relationship("MedicalDocument", back_populates="patient")
    consents = relationship("Consent", back_populates="patient")
    access_requests = relationship("AccessRequest", back_populates="patient")
    adverse_events = relationship("ObservedAdverseEvent", back_populates="patient")

class ResearchOrganization(BaseModel):
    __tablename__ = "research_organization"

    name = Column(String(150), nullable=False)
    organization_type = Column(String(100), nullable=False)

    projects = relationship("ResearchProject", back_populates="organization")

class ResearchProject(BaseModel):
    __tablename__ = "research_project"

    organization_id = Column(String(36), ForeignKey("research_organization.id"), nullable=False)
    title = Column(String(200), nullable=False)
    purpose = Column(String, nullable=False)
    status = Column(String(50), default="ACTIVE", nullable=False)
    created_by = Column(String(36), ForeignKey("app_user.id"), nullable=False)

    organization = relationship("ResearchOrganization", back_populates="projects")
    creator = relationship("AppUser")
    consents = relationship("Consent", back_populates="project")
    access_requests = relationship("AccessRequest", back_populates="project")
