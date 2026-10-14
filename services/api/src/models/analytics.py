from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from src.models.base import BaseModel, get_utc_now

class Cohort(BaseModel):
    __tablename__ = "cohort"

    name = Column(String(150), nullable=False, index=True)
    description = Column(String, nullable=True)
    created_by = Column(String(36), ForeignKey("app_user.id"), nullable=False)
    feature_definition_json = Column(JSON, nullable=False)
    algorithm = Column(String(50), default="K-Means", nullable=False)

    creator = relationship("AppUser")
    memberships = relationship("CohortMembership", back_populates="cohort", cascade="all, delete-orphan")

class CohortMembership(BaseModel):
    __tablename__ = "cohort_membership"

    cohort_id = Column(String(36), ForeignKey("cohort.id", ondelete="CASCADE"), nullable=False, index=True)
    patient_id = Column(String(36), ForeignKey("patient.id"), nullable=False, index=True)
    cluster_label = Column(Integer, nullable=False, index=True)
    run_id = Column(String(36), nullable=False, index=True)

    cohort = relationship("Cohort", back_populates="memberships")
    patient = relationship("Patient")

class AnalyticsRun(BaseModel):
    __tablename__ = "analytics_run"

    run_type = Column(String(50), nullable=False, index=True)
    parameters_json = Column(JSON, nullable=False)
    status = Column(String(50), default="COMPLETED", nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), default=get_utc_now, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    summary_json = Column(JSON, nullable=False)
