from sqlalchemy import Column, String, Boolean, Date, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.orm import relationship
from src.models.base import BaseModel, get_utc_now

class AppUser(BaseModel):
    __tablename__ = "app_user"

    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=get_utc_now, onupdate=get_utc_now, nullable=False)

    __table_args__ = (
        CheckConstraint("role IN ('patient', 'doctor', 'researcher', 'insurance_analyst', 'admin')", name="check_user_role"),
    )

    patient_profile = relationship("Patient", back_populates="user", uselist=False)
    doctor_profile = relationship("Doctor", back_populates="user", uselist=False)

class Hospital(BaseModel):
    __tablename__ = "hospital"

    name = Column(String(150), nullable=False)
    region = Column(String(100), nullable=False)

    doctors = relationship("Doctor", back_populates="hospital")
    visits = relationship("Visit", back_populates="hospital")

class Doctor(BaseModel):
    __tablename__ = "doctor"

    user_id = Column(String(36), ForeignKey("app_user.id", ondelete="CASCADE"), unique=True, nullable=False)
    hospital_id = Column(String(36), ForeignKey("hospital.id"), nullable=False)
    display_name = Column(String(100), nullable=False)
    specialty = Column(String(100), nullable=False)

    user = relationship("AppUser", back_populates="doctor_profile")
    hospital = relationship("Hospital", back_populates="doctors")
    visits = relationship("Visit", back_populates="doctor")

class Patient(BaseModel):
    __tablename__ = "patient"

    user_id = Column(String(36), ForeignKey("app_user.id", ondelete="SET NULL"), unique=True, nullable=True)
    display_code = Column(String(50), unique=True, nullable=False, index=True)
    date_of_birth = Column(Date, nullable=False)
    sex = Column(String(20), nullable=False)

    __table_args__ = (
        CheckConstraint("sex IN ('M', 'F', 'O')", name="check_patient_sex"),
    )

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
