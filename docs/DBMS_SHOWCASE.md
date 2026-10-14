# MedChain Advanced DBMS Showcase & Normalization Walkthrough

## 1. Relational Normalization Walkthrough (1NF -> 2NF -> 3NF)

To demonstrate foundational database principles, consider an unnormalized, flat spreadsheet record commonly found in legacy clinic exports:

### 1.1 Unnormalized Form (UNF)
```
PatientEncounterRecord = [
  PatientCode, PatientDOB, PatientSex, DoctorName, HospitalName, HospitalRegion,
  VisitDate, VisitType, DiseaseCodes (comma-separated), DiseaseNames (comma-separated),
  MedicationNames (comma-separated), Doses (comma-separated),
  PolicyNumber, ProviderName, ClaimedAmount, ClaimStatus
]
```
**Anomalies Present in UNF:**
- **Update Anomaly:** If a hospital changes its region, thousands of duplicate encounter rows must be updated.
- **Insertion Anomaly:** A new disease or medication cannot be added to the catalog without creating a dummy patient visit.
- **Deletion Anomaly:** Deleting a patient's only visit deletes the definition of the prescribed drug or hospital.

---

### 1.2 First Normal Form (1NF)
**Rule:** Eliminate repeating groups and ensure atomic column values.
- Multi-valued columns (e.g. comma-separated lists of `DiseaseCodes`, `MedicationNames`, and `Doses`) are decomposed into atomic rows.
- Each table has an identified Primary Key.

```
Table: PATIENT_VISIT_1NF (
    VisitID, PatientCode, PatientDOB, DoctorName, HospitalName, HospitalRegion,
    DiseaseCode, DiseaseName, MedicationCode, MedicationName, DoseText
)
Primary Key: (VisitID, DiseaseCode, MedicationCode)
```

---

### 1.3 Second Normal Form (2NF)
**Rule:** Satisfies 1NF AND every non-key attribute is fully functionally dependent on the entire primary key (no partial functional dependencies).
- In `PATIENT_VISIT_1NF`, `PatientDOB` depends only on `PatientCode`, not `(VisitID, DiseaseCode, MedicationCode)`.
- `DiseaseName` depends only on `DiseaseCode`.
- `MedicationName` depends only on `MedicationCode`.
- `HospitalRegion` depends only on `HospitalName`.

**Decomposition into 2NF:**
1. `PATIENT(PatientID, DisplayCode, DateOfBirth, Sex)`
2. `HOSPITAL(HospitalID, Name, Region)`
3. `DOCTOR(DoctorID, HospitalID, DisplayName, Specialty)`
4. `VISIT(VisitID, PatientID, DoctorID, VisitDate, VisitType)`
5. `DISEASE(DiseaseID, Code, Name)`
6. `MEDICATION(MedicationID, Code, Name, GenericName, DrugClass)`
7. `DIAGNOSIS(DiagnosisID, VisitID, DiseaseID, Severity)`
8. `PRESCRIPTION(PrescriptionID, VisitID, MedicationID, DoseText, FrequencyText)`

---

### 1.4 Third Normal Form (3NF)
**Rule:** Satisfies 2NF AND no non-key attribute is transitively dependent on the primary key (no $X \to Y$ and $Y \to Z$ where $X$ is the PK and $Y$ is non-prime).
- In the insurance domain, a claim belongs to an encounter: `ClaimID -> PolicyID -> ProviderID -> ProviderName`.
- `ProviderName` was transitively dependent on `ClaimID` via `PolicyID`.
- We isolate `INSURANCE_PROVIDER`, `INSURANCE_POLICY`, `INSURANCE_CLAIM`, and `CLAIM_ITEM`.

**Resulting 3NF Schema in MedChain:**
All 30 PostgreSQL tables conform to 3NF. Zero non-key transitive dependencies exist.

---

## 2. Advanced SQL Showcase Queries

### 2.1 Multi-Table Inner Join with Sorting
```sql
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
```

---

### 2.2 Common Table Expression (CTE) & Subquery
Identifies disease patterns within high-cost patient cohorts:
```sql
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
```

---

### 2.3 Window Functions: Partitioning & Cumulative Totals
Calculates chronological encounter rank and cumulative billing per policyholder:
```sql
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
```

---

### 2.4 Index Demonstration & Query Plan (`EXPLAIN`)
Comparing unindexed sequential scan versus B-Tree index lookup:
```sql
EXPLAIN QUERY PLAN 
SELECT * FROM patient WHERE display_code = 'PT-100201';
```
**Query Plan Output:**
```
SEARCH patient USING INDEX ix_patient_display_code (display_code=?)
```
The indexed scan executes in $O(\log N)$ logarithmic time rather than $O(N)$ full table scan.

---

### 2.5 Transaction Demonstration & Rollback Guarantee
When an invalid claim item is submitted (such as negative quantity or database constraint breach), the entire transaction aborts atomically:
```sql
BEGIN TRANSACTION;
-- Insert parent claim
INSERT INTO insurance_claim (id, policy_id, visit_id, claimed_amount, status)
VALUES ('claim-test-id', 'policy-uuid', 'visit-uuid', 500.00, 'SUBMITTED');

-- Attempt inserting item that violates quantity CHECK constraint (quantity <= 0)
INSERT INTO claim_item (id, claim_id, item_code, description, quantity, unit_cost, line_amount)
VALUES ('item-test-id', 'claim-test-id', 'CPT-99214', 'Invalid Item', -1, 500.00, -500.00);

-- Fails CHECK (quantity > 0)
ROLLBACK;
```
No orphan `insurance_claim` record is left behind in the database.
