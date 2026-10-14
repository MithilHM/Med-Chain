# MedChain: Implementation Plan & Phase Tracking

## 1. Project Overview
MedChain is an end-to-end, locally runnable healthcare data platform showcasing database engineering, privacy-preserving research queries, insurance analytics, graph relationships, and blockchain-backed consent/auditability.

All synthetic data and models strictly demonstrate computer science and database principles; no clinical validity or regulatory compliance is implied.

---

## 2. Phase-by-Phase Execution Plan

### Phase 0: Repository, Requirements & Planning
- [x] Inspect existing workspace and environment.
- [ ] Create core documentation: `docs/IMPLEMENTATION_PLAN.md`, `docs/ARCHITECTURE.md`, `docs/ERD.md`, `docs/API.md`, `docs/SECURITY_AND_PRIVACY.md`.
- [ ] Establish repository structure: `apps/web`, `services/api`, `contracts`, `infra`, `scripts`, `docs`.
- [ ] Set up `.env.example` and environment configuration schema.
- **Acceptance Check:** Comprehensive architecture, plans, and API contracts committed.

### Phase 1: Foundation & Local Infrastructure
- [ ] Create `infra/docker-compose.yml` for PostgreSQL, MongoDB, Neo4j, API, and Hardhat.
- [ ] Scaffold FastAPI backend (`services/api`) with Pydantic v2 settings, health check endpoints (`/api/v1/health`), and structured logging.
- [ ] Add service-level resilience and connectivity checks for PostgreSQL, MongoDB, Neo4j, and Hardhat node.
- [ ] Set up pytest framework in `services/api`.
- [ ] Scaffold Next.js frontend (`apps/web`) with TypeScript and Tailwind CSS.
- **Acceptance Check:** Backend and frontend build cleanly; health check reports live status of connected data stores.

### Phase 2: Relational Schema & Synthetic Seed Data
- [ ] Define SQLAlchemy 2.x declarative models for all 30 PostgreSQL tables specified in PRD Section 6.1:
  - Identity & Orgs: `app_user`, `patient`, `doctor`, `hospital`, `research_organization`, `research_project`
  - Clinical: `visit`, `disease`, `diagnosis`, `medication`, `prescription`, `treatment`, `lab_test`, `lab_result`, `side_effect`, `observed_adverse_event`
  - Documents & Integrity: `medical_document`, `record_integrity`
  - Insurance: `insurance_provider`, `insurance_policy`, `insurance_claim`, `claim_item`
  - Consent & Audit: `consent`, `access_request`, `access_event`, `blockchain_event`, `outbox_event`
  - Cohort Analytics: `cohort`, `cohort_membership`, `analytics_run`
- [ ] Implement Alembic migrations and database initialization script.
- [ ] Add DB constraints (FKs, CHECK constraints on amounts, status enum checks, valid date ranges).
- [ ] Build deterministic synthetic data generator (`scripts/seed_demo.py`) with realistic medical codes (ICD-10-like, RxNorm-like) and linked records.
- [ ] Implement database reset script (`scripts/reset_demo.py`).
- **Acceptance Check:** Schema migrates cleanly; seed script populates consistent records; constraint violations raise proper database errors.

### Phase 3: Authentication & Role-Based Access Control (RBAC)
- [ ] Implement secure password hashing (Argon2 / bcrypt) and JWT access tokens.
- [ ] Implement FastAPI security dependencies: `get_current_user`, `require_role(["patient", "doctor", "researcher", "insurance_analyst", "admin"])`.
- [ ] Enforce patient data isolation (patient can only access own data) and doctor patient-assignment verification.
- [ ] Implement seeded demo accounts with role switching in demo mode:
  - Patient: `patient@medchain.local`
  - Doctor: `doctor@medchain.local`
  - Researcher: `researcher@medchain.local`
  - Insurance Analyst: `analyst@medchain.local`
  - Admin: `admin@medchain.local`
- **Acceptance Check:** Pytest suite verifies cross-role and cross-patient requests are denied with HTTP 403.

### Phase 4: Clinical Records & MongoDB Document Integration
- [ ] Implement REST endpoints for patients, visits, diagnoses, prescriptions, lab results, and treatments.
- [ ] Implement MongoDB repository for semi-structured `medical_documents` (clinical notes, diagnostic reports).
- [ ] Link relational document metadata in PostgreSQL with MongoDB document contents.
- [ ] Implement graceful fallback and safe failure handling if MongoDB is offline.
- [ ] Build patient records timeline and clinical document viewer in Next.js web UI.
- **Acceptance Check:** Clinical records and MongoDB documents are created, retrieved, and linked; MongoDB failures are surfaced gracefully without crashing PostgreSQL workflows.

### Phase 5: Insurance Database & Analytics
- [ ] Implement policies, claims, and claim items endpoints.
- [ ] Implement transactional claim submission with rollback demonstration on failure.
- [ ] Implement explainable duplicate/anomaly review rules (overlapping dates, identical service codes, excessive billing).
- [ ] Implement insurance cost and utilization aggregate queries.
- [ ] Enforce security boundary: insurance analysts cannot view raw clinical notes.
- [ ] Build Insurance Analytics dashboard in frontend with anomaly review queue.
- **Acceptance Check:** Claim rollback test passes; anomaly queue identifies synthetic duplicates; analyst access to clinical notes is blocked with 403.

### Phase 6: Patient Consent & Research Workflows
- [ ] Implement research project management and access requests (`/access-requests`).
- [ ] Implement Consent Center (`/consents`): grant consent with granular scopes (`aggregate_diagnoses`, `deidentified_cohort`, `medication_history`, `lab_summaries`), expiry date, and instant revocation.
- [ ] Implement central consent authorization evaluation engine:
  - Checks purpose, active consent, expiration date, and revocation status before executing research queries.
  - Denies by default if consent is absent, expired, or revoked.
- [ ] Log all access attempts (granted and denied) to `access_event` with reasons.
- [ ] Build Patient Consent Center UI and Researcher Query UI.
- **Acceptance Check:** Researcher query succeeds with active consent; after revocation, query immediately returns 403 and denial is recorded in audit log.

### Phase 7: Blockchain Consent & Record Integrity
- [ ] Develop Solidity smart contract `MedChainAudit.sol`:
  - `recordConsentGranted(bytes32 consentIdHash, bytes32 projectHash, uint256 expiry)`
  - `recordConsentRevoked(bytes32 consentIdHash)`
  - `recordAccessEvent(bytes32 eventHash, bytes32 actorHash, bytes32 resourceHash)`
  - `anchorRecordCommitment(bytes32 recordRefHash, bytes32 commitmentHash)`
- [ ] Write Hardhat test suite verifying contract events, immutability, and access controls.
- [ ] Implement Python blockchain adapter using Web3.py / ethers RPC:
  - Transacts to local Hardhat node or container.
  - Distinguishes statuses: `confirmed`, `pending`, `failed`, `unanchored`.
- [ ] Implement cryptographic record commitment verification (SHA-256 canonical JSON with salted off-chain keys).
- [ ] Build UI integrity verifier: demonstrates valid check for unaltered records, and tampering detection for modified records.
- **Acceptance Check:** Contract tests pass; UI shows live on-chain transaction hash and block numbers; tampered records fail integrity verification.

### Phase 8: Neo4j Graph Intelligence
- [ ] Implement graph synchronization service: projects authorized relational data into Neo4j graph nodes (`Patient`, `Disease`, `Medication`, `SideEffect`, `Cohort`) and relationships (`HAS_DIAGNOSIS`, `RECEIVED`, `OBSERVED_WITH`, `CO_OCCURS_WITH`).
- [ ] Build graph queries:
  - Disease co-occurrence patterns
  - Medication-to-observed-side-effect associations
  - Cohort treatment paths
- [ ] Gate patient-level traversals through consent service; provide aggregate counts and association disclaimers.
- [ ] Implement Admin rebuild/re-sync graph button with status monitoring.
- [ ] Build interactive Disease-Drug Graph Explorer UI.
- **Acceptance Check:** Graph queries return results matching PostgreSQL reference data; rebuild completes cleanly; unauthorized traversal is rejected.

### Phase 9: Patient Cohort Analytics
- [ ] Implement unsupervised clustering pipeline (`K-Means` via scikit-learn) on synthetic, de-identified feature matrices (diagnosis frequencies, lab abnormalities, medication counts).
- [ ] Ensure direct patient identifiers are strictly excluded from feature extraction.
- [ ] Implement deterministic clustering with fixed random seed and customizable $k$.
- [ ] Store cohort run parameters, metrics (inertia, silhouette if applicable), and membership in `cohort` and `cohort_membership`.
- [ ] Build Cohort Explorer UI displaying cluster distributions and aggregated radar/bar profiles.
- **Acceptance Check:** Clustering produces reproducible clusters; direct identifiers are absent from dataset; results are clearly labeled exploratory.

### Phase 10: Audit Trail & Advanced DBMS Showcase
- [ ] Build full Audit & Integrity log view with transaction hashes and actor actions.
- [ ] Implement SQL Showcase module executing live queries:
  - Multi-table joins across clinical, insurance, and consent domains.
  - Window functions (e.g., patient timeline rank, cumulative disease expenditures).
  - Recursive CTEs / hierarchical queries.
  - Index performance demonstration (`EXPLAIN ANALYZE` before & after indexing).
  - Materialized / standard database views for de-identified research and insurance aggregates.
  - Triggers and constraint validation.
- [ ] Document relational normalization walkthrough (1NF -> 2NF -> 3NF) in `docs/DBMS_SHOWCASE.md`.
- **Acceptance Check:** SQL showcase executes live and returns verified explain outputs; audit log records every critical system event.

### Phase 11: Hardening, Integration & Final Demonstration
- [ ] End-to-end integration testing across frontend, backend, databases, and blockchain.
- [ ] Run full automated test suite (pytest + hardhat).
- [ ] Verify complete demo walkthrough (PRD Section 16).
- [ ] Finalize documentation: `README.md`, `docs/DEMO_SCRIPT.md`, `docs/API.md`.
- **Acceptance Check:** Clean startup, all interactive workflows operational, zero inert buttons, all tests passing.
