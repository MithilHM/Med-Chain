# MedChain: Privacy-Preserving Healthcare Intelligence & Multi-Model Audit Platform

[![E2E Verification](https://img.shields.io/badge/E2E%20Tests-11%20Passed-brightgreen)](services/api/tests)
[![Smart Contracts](https://img.shields.io/badge/Solidity%20Contracts-8%20Passed-blue)](contracts/test)
[![Frontend Build](https://img.shields.io/badge/Next.js%2014-Compiled%20%E2%9C%93-success)](apps/web)
[![DBMS Showcase](https://img.shields.io/badge/SQL%20Showcase-3NF%20%2B%20CTE%20%2B%20Window%20Functions-orange)](docs/DBMS_SHOWCASE.md)

**MedChain** is an educational privacy-preserving healthcare data intelligence demonstration. It explores a **hybrid multi-store architecture** integrating relational records, semi-structured clinical documents, derived graph analytics, unsupervised cohort discovery, and an Ethereum/Hardhat cryptographic commitment layer.

> MedChain is an educational demonstration using synthetic data. It is not a clinical system and is not certified for regulated health data.

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

- **Centralized Deny-by-Default Consent Engine:** Gated research access control enforcing patient consent scopes (`aggregate_diagnoses`, `medication_history`, `lab_summaries`). Immediate real-time revocation enforcement with zero server restart or cache invalidation delays.
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
│   ├── contracts/             # MedChainAudit.sol Solidity smart contract
│   ├── test/                  # Hardhat contract test suite (8 tests)
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
        │   ├── routers/       # 13 REST API routers under /api/v1
        │   ├── schemas/       # Pydantic v2 validation schemas
        │   └── services/      # Business logic: Consent, Integrity, ML, Anomaly, Graph
        └── tests/             # Pytest integration and E2E scenario suite (11 tests)
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
*Expected output: All 8 contract tests passing.*

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
*Runs all 11 test suites including `test_e2e_prd_scenario.py` verifying the full 12-step narrative.*

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
*Verifies 0 TypeScript errors and generates all 14 static route pages.*

---

## Demo Personas & Pre-Seeded Accounts

All seeded demo accounts share the password: **`Password123!`**

| Persona | Email / Login | Role | Demonstrates |
| :--- | :--- | :--- | :--- |
| **System Admin** | `admin@medchain.local` | `admin` | Infrastructure health, graph rebuild, store reset |
| **Primary Patient** | `patient@medchain.local` | `patient` | Access request approval, real-time revocation |
| **Attending Doctor**| `doctor@medchain.local` | `doctor` | Longitudinal encounter timeline, note entry |
| **Research Scientist**| `researcher@medchain.local`| `researcher`| Consent-gated queries, K-Means cohorting |
| **Insurance Analyst**| `analyst@medchain.local` | `insurance_analyst`| Transactional claim rollback, fraud queue |

In local demo mode, the header role switcher can change demo personas. Regular accounts sign in with their own credentials and do not get the demo role switcher.

---

## Detailed Documentation Links

- [System Architecture & Privacy Model](docs/ARCHITECTURE.md)
- [Implementation Plan & Phase Roadmap](docs/IMPLEMENTATION_PLAN.md)
- [Complete Entity-Relationship Schema (ERD)](docs/ERD.md)
- [API Reference & OpenAPI Specifications](docs/API.md)
- [Cryptographic Security & Threat Model](docs/SECURITY_AND_PRIVACY.md)
- [DBMS Normalization & Query Optimization Showcase](docs/DBMS_SHOWCASE.md)
- [12-Step Evaluation Demonstration Script](docs/DEMO_SCRIPT.md)

---

## Compliance & Privacy Standards

- **HIPAA Minimum Necessary Standard:** Direct identifiers are stripped from research queries. Only consented, de-identified aggregate vectors are accessible.
- **GDPR Article 17 (Right to Erasure / Revocation):** When a patient revokes consent, access is cut off immediately at the centralized policy engine.
- **Off-Chain Confidentiality:** No PHI, names, or cleartext notes are ever committed to the blockchain. All ledger anchors consist of salted SHA-256 cryptographic commitments.
