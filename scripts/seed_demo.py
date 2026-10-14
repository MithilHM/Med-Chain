import sys
import os
import asyncio
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

# Add root and api service to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../services/api"))

from src.database import init_db, get_db_session
from src.services.auth import hash_password
from src.services.mongo import MongoDocumentService
from src.services.integrity import IntegrityService
from src.services.neo4j_sync import GraphSyncService
from src.models import (
    AppUser, Hospital, Doctor, Patient, ResearchOrganization, ResearchProject,
    Disease, Medication, SideEffect, LabTest, Visit, Diagnosis, Prescription,
    Treatment, LabResult, ObservedAdverseEvent, MedicalDocument, RecordIntegrity,
    InsuranceProvider, InsurancePolicy, InsuranceClaim, ClaimItem,
    Consent, AccessRequest
)

async def seed():
    print("[Seed] Initializing database schema...")
    await init_db()

    async with get_db_session() as db:
        print("[Seed] Seeding identity accounts...")
        default_pwd = hash_password("Password123!")

        # App Users
        admin_user = AppUser(email="admin@medchain.local", password_hash=default_pwd, role="admin")
        doctor_user = AppUser(email="doctor@medchain.local", password_hash=default_pwd, role="doctor")
        patient_user = AppUser(email="patient@medchain.local", password_hash=default_pwd, role="patient")
        researcher_user = AppUser(email="researcher@medchain.local", password_hash=default_pwd, role="researcher")
        analyst_user = AppUser(email="analyst@medchain.local", password_hash=default_pwd, role="insurance_analyst")

        db.add_all([admin_user, doctor_user, patient_user, researcher_user, analyst_user])
        await db.flush()

        # Hospitals
        hosp1 = Hospital(name="Metropolitan Academic Medical Center", region="North Central")
        hosp2 = Hospital(name="St. Jude Research Hospital", region="Downtown Metro")
        db.add_all([hosp1, hosp2])
        await db.flush()

        # Doctor profile
        doc1 = Doctor(
            user_id=doctor_user.id,
            hospital_id=hosp1.id,
            display_name="Dr. Sarah Chen, MD",
            specialty="Cardiovascular & Metabolic Medicine"
        )
        db.add(doc1)
        await db.flush()

        # Seed Primary Demo Patient
        demo_patient = Patient(
            user_id=patient_user.id,
            display_code="PT-100201",
            date_of_birth=date(1975, 6, 15),
            sex="M"
        )
        db.add(demo_patient)
        await db.flush()

        # Additional synthetic patients (for cohorting & research analytics)
        synthetic_patients = []
        for i in range(1, 16):
            pt = Patient(
                user_id=None,
                display_code=f"PT-10020{i+1}",
                date_of_birth=date(1960 + (i * 2) % 35, (i % 12) + 1, (i % 28) + 1),
                sex="F" if i % 2 == 0 else "M"
            )
            synthetic_patients.append(pt)
            db.add(pt)
        await db.flush()

        # Research Organization & Projects
        res_org = ResearchOrganization(name="Global Cardiometabolic Research Collaborative", organization_type="Academic Consortium")
        db.add(res_org)
        await db.flush()

        proj1 = ResearchProject(
            organization_id=res_org.id,
            title="Type 2 Diabetes & Vascular Outcomes Longitudinal Analysis",
            purpose="Evaluate longitudinal metabolic markers and drug associations across de-identified synthetic patient cohorts.",
            status="ACTIVE",
            created_by=researcher_user.id
        )
        proj2 = ResearchProject(
            organization_id=res_org.id,
            title="Antihypertensive Drug Exposure & Adverse Event Surveillance",
            purpose="Analyze reported adverse symptom associations and lab variability.",
            status="ACTIVE",
            created_by=researcher_user.id
        )
        db.add_all([proj1, proj2])
        await db.flush()

        # Clinical Catalog: Diseases
        d_dm2 = Disease(code="E11.9", name="Type 2 diabetes mellitus without complications", description="Chronic metabolic disorder characterized by hyperglycemia.")
        d_htn = Disease(code="I10", name="Essential (primary) hypertension", description="Elevated systemic arterial pressure.")
        d_hld = Disease(code="E78.5", name="Hyperlipidemia, unspecified", description="Elevated lipid and lipoprotein concentrations in systemic circulation.")
        d_cad = Disease(code="I25.10", name="Atherosclerotic heart disease", description="Native coronary artery disease with atherosclerotic plaque.")
        d_gerd = Disease(code="K21.9", name="Gastro-esophageal reflux disease", description="Gastric acid reflux without specified esophagitis.")
        db.add_all([d_dm2, d_htn, d_hld, d_cad, d_gerd])
        await db.flush()

        # Clinical Catalog: Medications
        m_met = Medication(code="RX-860975", name="Metformin Hydrochloride 500mg", generic_name="Metformin", drug_class="Biguanide")
        m_aml = Medication(code="RX-197361", name="Amlodipine Besylate 5mg", generic_name="Amlodipine", drug_class="Calcium Channel Blocker")
        m_lis = Medication(code="RX-311756", name="Lisinopril 10mg", generic_name="Lisinopril", drug_class="ACE Inhibitor")
        m_ato = Medication(code="RX-855332", name="Atorvastatin Calcium 20mg", generic_name="Atorvastatin", drug_class="HMG-CoA Reductase Inhibitor")
        m_emp = Medication(code="RX-897122", name="Empagliflozin 10mg", generic_name="Empagliflozin", drug_class="SGLT2 Inhibitor")
        db.add_all([m_met, m_aml, m_lis, m_ato, m_emp])
        await db.flush()

        # Clinical Catalog: Side Effects
        se_ede = SideEffect(code="SE-1001", name="Peripheral Edema", description="Fluid retention and swelling in lower extremities.")
        se_nau = SideEffect(code="SE-1002", name="Gastrointestinal Nausea", description="Abdominal upset or mild nausea.")
        se_cou = SideEffect(code="SE-1003", name="Persistent Dry Cough", description="Dry irritating cough typical of ACE inhibitors.")
        se_mya = SideEffect(code="SE-1004", name="Myalgia", description="Muscle ache and soreness associated with statin exposure.")
        se_hyp = SideEffect(code="SE-1005", name="Hypoglycemia", description="Abnormally low blood glucose levels.")
        db.add_all([se_ede, se_nau, se_cou, se_mya, se_hyp])
        await db.flush()

        # Clinical Catalog: Lab Tests
        lt_a1c = LabTest(code="LOINC-4548-4", name="Hemoglobin A1c", unit="%", reference_range_text="4.0 - 5.6")
        lt_cho = LabTest(code="LOINC-2093-3", name="Total Cholesterol", unit="mg/dL", reference_range_text="125 - 200")
        lt_glu = LabTest(code="LOINC-2345-7", name="Fasting Blood Glucose", unit="mg/dL", reference_range_text="70 - 99")
        lt_cre = LabTest(code="LOINC-2160-0", name="Serum Creatinine", unit="mg/dL", reference_range_text="0.7 - 1.3")
        db.add_all([lt_a1c, lt_cho, lt_glu, lt_cre])
        await db.flush()

        print("[Seed] Seeding clinical encounters and documents...")
        all_pts = [demo_patient] + synthetic_patients
        now_dt = datetime.now(timezone.utc)

        # Create encounters for demo patient
        v1 = Visit(
            patient_id=demo_patient.id,
            doctor_id=doc1.id,
            hospital_id=hosp1.id,
            visit_at=now_dt - timedelta(days=60),
            visit_type="Outpatient Consultation",
            summary_code="COMPREHENSIVE_EVAL"
        )
        db.add(v1)
        await db.flush()

        diag1 = Diagnosis(visit_id=v1.id, disease_id=d_dm2.id, severity="Moderate", status="Active")
        diag2 = Diagnosis(visit_id=v1.id, disease_id=d_htn.id, severity="Mild", status="Active")
        db.add_all([diag1, diag2])

        presc1 = Prescription(
            visit_id=v1.id,
            medication_id=m_met.id,
            start_date=date.today() - timedelta(days=60),
            dose_text="500 mg",
            frequency_text="Twice daily with meals",
            prescribed_by=doc1.id
        )
        presc2 = Prescription(
            visit_id=v1.id,
            medication_id=m_aml.id,
            start_date=date.today() - timedelta(days=60),
            dose_text="5 mg",
            frequency_text="Once daily in the morning",
            prescribed_by=doc1.id
        )
        db.add_all([presc1, presc2])

        treat1 = Treatment(
            visit_id=v1.id,
            treatment_type="Pharmacotherapy & Lifestyle Counseling",
            description_code="TX-DIABETES-MGMT",
            start_date=date.today() - timedelta(days=60),
            outcome_status="IN_PROGRESS"
        )
        db.add(treat1)

        lr1 = LabResult(visit_id=v1.id, lab_test_id=lt_a1c.id, result_value=Decimal("7.4"), is_abnormal=True)
        lr2 = LabResult(visit_id=v1.id, lab_test_id=lt_glu.id, result_value=Decimal("142.0"), is_abnormal=True)
        db.add_all([lr1, lr2])

        ae1 = ObservedAdverseEvent(
            patient_id=demo_patient.id,
            prescription_id=presc2.id,
            side_effect_id=se_ede.id,
            severity="Mild",
            outcome="RESOLVING",
            evidence_quality="OBSERVED_ASSOCIATION"
        )
        db.add(ae1)
        await db.flush()

        # Seed clinical note in MongoDB & PostgreSQL record integrity commitment
        import uuid
        mongo_doc_id = str(uuid.uuid4())
        doc_content = (
            "PATIENT VISIT NOTE:\n"
            "51-year-old male with confirmed Type 2 Diabetes Mellitus and stage-1 hypertension. "
            "Patient reports adherence to Metformin 500mg BID and Amlodipine 5mg QD. "
            "Mild dependent bilateral ankle edema observed, likely secondary to dihydropyridine calcium channel blockade. "
            "HbA1c elevated at 7.4%. Advised low-sodium diabetic diet and follow-up in 8 weeks."
        )
        raw_doc = {
            "_id": mongo_doc_id,
            "patient_id": demo_patient.id,
            "visit_id": v1.id,
            "document_type": "clinical_note",
            "title": "Comprehensive Cardiometabolic Assessment",
            "content": doc_content,
            "structured_extract": {"vitals": {"bp": "138/88", "pulse": 74}, "assessment": "T2D + HTN"},
            "created_at": (now_dt - timedelta(days=60)).isoformat(),
            "created_by": doctor_user.id,
            "version": 1
        }
        await MongoDocumentService.insert_document(raw_doc)

        commitment_hash, salt = IntegrityService.create_commitment_for_doc(raw_doc)
        med_doc = MedicalDocument(
            patient_id=demo_patient.id,
            visit_id=v1.id,
            document_type="clinical_note",
            mongo_document_id=mongo_doc_id,
            storage_status="STORED",
            created_by=doctor_user.id
        )
        db.add(med_doc)
        await db.flush()

        rec_integrity = RecordIntegrity(
            medical_document_id=med_doc.id,
            record_version=1,
            commitment_hash=commitment_hash,
            algorithm="SHA256_SALTED",
            salt=salt,
            verified_at=now_dt,
            verification_status="VERIFIED_MATCH"
        )
        db.add(rec_integrity)

        # Seed encounters for remaining synthetic patients
        for idx, pt in enumerate(synthetic_patients):
            v = Visit(
                patient_id=pt.id,
                doctor_id=doc1.id,
                hospital_id=hosp1.id,
                visit_at=now_dt - timedelta(days=(idx * 7) + 5),
                visit_type="Routine Chronic Follow-up",
                summary_code="FOLLOWUP"
            )
            db.add(v)
            await db.flush()

            # Assign diseases
            assigned_diseases = [d_dm2, d_htn] if idx % 2 == 0 else [d_hld, d_cad]
            for dis in assigned_diseases:
                db.add(Diagnosis(visit_id=v.id, disease_id=dis.id, severity="Moderate", status="Active"))

            # Assign meds
            assigned_med = m_met if idx % 2 == 0 else m_ato
            pr = Prescription(
                visit_id=v.id,
                medication_id=assigned_med.id,
                start_date=date.today() - timedelta(days=30),
                dose_text="Standard",
                frequency_text="Daily",
                prescribed_by=doc1.id
            )
            db.add(pr)

            # Assign labs
            db.add(LabResult(visit_id=v.id, lab_test_id=lt_a1c.id, result_value=Decimal(str(6.0 + (idx % 4))), is_abnormal=(idx % 2 == 0)))

        await db.flush()

        print("[Seed] Seeding Insurance policies, claims, and explainable anomalies...")
        ins_prov = InsuranceProvider(name="National Anthem Healthcare Alliance", provider_code="NAHA-808")
        db.add(ins_prov)
        await db.flush()

        policy = InsurancePolicy(
            patient_id=demo_patient.id,
            provider_id=ins_prov.id,
            policy_reference="POL-778219-GOLD",
            coverage_type="Comprehensive Preferred PPO",
            valid_from=date(2024, 1, 1),
            valid_until=date(2027, 12, 31),
            status="ACTIVE"
        )
        db.add(policy)
        await db.flush()

        # Claim 1: Clean approved claim
        claim1 = InsuranceClaim(
            policy_id=policy.id,
            visit_id=v1.id,
            submitted_at=now_dt - timedelta(days=58),
            claimed_amount=Decimal("450.00"),
            approved_amount=Decimal("380.00"),
            status="APPROVED",
            review_flag=False
        )
        db.add(claim1)
        await db.flush()

        item1 = ClaimItem(
            claim_id=claim1.id,
            treatment_id=treat1.id,
            item_code="CPT-99214",
            description="Outpatient physician visit, moderate complexity",
            quantity=1,
            unit_cost=Decimal("250.00"),
            line_amount=Decimal("250.00")
        )
        item2 = ClaimItem(
            claim_id=claim1.id,
            treatment_id=None,
            item_code="CPT-83036",
            description="Hemoglobin A1c quantitative assay",
            quantity=1,
            unit_cost=Decimal("200.00"),
            line_amount=Decimal("200.00")
        )
        db.add_all([item1, item2])

        # Claim 2: Seeded duplicate item anomaly for human review
        claim2 = InsuranceClaim(
            policy_id=policy.id,
            visit_id=v1.id,
            submitted_at=now_dt - timedelta(days=2),
            claimed_amount=Decimal("1200.00"),
            approved_amount=Decimal("0.00"),
            status="UNDER_REVIEW",
            review_flag=True,
            review_reason="Potential duplicate service items: Multiple identical billing codes (CPT-99214) submitted on same encounter."
        )
        db.add(claim2)
        await db.flush()

        item2_a = ClaimItem(
            claim_id=claim2.id,
            treatment_id=treat1.id,
            item_code="CPT-99214",
            description="Outpatient physician visit, moderate complexity",
            quantity=1,
            unit_cost=Decimal("600.00"),
            line_amount=Decimal("600.00")
        )
        item2_b = ClaimItem(
            claim_id=claim2.id,
            treatment_id=treat1.id,
            item_code="CPT-99214",
            description="Outpatient physician visit, moderate complexity [Duplicate]",
            quantity=1,
            unit_cost=Decimal("600.00"),
            line_amount=Decimal("600.00")
        )
        db.add_all([item2_a, item2_b])

        print("[Seed] Seeding Research consent and access requests...")
        # Access Request 1 (Pending review by patient)
        req1 = AccessRequest(
            patient_id=demo_patient.id,
            requester_project_id=proj2.id,
            requested_scope_json=["aggregate_diagnoses", "medication_history", "adverse_events"],
            purpose="Analyze cardiovascular medication tolerance and real-world reported symptom clusters.",
            status="PENDING",
            requested_at=now_dt - timedelta(hours=6)
        )
        db.add(req1)

        # Pre-seed active Consent for Project 1 (allows researcher to query immediately; can be revoked in demo)
        consent1 = Consent(
            patient_id=demo_patient.id,
            requester_project_id=proj1.id,
            purpose=proj1.purpose,
            scope_json=["aggregate_diagnoses", "medication_history", "lab_summaries", "deidentified_cohort"],
            access_mode="DE_IDENTIFIED",
            valid_from=now_dt - timedelta(days=10),
            valid_until=now_dt + timedelta(days=90),
            status="GRANTED",
            granted_at=now_dt - timedelta(days=10),
            chain_tx_hash="unanchored-seed-grant-01"
        )
        db.add(consent1)

        # Also add consents for several synthetic patients to enable rich aggregate research queries
        for pt in synthetic_patients[:10]:
            c = Consent(
                patient_id=pt.id,
                requester_project_id=proj1.id,
                purpose=proj1.purpose,
                scope_json=["aggregate_diagnoses", "medication_history", "lab_summaries", "deidentified_cohort"],
                access_mode="DE_IDENTIFIED",
                valid_from=now_dt - timedelta(days=10),
                valid_until=now_dt + timedelta(days=90),
                status="GRANTED",
                granted_at=now_dt - timedelta(days=10),
                chain_tx_hash=f"unanchored-seed-pt-{pt.display_code}"
            )
            db.add(c)

        await db.commit()
        print("[Seed] Relational and document seed completed.")

        print("[Seed] Building initial Neo4j / Graph projection...")
        graph_status = await GraphSyncService.rebuild_graph(db)
        print(f"[Seed] Graph synchronization complete: {graph_status}")

    print("\n=======================================================")
    print(" DEMO SEED COMPLETED SUCCESSFULLY")
    print(" Demo Users:")
    print(" - Patient:            patient@medchain.local     (Password123!)")
    print(" - Doctor:             doctor@medchain.local      (Password123!)")
    print(" - Researcher:         researcher@medchain.local  (Password123!)")
    print(" - Insurance Analyst:  analyst@medchain.local     (Password123!)")
    print(" - Administrator:      admin@medchain.local       (Password123!)")
    print("=======================================================\n")

if __name__ == "__main__":
    asyncio.run(seed())
