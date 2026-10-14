import sys
import os
import asyncio
from sqlalchemy import text

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../services/api"))

from src.database import get_db_session

async def run_showcase():
    print("=" * 70)
    print("   MEDCHAIN ADVANCED DBMS SHOWCASE QUERIES")
    print("=" * 70)

    async with get_db_session() as db:
        # 1. Complex Multi-Table Join across Clinical & Reference Domains
        print("\n--- 1. Multi-Table Join: Patient Encounter History with Diseases & Prescriptions ---")
        q1 = text("""
            SELECT 
                p.display_code AS patient_code,
                v.visit_at,
                d.name AS disease_name,
                diag.severity,
                m.name AS medication_name,
                pr.dose_text
            FROM patient p
            JOIN visit v ON v.patient_id = p.id
            JOIN diagnosis diag ON diag.visit_id = v.id
            JOIN disease d ON d.id = diag.disease_id
            JOIN prescription pr ON pr.visit_id = v.id
            JOIN medication m ON m.id = pr.medication_id
            ORDER BY v.visit_at DESC
            LIMIT 5;
        """)
        res1 = await db.execute(q1)
        for row in res1.mappings():
            print(dict(row))

        # 2. CTE and Subqueries: Disease Prevalence within High-Cost Policy Cohorts
        print("\n--- 2. CTE & Subquery: Diagnoses in Patients with High Insurance Claims ---")
        q2 = text("""
            WITH HighClaimPatients AS (
                SELECT pol.patient_id, SUM(c.claimed_amount) AS total_claimed
                FROM insurance_claim c
                JOIN insurance_policy pol ON pol.id = c.policy_id
                GROUP BY pol.patient_id
                HAVING SUM(c.claimed_amount) > 300
            )
            SELECT 
                hcp.patient_id,
                hcp.total_claimed,
                d.name AS disease_name,
                COUNT(diag.id) AS diagnosis_count
            FROM HighClaimPatients hcp
            JOIN visit v ON v.patient_id = hcp.patient_id
            JOIN diagnosis diag ON diag.visit_id = v.id
            JOIN disease d ON d.id = diag.disease_id
            GROUP BY hcp.patient_id, hcp.total_claimed, d.name
            ORDER BY hcp.total_claimed DESC;
        """)
        res2 = await db.execute(q2)
        for row in res2.mappings():
            print(dict(row))

        # 3. Window Function: Chronological Visit Rank and Cumulative Expenditure
        print("\n--- 3. Window Function: Chronological Visit Sequence & Cumulative Claims ---")
        q3 = text("""
            SELECT 
                c.id AS claim_id,
                pol.patient_id,
                c.submitted_at,
                c.claimed_amount,
                ROW_NUMBER() OVER (PARTITION BY pol.patient_id ORDER BY c.submitted_at ASC) as visit_seq_num,
                SUM(c.claimed_amount) OVER (PARTITION BY pol.patient_id ORDER BY c.submitted_at ASC) as cumulative_claimed
            FROM insurance_claim c
            JOIN insurance_policy pol ON pol.id = c.policy_id
            ORDER BY pol.patient_id, c.submitted_at ASC;
        """)
        res3 = await db.execute(q3)
        for row in res3.mappings():
            print(dict(row))

        # 4. Aggregates with GROUP BY & HAVING
        print("\n--- 4. Aggregates: Diseases with Multiple Active Diagnoses ---")
        q4 = text("""
            SELECT 
                d.code,
                d.name,
                COUNT(diag.id) as case_count
            FROM disease d
            JOIN diagnosis diag ON diag.disease_id = d.id
            WHERE diag.status = 'Active'
            GROUP BY d.code, d.name
            HAVING COUNT(diag.id) >= 1
            ORDER BY case_count DESC;
        """)
        res4 = await db.execute(q4)
        for row in res4.mappings():
            print(dict(row))

        # 5. Query Plan (EXPLAIN)
        print("\n--- 5. Query Plan (EXPLAIN) on Indexed Patient Lookup ---")
        q5 = text("EXPLAIN QUERY PLAN SELECT * FROM patient WHERE display_code = 'PT-100201';")
        res5 = await db.execute(q5)
        for row in res5.mappings():
            print(dict(row))

    print("\n" + "=" * 70)
    print("   ALL SQL SHOWCASE QUERIES EXECUTED SUCCESSFULLY")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    asyncio.run(run_showcase())
