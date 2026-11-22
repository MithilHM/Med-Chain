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
from src.services.privacy import MIN_RESEARCH_GROUP_SIZE

logger = logging.getLogger("medchain.cohort_ml")

def generate_patient_cohorts(patient_features_df: pd.DataFrame, n_clusters: int = 3):
    """
    Inputs a DataFrame containing patient clinical metrics:
    ['age', 'visit_frequency', 'hba1c_level', 'sys_bp', 'claim_cost']
    Outputs cluster assignments (Cohort IDs).
    """
    feature_cols = ['age', 'visit_frequency', 'hba1c_level', 'sys_bp', 'claim_cost']
    available_cols = [c for c in feature_cols if c in patient_features_df.columns]
    cols_to_use = available_cols if len(available_cols) > 0 else patient_features_df.select_dtypes(include=[np.number]).columns.tolist()
    X = patient_features_df[cols_to_use].values
    
    # Standardize feature matrix
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    # Fit K-Means
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    patient_features_df['cohort_id'] = kmeans.fit_predict(X_scaled)
    
    return patient_features_df, kmeans.cluster_centers_

class CohortMLService:
    @staticmethod
    async def run_clustering(
        db: AsyncSession,
        cohort_name: str,
        k: int,
        creator_user_id: str,
        project_id: str,
        patient_ids: List[str],
        features: List[str],
        random_state: int = 42
    ) -> Dict[str, Any]:
        """
        Executes unsupervised K-Means clustering on de-identified synthetic patient features.
        Zero direct identifiers are included in the feature matrix.
        """
        # The caller passes only patients with active consent for this project and scope.
        if len(set(patient_ids)) < MIN_RESEARCH_GROUP_SIZE:
            raise ValueError(
                f"At least {MIN_RESEARCH_GROUP_SIZE} consented patients are required for cohort analysis."
            )
        selected_features = set(features)
        patient_query = select(Patient.id)
        if "age_bracket" in selected_features:
            patient_query = select(Patient.id, Patient.date_of_birth)
        patient_records = (await db.execute(
            patient_query.where(Patient.id.in_(patient_ids)).order_by(Patient.id.asc())
        )).all()
        if not patient_records:
            raise ValueError("No patient records found to cluster.")

        diseases = (await db.execute(select(Disease).order_by(Disease.code.asc()))).scalars().all() if "diagnoses" in selected_features else []
        medications = (await db.execute(select(Medication).order_by(Medication.code.asc()))).scalars().all() if "medications" in selected_features else []
        disease_codes = [d.code for d in diseases]
        med_codes = [m.code for m in medications]

        patient_rows = []
        patient_id_map = []

        now_year = datetime.now().year

        for patient_record in patient_records:
            patient_id = patient_record.id
            # Build feature vector
            approx_age = None
            if "age_bracket" in selected_features:
                birth_date = patient_record.date_of_birth
                birth_year = birth_date.year if hasattr(birth_date, "year") else 1980
                approx_age = max(0, now_year - birth_year)

            # Fetch clinical activity only when one of its feature groups is selected.
            clinical_features = {"diagnoses", "medications", "lab_abnormalities"}
            visits = []
            if selected_features.intersection(clinical_features):
                visits = (await db.execute(select(Visit).where(Visit.patient_id == patient_id))).scalars().all()
            visit_ids = [v.id for v in visits]

            row = {}
            if "age_bracket" in selected_features:
                age_bands = {
                    "age_0_17": approx_age < 18,
                    "age_18_39": 18 <= approx_age < 40,
                    "age_40_64": 40 <= approx_age < 65,
                    "age_65_plus": approx_age >= 65,
                }
                row.update({key: int(in_band) for key, in_band in age_bands.items()})

            diag_counts = {f"d_{c}": 0 for c in disease_codes}
            med_counts = {f"m_{c}": 0 for c in med_codes}
            abnormal_labs = 0

            if visit_ids:
                if "diagnoses" in selected_features:
                    diags = (await db.execute(select(Diagnosis).where(Diagnosis.visit_id.in_(visit_ids)))).scalars().all()
                    for dg in diags:
                        disease_obj = next((d for d in diseases if d.id == dg.disease_id), None)
                        if disease_obj and f"d_{disease_obj.code}" in diag_counts:
                            diag_counts[f"d_{disease_obj.code}"] += 1

                if "medications" in selected_features:
                    prescs = (await db.execute(select(Prescription).where(Prescription.visit_id.in_(visit_ids)))).scalars().all()
                    for pr in prescs:
                        med_obj = next((m for m in medications if m.id == pr.medication_id), None)
                        if med_obj and f"m_{med_obj.code}" in med_counts:
                            med_counts[f"m_{med_obj.code}"] += 1

                if "lab_abnormalities" in selected_features:
                    labs = (await db.execute(select(LabResult).where(LabResult.visit_id.in_(visit_ids)))).scalars().all()
                    abnormal_labs = sum(1 for l in labs if l.is_abnormal)

            if "lab_abnormalities" in selected_features:
                row["abnormal_labs"] = abnormal_labs
            if "diagnoses" in selected_features:
                row.update(diag_counts)
            if "medications" in selected_features:
                row.update(med_counts)

            patient_rows.append(row)
            patient_id_map.append(patient_id)

        df = pd.DataFrame(patient_rows)

        # Scale features
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(df)

        # Clamp k to number of samples if smaller
        effective_k = min(k, len(patient_id_map))
        while True:
            kmeans = KMeans(n_clusters=effective_k, random_state=random_state, n_init=10)
            cluster_labels = kmeans.fit_predict(X_scaled)
            cluster_sizes = np.bincount(cluster_labels, minlength=effective_k)
            if cluster_sizes.min() >= MIN_RESEARCH_GROUP_SIZE or effective_k == 1:
                break
            effective_k -= 1

        # Store Cohort record
        import uuid
        run_id = str(uuid.uuid4())
        cohort = Cohort(
            name=cohort_name,
            description="Synthetic exploratory cohort generated via K-Means",
            created_by=creator_user_id,
            feature_definition_json={
                "features": features,
                "k": effective_k,
                "random_state": random_state,
                "project_id": project_id,
            },
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
                if (sub_df[f"d_{c}"] > 0).sum() >= MIN_RESEARCH_GROUP_SIZE:
                    d_obj = next((d for d in diseases if d.code == c), None)
                    if d_obj:
                        top_d.append(d_obj.name)

            # Find top meds
            top_m = []
            for c in med_codes:
                if (sub_df[f"m_{c}"] > 0).sum() >= MIN_RESEARCH_GROUP_SIZE:
                    m_obj = next((m for m in medications if m.code == c), None)
                    if m_obj:
                        top_m.append(m_obj.name)

            cluster_summaries.append({
                "cluster_label": c_idx,
                "cluster_name": f"Sub-cohort {c_idx + 1}",
                "patient_count": len(indices),
                "avg_age": round(float(sum(
                    sub_df[column].mean() * midpoint
                    for column, midpoint in (("age_0_17", 8.5), ("age_18_39", 28.5), ("age_40_64", 52), ("age_65_plus", 75))
                )), 1) if "age_bracket" in selected_features and not sub_df.empty else None,
                "top_diagnoses": top_d[:3],
                "top_medications": top_m[:3]
            })

        analytics_run = AnalyticsRun(
            run_type="COHORT_KMEANS",
            parameters_json={
                "k": effective_k,
                "random_state": random_state,
                "cohort_name": cohort_name,
                "cohort_id": cohort.id,
                "project_id": project_id,
                "features": features,
            },
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
            "disclaimer": "Exploratory synthetic pattern only. Not for clinical diagnosis or causal inference.",
            "features": features,
        }
