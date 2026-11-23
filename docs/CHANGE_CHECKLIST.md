# MedChain Change Checklist

This checklist tracks the implementation work completed in this project session and the remaining essential work. Completed items are checked; unchecked items are still pending.

For the prioritized static audit, confirmed risks, and optional improvements, see [REVIEW_BACKLOG.md](REVIEW_BACKLOG.md).

## Completed

- [x] Added login and token-based API authentication, shared frontend API client, authentication shell, and demo role switching limited to development/test demo mode.
- [x] Enforced patient ownership, doctor assignment, consent scope, expiry, and revocation checks for protected records and documents.
- [x] Added research access checks, minimum cohort-size protections, and small-cell suppression based on distinct contributing patients for aggregate diagnosis and prescription totals.
- [x] Encrypted semi-structured clinical document payloads with AES-256-GCM, added production key validation, and supported lazy migration of legacy plaintext documents.
- [x] Kept sensitive medical payloads off-chain and clarified integrity outcomes for verified, mismatched, and missing documents.
- [x] Restricted SQLite fallback, demo reset, and tampering controls to explicitly permitted development/demo use; added database URL validation and safe unavailable-database responses.
- [x] Restricted synthetic demo seeding and its predictable demo accounts to development/test demo mode.
- [x] Added startup schema initialization and compensating cleanup when a cross-store document write fails.
- [x] Scoped insurance analyst policy, claim, anomaly, and expenditure operations to the analyst's assigned provider.
- [x] Added database and best-effort chain audit events for relevant patient and insurance access/actions.
- [x] Updated README and API documentation for implemented security and provider-scope behavior.
- [x] Corrected system health reporting to show degraded state when any backing store is falling back or blockchain evidence is unavailable; the response identifies degraded services.
- [x] Fixed graph rebuild refresh to reload data with the current user role and selected research project.
- [x] Added an admin-only interactive DBMS showcase with fixed read-only SQL examples, aggregate small-group suppression, and an indexed lookup plan.
- [x] Updated admin service cards to distinguish live stores, local fallbacks, unsynchronized graph state, and unavailable services.
- [x] Cleared stale integrity verification state after a successful tamper demo and marked the stored verification as unverified pending a new check.
- [x] Fixed demo seed/reset script path resolution for both local and Docker layouts.
- [x] Added a relational check constraint preventing approved claim amounts from exceeding the claimed amount, matching the existing API validation.
- [x] Added a relational check that each claim line total equals quantity times unit cost.
- [x] Constrained consent and claim status values to the states used by the API and demo data.
- [x] Filtered the sidebar modules by the signed-in role and refreshed navigation when login, logout, or demo role changes; backend authorization remains enforced independently.
- [x] Made dashboard metrics and demo links role appropriate; researcher graph metrics now use an active project consent scope instead of an unscoped request.
- [x] Counted a consent as active on the dashboard only when it is granted, unrevoked, and inside its validity window.
- [x] Deduplicated claims per disease in insurer expenditure analytics so repeated diagnosis rows do not inflate claim amounts.
- [x] Disabled local encrypted JSON document fallback outside development and test; production reports the document store as unavailable and fails closed when MongoDB is down.
- [x] Corrected architecture documentation to describe current inline blockchain calls and admin-triggered graph rebuilds instead of claiming an implemented outbox worker.
- [x] Integrity verification compares the local record commitment and version against the deployed contract; the UI distinguishes a confirmed chain match from a local hash match with an unanchored or unavailable chain.
- [x] Removed unsupported RFC 8785 conformance claims; the implementation uses deterministic sorted-key compact JSON serialization.
- [x] Separated live Neo4j synchronization status from the in-memory fallback so failed live rebuilds no longer appear healthy; the admin endpoint now reports a service failure.
- [x] Replaced per-record graph rebuild lookups with joined relational reads to avoid N+1 database round trips.
- [x] Marked live graph rebuilds as syncing before relational extraction so failures cannot leave stale success status visible.
- [x] Kept internal cohort clustering exceptions in server logs instead of returning database or library details to API clients.
- [x] Restricted detailed health and blockchain diagnostics to admins; `/api/v1/health` now exposes only a minimal public liveness status.
- [x] Validated PostgreSQL URL overrides for strong embedded credentials, supported async/sync drivers, and a shared database target.
- [x] Blockchain health and contract use now require a matching RPC chain ID and deployed contract bytecode; missing or mismatched chain evidence reports degraded status.
- [x] Replaced browser-stored bearer tokens with short-lived HttpOnly session cookies; logout invalidates previously issued account tokens.
- [x] Removed automatic demo-doctor sign-in, disabled API docs outside development/test, and restricted CORS methods and headers.
- [x] Removed static test/build badges and clarified that this is a prototype not ready for real patient data.

### 2026-11-22: real-time integration and reliability pass

- [x] Regenerated the Alembic baseline from the models (the previous one was missing four tables and many columns) and added migration `002`; verified upgrade, zero drift, downgrade, and re-upgrade.
- [x] Implemented the transactional outbox end to end: producers enqueue in the authoritative transaction; a background worker delivers with backoff, idempotent on-chain checks, stale-claim recovery, and single-sender election. An unavailable chain no longer counts as delivered.
- [x] Closed the consent-revocation race with `FOR SHARE` / `FOR UPDATE` locking.
- [x] Made session checks fail closed; added account lockout, login rate limiting, and timing-equalized sign-in.
- [x] Added HL7 v2 real-time ingestion (`ADT^A01/A04/A08/A03`, `ORU^R01`) over MLLP (TLS/mTLS) and HTTPS with per-source keys, an encrypted idempotent ledger, identifier-only patient matching, a review queue, and reprocessing.
- [x] Added a Server-Sent Events stream with per-patient authorization and session re-validation, plus a live clinical feed on the dashboard.
- [x] Rewrote FHIR import to remove default patients, invented demographics and timestamps, first-row doctor/hospital assignment, and unverified `VERIFIED_MATCH` status.
- [x] Made break-the-glass grants real (honored by access checks) with a compliance review queue; added care-team assignments.
- [x] Made document amendments non-destructive, integrity-gated, session-attributed, and anchored with increasing versions.
- [x] Moved web3 calls off the event loop, serialized nonces, and switched on-chain references to keyed HMAC pseudonyms.
- [x] Hardened `MedChainAudit` (authorized writers, no consent re-grant, increasing record versions) and stopped deploying the deprecated `MedChainTrustLayer`.
- [x] Returned HTTP 503 for document-store outages; added request IDs and security headers (`Cache-Control: no-store`).
- [x] Fixed the `/admin/sessions` crash, the ungated `/graph/path-query`, the fabricated disaster-recovery status, and the invalid token lifetime in `.env.example`.
- [x] Bound backing-service ports to localhost in Compose and added an optional MLLP service.
- [x] Added CI jobs for contract tests and PostgreSQL migrations.

### 2026-11-22: identity, clinical lifecycle, and operations pass

- [x] Hospital SSO (OIDC with PKCE), SCIM 2.0 provisioning and deprovisioning, TOTP MFA with recovery codes and replay protection, MFA-required roles, and a bootstrap-admin script.
- [x] Database-backed login rate limiting shared by all replicas.
- [x] Encrypted patient names with blind-index search, captured from HL7 `PID-5` and FHIR, shown to care roles only.
- [x] HL7 `A02` transfer, `A11` cancel admit, `A13` cancel discharge, and approval-gated `A40` merges (two-person rule); merged records are read-only.
- [x] Care-team and visit-based access end after discharge; cancelled visits grant nothing.
- [x] Single-hospital boundary via `HOSPITAL_FACILITY_CODES`.
- [x] PostgreSQL `LISTEN/NOTIFY` event fan-out across API replicas and the MLLP listener.
- [x] Monitoring: alert lifecycle, webhook notifications, Prometheus `/metrics`, Operations console.
- [x] Encryption key ring with key IDs, a rotation job and script, and a status endpoint.
- [x] Atomic, pseudonymous Neo4j rebuild; removed the invented side-effect results; live graph health.
- [x] Batched and paginated timeline, document list, and audit list.
- [x] Ledger transactions: gas estimation, EIP-1559, confirmations, secret-file signing key.
- [x] Migration `003`; CI jobs for PostgreSQL concurrency and the live chain.
- [x] Frontend: SSO and MFA sign-in, the Account Security page, the Operations console, patient names in charts.
- [x] Docs: [OPERATIONS.md](OPERATIONS.md) runbook; updated integration, readiness, security, and architecture docs.

### 2026-11-23: sign-up, patient administration, and clinical entry

- [x] Patient-portal sign-up with a one-time activation code issued at registration plus date-of-birth check; codes are hashed, expire, and lock after 5 failures.
- [x] Staff accounts created by administrators with one-time activation links; password-reset links, MFA reset, role changes, and deactivation (sessions revoked); change-password for signed-in users; a password policy.
- [x] Patient registration restricted to administrators, with name, registering hospital (MRN authority), primary doctor, and optional portal code. New patients now appear in the primary doctor's list.
- [x] Care-team management, audited demographic corrections, and server-side search by MRN fragment or family name.
- [x] Clinical data entry: encounters that work for brand-new patients (previously the UI sent placeholder doctor/hospital IDs), diagnoses, prescriptions, lab results with automatic abnormal flags, discharge, and an allergy list.
- [x] Hospital directory and doctor directory endpoints; Users & Hospitals admin page; sign-up page.
- [x] Fixed chart display bugs: hardcoded facility name, `Ref: undefined` on labs, `undefined` in the break-glass confirmation, and the patient search ignoring names.
- [x] Migration `004`.

## Essential work still pending (requires the hospital)

- [ ] Register MedChain in the hospital IdP, map directory groups, and connect SCIM.
- [ ] Validate the HL7 interface end to end with the hospital's test feed; register all facility codes and provider IDs.
- [ ] Stand up a permissioned ledger network with an HSM-backed signer.
- [ ] Provision TLS, encrypted storage and backups, and a secrets manager; record a restore drill.
- [ ] Load-test and run failure drills; wire alerts to on-call.
- [ ] Obtain privacy, security, legal, and clinical-safety approvals and an independent penetration test.
