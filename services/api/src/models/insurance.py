from sqlalchemy import Column, String, Integer, Boolean, Date, DateTime, Numeric, ForeignKey, CheckConstraint
from sqlalchemy.orm import relationship
from src.models.base import BaseModel, get_utc_now

class InsuranceProvider(BaseModel):
    __tablename__ = "insurance_provider"

    name = Column(String(150), nullable=False)
    provider_code = Column(String(50), unique=True, nullable=False, index=True)

    policies = relationship("InsurancePolicy", back_populates="provider")

class InsurancePolicy(BaseModel):
    __tablename__ = "insurance_policy"

    patient_id = Column(String(36), ForeignKey("patient.id"), nullable=False, index=True)
    provider_id = Column(String(36), ForeignKey("insurance_provider.id"), nullable=False, index=True)
    policy_reference = Column(String(100), unique=True, nullable=False, index=True)
    coverage_type = Column(String(100), nullable=False)
    valid_from = Column(Date, nullable=False)
    valid_until = Column(Date, nullable=False)
    status = Column(String(50), default="ACTIVE", nullable=False)

    __table_args__ = (
        CheckConstraint("valid_until >= valid_from", name="check_policy_validity_dates"),
    )

    patient = relationship("Patient", back_populates="policies")
    provider = relationship("InsuranceProvider", back_populates="policies")
    claims = relationship("InsuranceClaim", back_populates="policy")

class InsuranceClaim(BaseModel):
    __tablename__ = "insurance_claim"

    policy_id = Column(String(36), ForeignKey("insurance_policy.id"), nullable=False, index=True)
    visit_id = Column(String(36), ForeignKey("visit.id"), nullable=False, index=True)
    submitted_at = Column(DateTime(timezone=True), default=get_utc_now, nullable=False, index=True)
    claimed_amount = Column(Numeric(12, 2), nullable=False)
    approved_amount = Column(Numeric(12, 2), default=0.00, nullable=False)
    status = Column(String(50), default="SUBMITTED", nullable=False, index=True)
    review_flag = Column(Boolean, default=False, nullable=False, index=True)
    review_reason = Column(String, nullable=True)

    __table_args__ = (
        CheckConstraint("claimed_amount >= 0", name="check_claim_amount_non_negative"),
        CheckConstraint("approved_amount >= 0", name="check_approved_amount_non_negative"),
    )

    policy = relationship("InsurancePolicy", back_populates="claims")
    visit = relationship("Visit", back_populates="claims")
    items = relationship("ClaimItem", back_populates="claim", cascade="all, delete-orphan")

class ClaimItem(BaseModel):
    __tablename__ = "claim_item"

    claim_id = Column(String(36), ForeignKey("insurance_claim.id", ondelete="CASCADE"), nullable=False, index=True)
    treatment_id = Column(String(36), ForeignKey("treatment.id"), nullable=True)
    item_code = Column(String(50), nullable=False)
    description = Column(String(200), nullable=False)
    quantity = Column(Integer, default=1, nullable=False)
    unit_cost = Column(Numeric(12, 2), nullable=False)
    line_amount = Column(Numeric(12, 2), nullable=False)

    __table_args__ = (
        CheckConstraint("quantity > 0", name="check_item_quantity_positive"),
        CheckConstraint("unit_cost >= 0", name="check_unit_cost_non_negative"),
        CheckConstraint("line_amount >= 0", name="check_line_amount_non_negative"),
    )

    claim = relationship("InsuranceClaim", back_populates="items")
    treatment = relationship("Treatment", back_populates="claim_items")
