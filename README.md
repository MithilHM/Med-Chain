# MedChain: Privacy-Preserving Healthcare Intelligence & Multi-Model Audit Platform

**MedChain** is a healthcare data platform prototype for consent-managed records, real-time clinical integration, research analytics, and tamper-evident audit events. It is a single-organization system tested with synthetic data; it is not yet approved to store or process real patient records.

> **Deployment status:** the code-level controls for a single-hospital pilot are implemented and tested: real-time HL7 v2 ingestion, hospital SSO/SCIM/MFA, durable audit delivery, approval-gated merges, alerting, and key rotation. What remains needs the hospital itself: identity-provider registration, interface validation on its test feed, a permissioned ledger network, infrastructure hardening, and institutional approval. Connect only to a hospital *test* environment until every gate in [Production Readiness](docs/PRODUCTION_READINESS.md) is closed. Operators should start with the [Operations Runbook](docs/OPERATIONS.md).

See the [change checklist](docs/CHANGE_CHECKLIST.md) for completed changes and remaining essential work.
See the [review backlog](docs/REVIEW_BACKLOG.md) for confirmed security/reliability gaps and optional improvements.

---

## Architecture Overview

MedChain addresses the tension between clinical data usability, institutional privacy, and tamper evidence through clear separation of concerns:

```
                  +----------------------------------------------+
                  |         MedChain Web Console (Next.js)       |
                  |     Role Switcher: Patient/Doc/Res/Analyst   |
                  +----------------------+-----------------------+
                                         |
                                         v
                  +----------------------------------------------+
                  |      FastAPI Application Gateway & Policies  |
                  |    Centralized Deny-by-Default Consent Engine|
                  +-------+-------------+-------------+----------+
                          |             |             |
        +-----------------+             |             +-----------------+
        |                               |                               |
        v                               v                               v
+---------------+             +-------------------+           +-------------------+
|  PostgreSQL   |             |     MongoDB       |           |   Ethereum / EVM  |
| (Authoritative|             |  (Semi-Structured |           | (Smart Contracts) |
| Relational,   |             |  Clinical Notes   |           | Salted SHA-256    |
| 30 Tables)    |             |  & Discharge Sums)|           | Zero Raw PII/PHI  |
+-------+-------+             +---------+---------+           +---------+---------+
        |                               |                               |
                          | Admin-triggered rebuild       | SHA-256 Digest                | Nonce/Block
        v                               v                               v
+---------------+             +-------------------+           +-------------------+
|     Neo4j     |             | Sorted-key JSON   |          |   Scikit-Learn    |
| Derived Graph |             | Integrity Service |           | K-Means Cohorting |
| Projection    |             | Tamper Detection  |           | Feature Vectors   |
+---------------+             +-------------------+           +-------------------+
```

### Source-of-Truth Hierarchy
1. **Relational Store (PostgreSQL / SQLite fallback):** Authoritative source of truth for identity, patient demographics, clinical visits, diagnoses, prescriptions, insurance claims, and active consent states.
2. **Document Store (MongoDB / Local JSON fallback):** Semi-structured clinical narratives are encrypted with AES-256-GCM. The local JSON fallback is limited to development and test; production requires MongoDB. The API decrypts payloads only after access checks.
3. **Derived Graph (Neo4j / In-Memory projection):** Rebuilt from relational data through the admin graph-rebuild action. The in-memory projection is a development fallback; automated outbox synchronization is not yet implemented.
4. **Blockchain Audit Ledger (Solidity / Hardhat):** Records consent and access events plus salted document commitments. Raw clinical records and direct identifiers stay off-chain; opaque hashes are used for references.

---

## Key Features

- **Real-time Clinical Integration:** HL7 v2 `ADT^A01/A04/A08/A03` and `ORU^R01` over MLLP (TLS/mTLS) or HTTPS, with an encrypted idempotent message ledger, identifier-only patient matching, a manual review queue, and HL7 ACKs. See [Integration](docs/INTEGRATION.md).
- **Live Clinical Feed:** Server-Sent Events push admissions, results (with abnormal/critical flags), and alerts to the care team, filtered per patient and closed when the session ends.
- **Durable Audit Evidence:** Consent, access, document, and inbound-message evidence is written to a transactional outbox with the authoritative change and delivered to the chain with retries and idempotent checks; on-chain references are keyed HMAC pseudonyms.
- **Clinical Access Model:** Care-team assignments from ADT/FHIR/onboarding that end after discharge, time-boxed break-the-glass grants with compliance review, encrypted patient names visible only to care roles, and approval-gated duplicate-record merges.
- **Hospital Identity:** OIDC single sign-on with directory-group roles, SCIM deprovisioning, TOTP MFA with recovery codes, fail-closed sessions, lockout, and a database-backed rate limit.
- **Operations:** Prometheus `/metrics`, webhook alerting, an admin Operations console, encryption key rotation, an atomic graph rebuild, and PostgreSQL `LISTEN/NOTIFY` event fan-out across replicas.
- **Centralized Deny-by-Default Consent Engine:** Research authorization checks enforce patient consent scopes (`aggregate_diagnoses`, `medication_history`, `lab_summaries`). Authorized queries hold consent row locks, so revocation is serialized with in-flight queries.
- **Cryptographic Record Integrity:** Deterministic sorted-key compact JSON and salted SHA-256 hashing, checked against the on-chain commitment when the chain is available.
- **Advanced DBMS Engineering:** Relational schema documentation, a command-line SQL showcase, and an admin-only web explorer for fixed joins, CTEs, window aggregates, and an indexed lookup plan. Aggregate results hide groups with fewer than five patients.
- **Explainable Insurance Fraud Heuristics:** Automated anomaly flagging for overlapping visits, 48-hour duplicate billing, and unbundling, paired with human-in-the-loop analyst adjudication.
- **Provider-Scoped Insurance Access:** Insurance analysts are assigned to a provider and can view, create, adjudicate, and analyze only that provider's policies and claims.
- **Unsupervised Patient Cohort Clustering:** Scikit-learn K-Means pipeline generating multidimensional patient risk phenotypes from diagnoses, encounter frequencies, and billing data.
- **Resilient Local Operation:** Built-in self-healing fallbacks allowing full local execution of backend, smart contracts, scripts, and frontend even when external Docker services are offline.

---

## Directory Structure

```
MEDCHAIN/
├── apps/
│   └── web/                   # Next.js 14 App Router Web Application
│       ├── src/app/           # App Router modules for patient, research, insurance, admin, and audit workflows
│       ├── src/components/    # Glassmorphic UI components, Navbar, Role switcher
│       └── src/lib/api.ts     # Typed API client connecting to backend
├── contracts/
│   ├── contracts/             # MedChainAudit.sol (deployed); MedChainTrustLayer.sol (deprecated sketch, not deployed)
│   ├── test/                  # Hardhat contract test suite
│   └── scripts/               # Contract deployment scripts
├── docs/
│   ├── ARCHITECTURE.md        # System architecture, privacy model & source-of-truth rules
│   ├── IMPLEMENTATION_PLAN.md # 11-Phase execution roadmap matching PRD
│   ├── ERD.md                 # Complete Entity-Relationship schema for all 30 tables
│   ├── API.md                 # OpenAPI REST endpoints and schemas
│   ├── SECURITY_AND_PRIVACY.md# Threat model, commitment math, and cryptographic proofs
│   ├── DBMS_SHOWCASE.md       # 1NF/2NF/3NF normalization, CTEs, and EXPLAIN plans
│   └── DEMO_SCRIPT.md         # Step-by-step 12-stage PRD demo walk-through
├── infra/
│   └── docker-compose.yml     # Multi-store Docker topology (Postgres, Mongo, Neo4j, Hardhat)
├── scripts/
│   ├── seed_demo.py           # Deterministic demo generator across all stores
│   ├── reset_demo.py          # Complete multi-store drop and reseed script
│   └── run_sql_showcase.py    # Executes advanced DBMS analytics and EXPLAIN plans
└── services/
    └── api/                   # FastAPI Backend Gateway
        ├── src/
        │   ├── main.py        # Application entrypoint & route registration
        │   ├── database.py    # SQLAlchemy async engine & fallback logic
        │   ├── models/        # 30 SQLAlchemy relational models
        │   ├── routers/       # REST API routers under /api/v1 (incl. integration, events)
        │   ├── integration/   # HL7 v2 parser, message processor, MLLP listener
        │   ├── schemas/       # Pydantic v2 validation schemas
        │   └── services/      # Consent, outbox, chain, matching, events, integrity, ML, graph
        ├── alembic/versions/  # 001 baseline (generated from models), 002 integration schema
        └── tests/             # Pytest integration, HL7, access-control, and E2E scenario suite
```

---

## Quickstart Guide

### Prerequisites
- **Docker Engine with Compose** for the all-in-one setup below

### All-in-one Docker setup (recommended)

From the repository root:

```bash
cp .env.example .env
docker compose -f infra/docker-compose.yml up --build -d
docker compose -f infra/docker-compose.yml exec api python /app/scripts/seed_demo.py
```

Compose starts PostgreSQL, authenticated MongoDB, Neo4j, the API, and a local Hardhat chain. The chain deploys the audit contract before the API starts. The seed command creates synthetic demo records and accounts. Open `http://localhost:3000` and use **Sign in** with `patient@medchain.local` or another demo account; all seeded demo accounts use `Password123!`.

`DOCUMENT_ENCRYPTION_KEY` is a 64-character hexadecimal AES-256 key. The example key is for local synthetic data only. Set a unique key and store it outside the database for any deployment; losing or changing it makes encrypted clinical documents unreadable. Legacy plaintext documents are encrypted when first read.

Research query, graph, and cohort outputs require at least five consented patients. Result cells and cluster summaries supported by fewer than five patients are suppressed to reduce small-group disclosure risk. This is a basic disclosure control, not a guarantee of anonymity.

To stop the stack, run:

```bash
docker compose -f infra/docker-compose.yml down
```

Add `-v` only when you intend to delete the database volumes and all seeded data.

### Manual local setup

For the individual service instructions below, install **Python 3.11+**, **Node.js 18+**, and npm. Start the required databases separately or use the Compose stack above.

---

### 1. Smart Contract Suite

```bash
cd contracts
npm install
npm test
```
*Expected output: all contract tests passing.*

---

### 2. Backend Gateway & Database Initialization

```bash
cd services/api

# Create and activate virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
# source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Seed deterministic demo data across all stores
python ../../scripts/seed_demo.py

# Run backend server
uvicorn src.main:app --host 127.0.0.1 --port 8000 --reload
```
*Backend API docs are now available at: `http://localhost:8000/docs`.*

---

### 3. Frontend Web Console

```bash
cd apps/web
npm install
npm run dev
```
*Frontend Web Console is now live at: `http://localhost:3000`.*

---

## Running the Verification Test Suites

### Complete Backend & E2E Integration Suite
```bash
cd services/api
.venv\Scripts\pytest -v
```
*Runs the full suite, including `test_e2e_prd_scenario.py` (12-step narrative) and `test_realtime_integration.py` (HL7 ingestion, review queue, event authorization, outbox semantics).*

### Database migrations
```bash
cd services/api
alembic upgrade head      # required before non-development startup
```
CI also runs the migrations on PostgreSQL and fails if they drift from the models.

### Real-time HL7 listener
```bash
cd services/api
python -m src.integration.mllp_server   # or: docker compose -f infra/docker-compose.yml --profile integration up -d
```
See [docs/INTEGRATION.md](docs/INTEGRATION.md) for message types, field mapping, ACK semantics, and integration keys.

### Advanced SQL & DBMS Showcase
```bash
cd services/api
.venv\Scripts\python ../../scripts/run_sql_showcase.py
```
*Executes 5 complex queries demonstrating 3NF joins, recursive CTEs, and `EXPLAIN QUERY PLAN`.*

### Frontend Production Build Test
```bash
cd apps/web
npm run build
```
*Verifies there are no TypeScript errors and generates the static route pages.*

---

## Demo Personas & Pre-Seeded Accounts

All seeded demo accounts share the password: **`Password123!`**

| Persona | Email / Login | Role | Demonstrates |
| :--- | :--- | :--- | :--- |
| **System Admin** | `admin@medchain.local` | `admin` | Infrastructure health, graph rebuild, store reset |
| **Primary Patient** | `patient@medchain.local` | `patient` | Access request approval, consent revocation |
| **Attending Doctor**| `doctor@medchain.local` | `doctor` | Longitudinal encounter timeline, note entry |
| **Research Scientist**| `researcher@medchain.local`| `researcher`| Consent-gated queries, K-Means cohorting |
| **Insurance Analyst**| `analyst@medchain.local` | `insurance_analyst`| Transactional claim rollback, fraud queue |

In local demo mode, the header role switcher can change demo personas. Regular accounts sign in with their own credentials and do not get the demo role switcher.

---

## Detailed Documentation Links

- [System Architecture & Privacy Model](docs/ARCHITECTURE.md)
- [Real-time Clinical Integration (HL7 v2 / FHIR)](docs/INTEGRATION.md)
- [Operations Runbook (SSO, alerts, key rotation, ledger)](docs/OPERATIONS.md)
- [Implementation Plan & Phase Roadmap](docs/IMPLEMENTATION_PLAN.md)
- [Complete Entity-Relationship Schema (ERD)](docs/ERD.md)
- [API Reference & OpenAPI Specifications](docs/API.md)
- [Cryptographic Security & Threat Model](docs/SECURITY_AND_PRIVACY.md)
- [Hospital Production Readiness Gates](docs/PRODUCTION_READINESS.md)
- [DBMS Normalization & Query Optimization Showcase](docs/DBMS_SHOWCASE.md)
- [12-Step Evaluation Demonstration Script](docs/DEMO_SCRIPT.md)

---

## Privacy Design Scope

The prototype demonstrates selected privacy controls: scoped consent checks, aggregate suppression, encrypted document payloads, role checks, and off-chain medical records with on-chain commitments. These controls do not establish HIPAA or GDPR compliance. Institutional policy mapping, threat assessment, operational controls, and independent review are required before any regulated deployment. Revocation waits for in-flight authorized queries (PostgreSQL row locks) and blocks every later check; exports already downloaded cannot be recalled.
