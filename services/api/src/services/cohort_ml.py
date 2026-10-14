import logging
from typing import Dict, Any, List
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models import (
    Patient, Visit, Diagnosis, Disease, Prescription, Medication,
    LabResult, Cohort, CohortMembership, AnalyticsRun
)

logger = logging.getLogger("medchain.cohort_ml")

class CohortMLService:
    @staticmethod
    async def run_clustering(
        db: AsyncSession,
        cohort_name: str,
        k: int,
        creator_user_id: str,
        features: List[str],
        random_state: int = 42
    ) -> Dict[str, Any]:
        """
        Executes unsupervised K-Means clustering on de-identified synthetic patient features.
        Zero direct identifiers are included in the feature matrix.
        """
        # Fetch patients
        patients = (await db.execute(select(Patient))).scalars().all()
        if not patients:
            raise ValueError("No patient records found to cluster.")

        diseases = (await db.execute(select(Disease))).scalars().all()
        medications = (await db.execute(select(Medication))).scalars().all()
        disease_codes = [d.code for d in diseases]
        med_codes = [m.code for m in medications]

        patient_rows = []
        patient_id_map = []

        now_year = datetime.now().year

        for p in patients:
            # Build feature vector
            birth_year = p.date_of_birth.year if hasattr(p.date_of_birth, "year") else 1980
            approx_age = now_year - birth_year

            # Fetch patient visits
            visits = (await db.execute(select(Visit).where(Visit.patient_id == p.id))).scalars().all()
            visit_ids = [v.id for v in visits]

            diag_counts = {f"d_{c}": 0 for c in disease_codes}
            med_counts = {f"m_{c}": 0 for c in med_codes}
            abnormal_labs = 0

            if visit_ids:
                diags = (await db.execute(select(Diagnosis).where(Diagnosis.visit_id.in_(visit_ids)))).scalars().all()
                for dg in diags:
                    disease_obj = next((d for d in diseases if d.id == dg.disease_id), None)
                    if disease_obj and f"d_{disease_obj.code}" in diag_counts:
                        diag_counts[f"d_{disease_obj.code}"] += 1

                prescs = (await db.execute(select(Prescription).where(Prescription.visit_id.in_(visit_ids)))).scalars().all()
                for pr in prescs:
                    med_obj = next((m for m in medications if m.id == pr.medication_id), None)
                    if med_obj and f"m_{med_obj.code}" in med_counts:
                        med_counts[f"m_{med_obj.code}"] += 1

                labs = (await db.execute(select(LabResult).where(LabResult.visit_id.in_(visit_ids)))).scalars().all()
                abnormal_labs = sum(1 for l in labs if l.is_abnormal)

            row = {"age": approx_age, "abnormal_labs": abnormal_labs, "visit_count": len(visits)}
            row.update(diag_counts)
            row.update(med_counts)

            patient_rows.append(row)
            patient_id_map.append(p.id)

        df = pd.DataFrame(patient_rows)

        # Scale features
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(df)

        # Clamp k to number of samples if smaller
        effective_k = min(k, len(patient_id_map))
        kmeans = KMeans(n_clusters=effective_k, random_state=random_state, n_init=10)
        cluster_labels = kmeans.fit_predict(X_scaled)

        # Store Cohort record
        import uuid
        run_id = str(uuid.uuid4())
        cohort = Cohort(
            name=cohort_name,
            description="Synthetic exploratory cohort generated via K-Means",
            created_by=creator_user_id,
            feature_definition_json={"features": features, "k": effective_k, "random_state": random_state},
            algorithm="K-Means"
        )
        db.add(cohort)
        await db.flush()

        # Store memberships
        for pt_id, label in zip(patient_id_map, cluster_labels):
            membership = CohortMembership(
                cohort_id=cohort.id,
                patient_id=pt_id,
                cluster_label=int(label),
                run_id=run_id
            )
            db.add(membership)

        # Summarize clusters
        cluster_summaries = []
        for c_idx in range(effective_k):
            indices = [i for i, lbl in enumerate(cluster_labels) if lbl == c_idx]
            sub_df = df.iloc[indices]
            
            # Find top diagnoses
            top_d = []
            for c in disease_codes:
                if sub_df[f"d_{c}"].sum() > 0:
                    d_obj = next((d for d in diseases if d.code == c), None)
                    if d_obj:
                        top_d.append(d_obj.name)

            # Find top meds
            top_m = []
            for c in med_codes:
                if sub_df[f"m_{c}"].sum() > 0:
                    m_obj = next((m for m in medications if m.code == c), None)
                    if m_obj:
                        top_m.append(m_obj.name)

            cluster_summaries.append({
                "cluster_label": c_idx,
                "cluster_name": f"Sub-cohort {c_idx + 1}",
                "patient_count": len(indices),
                "avg_age": round(float(sub_df["age"].mean()), 1) if not sub_df.empty else 0.0,
                "top_diagnoses": top_d[:3],
                "top_medications": top_m[:3]
            })

        analytics_run = AnalyticsRun(
            run_type="COHORT_KMEANS",
            parameters_json={"k": effective_k, "random_state": random_state, "cohort_name": cohort_name},
            status="COMPLETED",
            summary_json={"clusters": cluster_summaries, "inertia": float(kmeans.inertia_)}
        )
        db.add(analytics_run)
        await db.commit()

        return {
            "id": cohort.id,
            "name": cohort.name,
            "algorithm": "K-Means",
            "created_at": cohort.created_at,
            "k": effective_k,
            "inertia": float(kmeans.inertia_),
            "clusters": cluster_summaries,
            "disclaimer": "Exploratory synthetic pattern only. Not for clinical diagnosis or causal inference."
        }
