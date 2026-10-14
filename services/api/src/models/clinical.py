from sqlalchemy import Column, String, Boolean, Date, DateTime, Numeric, ForeignKey, CheckConstraint
from sqlalchemy.orm import relationship
from src.models.base import BaseModel, get_utc_now

class Visit(BaseModel):
    __tablename__ = "visit"

    patient_id = Column(String(36), ForeignKey("patient.id"), nullable=False, index=True)
    doctor_id = Column(String(36), ForeignKey("doctor.id"), nullable=False, index=True)
    hospital_id = Column(String(36), ForeignKey("hospital.id"), nullable=False)
    visit_at = Column(DateTime(timezone=True), default=get_utc_now, nullable=False, index=True)
    visit_type = Column(String(50), nullable=False)
    summary_code = Column(String(50), nullable=True)

    patient = relationship("Patient", back_populates="visits")
    doctor = relationship("Doctor", back_populates="visits")
    hospital = relationship("Hospital", back_populates="visits")
    diagnoses = relationship("Diagnosis", back_populates="visit", cascade="all, delete-orphan")
    prescriptions = relationship("Prescription", back_populates="visit", cascade="all, delete-orphan")
    treatments = relationship("Treatment", back_populates="visit", cascade="all, delete-orphan")
    lab_results = relationship("LabResult", back_populates="visit", cascade="all, delete-orphan")
    documents = relationship("MedicalDocument", back_populates="visit")
    claims = relationship("InsuranceClaim", back_populates="visit")

class Disease(BaseModel):
    __tablename__ = "disease"

    code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(150), nullable=False, index=True)
    description = Column(String, nullable=True)

    diagnoses = relationship("Diagnosis", back_populates="disease")

class Diagnosis(BaseModel):
    __tablename__ = "diagnosis"

    visit_id = Column(String(36), ForeignKey("visit.id", ondelete="CASCADE"), nullable=False, index=True)
    disease_id = Column(String(36), ForeignKey("disease.id"), nullable=False, index=True)
    diagnosed_at = Column(DateTime(timezone=True), default=get_utc_now, nullable=False)
    severity = Column(String(50), nullable=False)
    status = Column(String(50), default="Active", nullable=False)
    notes_reference = Column(String(100), nullable=True)

    __table_args__ = (
        CheckConstraint("severity IN ('Mild', 'Moderate', 'Severe', 'Critical')", name="check_diag_severity"),
    )

    visit = relationship("Visit", back_populates="diagnoses")
    disease = relationship("Disease", back_populates="diagnoses")

class Medication(BaseModel):
    __tablename__ = "medication"

    code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(150), nullable=False, index=True)
    generic_name = Column(String(150), nullable=False)
    drug_class = Column(String(100), nullable=False, index=True)

    prescriptions = relationship("Prescription", back_populates="medication")

class Prescription(BaseModel):
    __tablename__ = "prescription"

    visit_id = Column(String(36), ForeignKey("visit.id", ondelete="CASCADE"), nullable=False, index=True)
    medication_id = Column(String(36), ForeignKey("medication.id"), nullable=False, index=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    dose_text = Column(String(100), nullable=False)
    frequency_text = Column(String(100), nullable=False)
    prescribed_by = Column(String(36), ForeignKey("doctor.id"), nullable=False)

    __table_args__ = (
        CheckConstraint("end_date IS NULL OR end_date >= start_date", name="check_prescription_dates"),
    )

    visit = relationship("Visit", back_populates="prescriptions")
    medication = relationship("Medication", back_populates="prescriptions")
    doctor = relationship("Doctor")
    adverse_events = relationship("ObservedAdverseEvent", back_populates="prescription")

class Treatment(BaseModel):
    __tablename__ = "treatment"

    visit_id = Column(String(36), ForeignKey("visit.id", ondelete="CASCADE"), nullable=False, index=True)
    treatment_type = Column(String(100), nullable=False)
    description_code = Column(String(100), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    outcome_status = Column(String(50), nullable=False)

    __table_args__ = (
        CheckConstraint("end_date IS NULL OR end_date >= start_date", name="check_treatment_dates"),
    )

    visit = relationship("Visit", back_populates="treatments")
    claim_items = relationship("ClaimItem", back_populates="treatment")

class LabTest(BaseModel):
    __tablename__ = "lab_test"

    code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(150), nullable=False)
    unit = Column(String(50), nullable=False)
    reference_range_text = Column(String(100), nullable=False)

    lab_results = relationship("LabResult", back_populates="lab_test")

class LabResult(BaseModel):
    __tablename__ = "lab_result"

    visit_id = Column(String(36), ForeignKey("visit.id", ondelete="CASCADE"), nullable=False, index=True)
    lab_test_id = Column(String(36), ForeignKey("lab_test.id"), nullable=False, index=True)
    result_value = Column(Numeric(10, 3), nullable=False)
    result_text = Column(String(200), nullable=True)
    measured_at = Column(DateTime(timezone=True), default=get_utc_now, nullable=False)
    is_abnormal = Column(Boolean, default=False, nullable=False)

    visit = relationship("Visit", back_populates="lab_results")
    lab_test = relationship("LabTest", back_populates="lab_results")

class SideEffect(BaseModel):
    __tablename__ = "side_effect"

    code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(150), nullable=False, index=True)
    description = Column(String, nullable=True)

    adverse_events = relationship("ObservedAdverseEvent", back_populates="side_effect")

class ObservedAdverseEvent(BaseModel):
    __tablename__ = "observed_adverse_event"

    patient_id = Column(String(36), ForeignKey("patient.id"), nullable=False, index=True)
    prescription_id = Column(String(36), ForeignKey("prescription.id"), nullable=True)
    side_effect_id = Column(String(36), ForeignKey("side_effect.id"), nullable=False, index=True)
    reported_at = Column(DateTime(timezone=True), default=get_utc_now, nullable=False)
    severity = Column(String(50), nullable=False)
    outcome = Column(String(100), nullable=False)
    evidence_quality = Column(String(50), default="OBSERVED_ASSOCIATION", nullable=False)

    patient = relationship("Patient", back_populates="adverse_events")
    prescription = relationship("Prescription", back_populates="adverse_events")
    side_effect = relationship("SideEffect", back_populates="adverse_events")
