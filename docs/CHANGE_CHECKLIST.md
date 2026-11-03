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

## Essential work still pending

- [ ] Add revocable browser sessions and production deployment hardening.
- [ ] Implement transactional outbox delivery and close the consent-revocation race for concurrent research queries.
- [ ] Make Neo4j rebuilds atomic and health checks reflect live connectivity/freshness.
- [ ] Return HTTP 503 for unavailable document storage instead of an unhandled 500.
- [ ] Replace static README pass-count badges with commit-backed CI results.
- [ ] Start the app with the documented local setup and confirm the core patient, consent, research, document, insurance, integrity, graph, and health workflows operate together.
- [ ] Resolve any startup or workflow failures found during that hands-on verification.
- [ ] Add an initial versioned database migration and review schema-level constraints. Alembic dependency/configuration are present, but there are no revision files yet and API startup still relies on `create_all`; this workspace currently has no installed Python runtime or project virtual environment to generate the revision from the models.
