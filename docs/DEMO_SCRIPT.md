# MedChain Demonstration Script & Scenario Walk-Through

This document provides an exact, step-by-step narrative for evaluating, demonstrating, or validating MedChain. It follows Section 16 of the Product Requirements Document (PRD) and covers end-to-end workflows across all operational layers.

---

## Demo Personas & Pre-Seeded Accounts

All demo users share the default password: **`Password123!`**

| Role | Username / Email | Linked Entity | Primary Workflow Responsibility |
| :--- | :--- | :--- | :--- |
| **System Admin** | `admin@medchain.local` | Platform Infrastructure | Multi-store health check, graph projection rebuild, store reset |
| **Primary Patient** | `patient@medchain.local` | Patient `PT-100201` | Review access requests, grant consent, real-time revocation |
| **Attending Doctor**| `doctor@medchain.local` | Dr. Sarah Chen, MD | Clinical encounter documentation, visit review, timeline inspection |
| **Research Scientist**| `researcher@medchain.local`| Academic Consortium | Project creation, access request submission, cohort K-Means, consent queries |
| **Insurance Analyst**| `analyst@medchain.local` | Health Payer Desk | Atomic claim validation, claim review queue, fraud adjudication |

---

## 12-Step Demonstration Narrative

### Step 1: System Baseline & Multi-Store Health Check
1. **Navigate to:** `/admin` on the Web UI or execute `GET /api/v1/health`.
2. **Observe:** The 4-store infrastructure probe indicators:
   - **PostgreSQL / Relational Store:** Operational (or resilient local SQLite fallback with 30 authoritative tables).
   - **MongoDB / Document Store:** Operational (or local filesystem document store fallback).
   - **Neo4j / Graph Intelligence:** Operational (or in-memory projected graph fallback).
   - **Hardhat / Blockchain Evidence:** Operational (or cached unanchored fallback).
3. **Verification:** All services report connectivity and sub-50ms query latencies without throwing uncaught connection exceptions.

---

### Step 2: Researcher Onboarding & Project Registration
1. **Switch Role:** Top-right navbar switcher -> select **Researcher (`researcher@medchain.local`)**.
2. **Navigate to:** `/research` (Research & Consent Portal).
3. **Action:** Click **"New Research Project"** and submit:
   - **Title:** `Cardio-Metabolic Cross-Disorder Longitudinal Study`
   - **IRB Number:** `IRB-2026-CARDIO-999`
   - **Purpose:** `Longitudinal metabolic syndrome progression and drug interactions.`
4. **Outcome:** Project is persisted with authoritative ID and status `ACTIVE`.

---

### Step 3: Access Request Submission
1. **Role:** Researcher.
2. **Action:** On `/research`, select the created project and click **"Request Patient Access"**:
   - **Target Patient:** Select `PT-100201 (Alice Smith)`
   - **Requested Data Scope:** `aggregate_diagnoses`
   - **Purpose Justification:** `Required for statistical cohort analysis under IRB protocol.`
3. **Outcome:** A new `AccessRequest` record is created in state `PENDING`. An audit log entry is written.

---

### Step 4: Centralized Policy Evaluation (Deny-by-Default)
1. **Role:** Researcher.
2. **Action:** On `/research`, under **"Consent-Gated Cohort Query Runner"**, select `PT-100201` and execute query type **Disease Distribution**.
3. **Result:** Request is **BLOCKED with HTTP 403 Forbidden**.
4. **Inspect Policy Message:**
   ```json
   {
     "detail": {
       "message": "Research query rejected by Consent Policy Engine: No active consent granted by patient for this research project.",
       "error_code": "CONSENT_REVOKED_OR_MISSING",
       "project_id": "<PROJECT_UUID>"
     }
   }
   ```
5. **Security Verification:** Confirms that patient records are strictly isolated under deny-by-default access policies prior to explicit patient consent.

---

### Step 5: Patient Consent Management & Policy Re-Evaluation (Grant)
1. **Switch Role:** Top-right navbar switcher -> select **Patient (`patient@medchain.local`)**.
2. **Navigate to:** `/consent` (Patient Consent Center).
3. **Observe:** The pending access request from the Academic Consortium is prominently displayed.
4. **Action:** Click **"Approve Access"** with 365-day validity.
5. **Result:**
   - Access request updates to `APPROVED`.
   - Authoritative `Consent` record is created with `status: GRANTED`.
   - Salted SHA-256 commitment is anchored to the smart contract ledger (`recordConsentGranted`).
6. **Re-Evaluation:** Switch back to **Researcher** -> Re-run the **Disease Distribution** query.
7. **Outcome:** **HTTP 200 OK**. Query returns de-identified aggregate diagnosis distributions for `PT-100201` with zero direct identifiers.

---

### Step 6: Research Cohort Execution & Exploration
1. **Role:** Researcher.
2. **Navigate to:** `/cohorts` (Cohort Analytics & ML Pipeline).
3. **Action:** Select $k=3$ clusters and click **"Run K-Means Clustering"**.
4. **Outcome:**
   - Scikit-learn normalizes multi-dimensional patient vectors (`age`, `encounter_count`, `condition_count`, `total_billed`).
   - Clusters are computed with inertia metrics.
   - Cluster Cards display clinical summaries:
     - **Cluster 0:** *Young Adult Acute / Low-Comorbidity*
     - **Cluster 1:** *Middle-Aged Metabolic Syndrome & Hypertension*
     - **Cluster 2:** *Elderly High-Cost Polypharmacy & Multi-Organ Failure*
5. **Observance:** Each card includes the mandatory non-causal heuristic disclaimer.

---

### Step 7: Real-Time Patient Consent Revocation & Immediate Enforcement
1. **Switch Role:** Select **Patient (`patient@medchain.local`)**.
2. **Navigate to:** `/consent`.
3. **Action:** Locate the active research consent and click **"Revoke Consent"**.
4. **Result:**
   - Consent status immediately transitions to `REVOKED` in the authoritative database.
   - Smart contract emits `ConsentRevoked` event with transaction receipt.
5. **Immediate Enforcement:**
   - Switch back to **Researcher** -> Attempt to re-run the patient research query.
   - Result: **HTTP 403 Forbidden** immediately without server restart or caching latency.

---

### Step 8: Cross-Database Data Consistency & Graph Rebuild
1. **Switch Role:** Select **Administrator (`admin@medchain.local`)**.
2. **Navigate to:** `/admin`.
3. **Action:** Click **"Rebuild Graph Projection"**.
4. **Result:**
   - Graph projection worker scans relational `visit`, `diagnosis`, `disease`, `prescription`, and `medication` tables.
   - Updates derived graph nodes (`Condition`, `Medication`) and co-occurrence edges.
   - Shows synchronization summary: `SYNCHRONIZED`, 31 nodes, 51 edges.

---

### Step 9: Clinical Document Tamper Detection & Cryptographic Integrity Verification
1. **Navigate to:** `/integrity` (Record Integrity Verifier).
2. **Step A (Clean Baseline):**
   - Click **"Verify Document"** on discharge note `DOC-100201-01`.
   - Result: **VERIFIED MATCH (Green)**.
   - Canonical RFC 8785 JSON representation matches salted SHA-256 commitment on the ledger.
3. **Step B (Tamper Simulation):**
   - Click **"Simulate Tamper Demo"**.
   - Backdoor injection modifies a clinical note field (e.g., changes medication dosage in MongoDB).
4. **Step C (Detection):**
   - Click **"Verify Document"** again.
   - Result: **TAMPER DETECTED (Red Alert)**.
   - Computed hash differs from immutable on-chain commitment. Explanatory diff shows exact discrepancy.

---

### Step 10: Insurance Claim Submission, Atomic Rollback, & Anomaly Detection
1. **Switch Role:** Select **Insurance Analyst (`analyst@medchain.local`)**.
2. **Navigate to:** `/insurance`.
3. **Step A (Atomic Rollback Demo):**
   - Click **"Submit Claim with Rollback Demo"** (sends negative quantity `-2`).
   - Result: **HTTP 400 Bad Request**. Entire transaction rolls back atomically without partial orphaned line item rows.
4. **Step B (Heuristic Anomaly Review):**
   - View the flagged anomaly queue. Observe duplicate billing flag: *"Duplicate claim detected within 48h for same patient, provider, and diagnosis code"*.
   - Click **"Review & Adjudicate"** -> Select **"Confirm Fraud"** and enter audit justification.
   - Result: Claim status transitions to `CONFIRMED_FRAUD` and audit entry is anchored.

---

### Step 11: Graph Analytics & Treatment Exploration
1. **Navigate to:** `/graph` (Disease-Drug Intelligence Graph).
2. **Action:** Enter ICD-10 code `I10` (Essential Primary Hypertension) or view the interactive graph.
3. **Outcome:**
   - Traverses directed graph relationships: `(:Disease {code: 'I10'})-[:TREATED_WITH]->(:Medication {name: 'Lisinopril'})`.
   - Inspect confidence metrics and co-occurrence frequency.
   - Review epidemiological caution label regarding synthetic correlation vs. causal clinical evidence.

---

### Step 12: Audit Trail Verification & On-Chain Proof Inspection
1. **Navigate to:** `/audit` (Immutable Audit Trail).
2. **Outcome:**
   - Real-time tabular log of every access event executed during Steps 1-11:
     - `ACCESS_REQUEST_CREATED`
     - `CONSENT_GRANTED` (with blockchain Tx Hash)
     - `RESEARCH_QUERY_ATTEMPT` (decision: DENIED)
     - `RESEARCH_QUERY_ATTEMPT` (decision: GRANTED)
     - `CONSENT_REVOKED` (with blockchain Tx Hash)
     - `TAMPER_DEMO_MUTATION`
     - `CLAIM_FRAUD_ADJUDICATION`
   - Complete non-repudiation audit trail suitable for HIPAA/GDPR institutional compliance.
