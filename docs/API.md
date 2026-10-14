# MedChain REST API Specification

**Base URL:** `/api/v1`  
**Authentication Scheme:** `Bearer <JWT_TOKEN>`  
**Default Error Format:**
```json
{
  "detail": "Error description message",
  "error_code": "RESOURCE_NOT_FOUND | PERMISSION_DENIED | CONSENT_REQUIRED | VALIDATION_ERROR"
}
```

---

## 1. Authentication & Session (`/auth`)

### `POST /auth/login`
- **Description:** Authenticate user credentials and issue short-lived JWT token.
- **Request Body:**
  ```json
  {
    "email": "doctor@medchain.local",
    "password": "Password123!"
  }
  ```
- **Response `200 OK`:**
  ```json
  {
    "access_token": "eyJhbGciOi...",
    "token_type": "bearer",
    "user": {
      "id": "uuid",
      "email": "doctor@medchain.local",
      "role": "doctor"
    }
  }
  ```

### `GET /auth/me`
- **Description:** Return authenticated user context and linked entity reference (e.g. `patient_id` or `doctor_id`).
- **Authorization:** Any authenticated user.

---

## 2. Patients & Clinical Encounters (`/patients`, `/visits`, `/clinical`)

### `GET /patients`
- **Description:** Paginated list of patients.
- **Authorization:**
  - `doctor`: assigned patients only.
  - `admin`: all synthetic patients.
  - `patient`: only own patient record.
  - `researcher`, `insurance_analyst`: 403 Forbidden (must use dedicated de-identified/insurance endpoints).

### `GET /patients/{id}/timeline`
- **Description:** Complete chronological encounter timeline including visits, diagnoses, prescriptions, lab results, and document metadata.
- **Authorization:** Assigned doctor or owner patient.

### `POST /visits`
- **Description:** Create a new clinical visit.
- **Authorization:** `doctor` or `admin`.

---

## 3. Documents & Semi-Structured Data (`/documents`)

### `POST /documents`
- **Description:** Create clinical document (written to MongoDB) with relational metadata (in PostgreSQL).
- **Request Body:**
  ```json
  {
    "patient_id": "uuid",
    "visit_id": "uuid",
    "document_type": "clinical_note",
    "title": "Synthetic Cardiology Follow-up",
    "content": "Patient reports mild chest discomfort..."
  }
  ```
- **Authorization:** `doctor` assigned to the patient.

### `GET /documents/{id}`
- **Description:** Retrieve document metadata and decrypted/fetched narrative text.
- **Authorization:** Assigned doctor or owner patient. Strictly forbidden to researchers and insurance analysts.

---

## 4. Patient Consent & Research Engine (`/consents`, `/access-requests`, `/research`)

### `POST /research-projects`
- **Description:** Create a research initiative declaring purpose and requested scope.
- **Authorization:** `researcher` or `admin`.

### `POST /access-requests`
- **Description:** Request consent from a patient for a research project.
- **Request Body:**
  ```json
  {
    "patient_id": "uuid",
    "project_id": "uuid",
    "purpose": "Type 2 Diabetes Cohort Study",
    "requested_scope": ["aggregate_diagnoses", "medication_history"]
  }
  ```

### `POST /access-requests/{id}/decision`
- **Description:** Patient approves or rejects research access request. When approved, creates a `consent` record and anchors event on-chain.
- **Authorization:** Only the target `patient`.

### `POST /consents/{id}/revoke`
- **Description:** Instantly revoke active consent, blocking all subsequent research queries and emitting a revocation blockchain event.
- **Authorization:** Owner `patient`.

### `POST /research/query`
- **Description:** Execute a privacy-preserving aggregate query against authorized data.
- **Request Body:**
  ```json
  {
    "project_id": "uuid",
    "query_type": "cohort_summary | disease_distribution | lab_trends",
    "filters": {"disease_code": "E11.9"}
  }
  ```
- **Consent Enforcement:**
  - Evaluates active consent for `project_id`.
  - If missing, expired, or revoked: returns `403 Forbidden` with `"error_code": "CONSENT_REVOKED_OR_MISSING"`.
  - Action and decision (`GRANTED` or `DENIED`) logged to `access_event`.

---

## 5. Blockchain & Integrity Verification (`/integrity`, `/blockchain`)

### `GET /integrity/verify/{document_id}`
- **Description:** Recalculates cryptographic commitment for the document version and compares against PostgreSQL and blockchain anchors.
- **Response `200 OK`:**
  ```json
  {
    "document_id": "uuid",
    "expected_hash": "0x4a9f...",
    "computed_hash": "0x4a9f...",
    "status": "VERIFIED_MATCH",
    "chain_tx_hash": "0x8f2c...",
    "chain_status": "CONFIRMED"
  }
  ```

### `POST /integrity/tamper-demo/{document_id}`
- **Description:** *DEMO ONLY.* Modifies one byte in MongoDB document content to prove tamper detection in the verification workflow.

### `GET /blockchain/status`
- **Description:** Return RPC connectivity, contract address, current block number, and transaction count.

---

## 6. Insurance Analytics (`/insurance`)

### `GET /insurance/claims`
- **Description:** List claims with anomaly review flags.
- **Authorization:** `insurance_analyst` or `admin`.

### `POST /insurance/claims`
- **Description:** Transactional claim submission with items.
- **Rollback Demonstration:** Simulates transactional integrity with atomic rollback on invalid item totals.

### `POST /insurance/claims/{id}/review`
- **Description:** Analyst records human review decision (`APPROVED`, `REJECTED`, `FLAGGED_INVESTIGATION`) and explanation.

### `GET /analytics/insurance/expenditure`
- **Description:** Disease-wise and treatment-type aggregate expenditures.

---

## 7. Derived Graph & Cohorts (`/graph`, `/cohorts`)

### `GET /graph/disease-cooccurrence`
- **Description:** Returns nodes and edges representing co-occurring diagnoses meeting minimum threshold.

### `GET /graph/drug-side-effects`
- **Description:** Returns medications and observed adverse events with explicit association disclaimers.

### `POST /cohorts/run`
- **Description:** Runs deterministic K-Means clustering over synthetic de-identified feature matrices.
- **Request Body:**
  ```json
  {
    "cohort_name": "Metabolic Cohort 2026",
    "k": 3,
    "feature_groups": ["diagnoses", "medications", "lab_abnormalities"]
  }
  ```

---

## 8. Admin & Operational Controls (`/admin`)

### `GET /admin/health`
- **Description:** Live probes for PostgreSQL, MongoDB, Neo4j, and Blockchain network.
- **Response `200 OK`:**
  ```json
  {
    "status": "healthy",
    "services": {
      "postgres": {"status": "up", "latency_ms": 2.1},
      "mongo": {"status": "up", "collections": 1},
      "neo4j": {"status": "up", "nodes": 128},
      "blockchain": {"status": "up", "block_number": 42}
    }
  }
  ```

### `POST /admin/graph/rebuild`
- **Description:** Drops and regenerates Neo4j projection from authoritative PostgreSQL tables.

### `POST /admin/demo/reset`
- **Description:** Clears all data stores and executes deterministic synthetic seed generator.
