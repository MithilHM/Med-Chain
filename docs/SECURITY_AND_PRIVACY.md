# MedChain Security & Privacy Architecture

## 1. Threat Model & Security Boundaries

MedChain is a prototype that applies selected security controls; it has not been independently assessed and must not be treated as a certified zero-trust or regulated-health deployment. Its current boundaries are:

1. **Client Isolation:** The UI is an untrusted presentation layer. Frontend route guards or hidden buttons are not security boundaries. Protected API routes authenticate the short-lived session cookie and apply role and ownership checks.
2. **Horizontal Access Checks:** Doctors are checked against patients with whom they have a visit assignment. Patients can retrieve their own linked record. This is not a complete hospital tenant boundary or care-team assignment model.
3. **Vertical Privilege Escalation Prevention:** Researchers and Insurance Analysts are strictly barred from clinical narrative endpoints (`/documents/*`).
4. **Data Minimization:** Research query endpoints return aggregate metrics or de-identified feature records with synthetic pseudonyms; direct identifiers are stripped prior to SQL projection.

---

## 2. Off-Chain Commitment & Integrity Scheme

Storing healthcare records, diagnostic codes, or patient identities on a public or semi-private blockchain introduces catastrophic privacy and regulatory vulnerabilities (GDPR right to erasure, HIPAA violations, re-identification attacks).

### The MedChain Cryptographic Commitment Protocol:
1. **Deterministic Serialization:** The record object is serialized as sorted-key compact JSON before salted SHA-256 hashing. This implementation does not claim RFC 8785 conformance.
2. **Salt Generation:** A cryptographically secure 256-bit random salt ($S$) is generated per record version and stored strictly in PostgreSQL's private `record_integrity` table.
3. **Commitment Computation:**
   $$\text{Commitment Hash} = \text{SHA-256}(\text{CanonicalJSON} \parallel \text{Salt})$$
4. **On-Chain Anchoring:** The smart contract receives only the `opaque_reference` (a random UUID) and the 32-byte `commitment_hash`.
5. **Tamper Verification:**
   - Any modification to a character in MongoDB changes the computed hash.
   - Without the off-chain salt, rainbow table or dictionary precomputation attacks on medical text are infeasible.

---

## 3. Patient Consent Lifecycle & Centralized Policy Enforcement

Patient autonomy is central to the MedChain research engine:

```
[Researcher Submits Request]
             │
             v
    (Status: PENDING)
             │
             ├──> [Patient Approves] ──> Status: GRANTED (Blockchain event emitted)
             │                                │
             │                                ├──> Valid until Expiry: Queries ALLOWED
             │                                └──> [Patient Revokes] ──> Status: REVOKED (Blockchain event)
             │                                                                │
             │                                                                v
             │                                                      Queries strictly DENIED
             │
             └──> [Patient Rejects]  ──> Status: REJECTED (Queries DENIED)
```

### Denial-by-Default Policy:
- If a research project requests data without an explicit, active `consent` record for the target patient cohort, the engine rejects the authorization check.
- If the current UTC time exceeds `valid_until`, the policy engine treats the consent as expired and raises HTTP 403.
- Every decision (`GRANTED` or `DENIED`) is recorded in PostgreSQL's `access_event` table, with the request ID, and its chain evidence is queued in the transactional outbox in the same transaction. PostgreSQL rows are not inherently immutable; the chain copy is what makes later alteration detectable.

Revocation is serialized with data use: an authorized research query holds `FOR SHARE` locks on the consent rows it relies on until its transaction commits, and revocation takes `FOR UPDATE` on the consent row. A revocation therefore waits for queries already in flight, and every query that starts afterwards is denied. Exports a researcher has already downloaded cannot be recalled.

---

## 4. Identity, Sessions, and Emergency Access

- **Sessions fail closed.** Every token must map to a registered, unrevoked, unexpired `user_session` row. A correctly signed token without a session row is rejected.
- **Hospital SSO.** Staff sign in through the hospital identity provider (OIDC authorization code with PKCE; ID tokens verified against the provider's JWKS for signature, issuer, audience, expiry, nonce, and `at_hash`). Roles come only from mapped directory groups, and `OIDC_REQUIRE_MFA_CLAIM` can require `amr=mfa`.
- **Provisioning.** SCIM 2.0 creates, updates, and deactivates accounts; deactivation revokes every session immediately. Accounts are never hard-deleted.
- **MFA for local accounts.** RFC 6238 TOTP. Secrets are encrypted at rest, an accepted code's time step can never be reused, and recovery codes are single use and stored as hashes. `MFA_REQUIRED_ROLES` blocks sign-in for those roles until MFA is enrolled. Production refuses to start unless SSO is enabled or admins require MFA.
- **Sign-in protection.** Accounts lock for `LOGIN_LOCKOUT_MINUTES` after `LOGIN_MAX_FAILED_ATTEMPTS` failures, including failed MFA codes. A per-client rate limit is stored in the database, so it holds across replicas. Unknown emails take the same bcrypt time as known ones, and locked accounts get the same message as bad passwords.
- **Browser storage.** The web app relies only on the HttpOnly, SameSite=strict session cookie. JavaScript never stores bearer tokens.
- **Care relationships.** Doctors may open a chart through an active care-team assignment (from ADT feeds, FHIR, or onboarding), an open visit (or one discharged within `CARE_TEAM_POST_DISCHARGE_DAYS`), or an active break-the-glass grant. Cancelled visits grant nothing.
- **Patient names.** Stored AES-GCM encrypted and bound to the patient ID, with an HMAC blind index for exact family-name search. Names appear only in care-role endpoints (`/patients`, FHIR export), never in research, insurance, graph, ledger, events, alerts, or metrics.
- **Key management.** Every application ciphertext records its key ID. Keys rotate without downtime through the key ring and `scripts/rotate_encryption_key.py` (see [OPERATIONS.md](OPERATIONS.md)).
- **Break-the-glass.** Emergency access creates a time-boxed `emergency_access_grant` (default 4 hours) with a mandatory justification. It is honored by the access check, announced to administrators in real time, and placed in a compliance review queue (`GET /admin/break-glass`). Reviewers cannot review their own access, and an `INAPPROPRIATE` outcome revokes any remaining window immediately.

## 5. On-chain Pseudonymity

On-chain identifiers are `HMAC-SHA256(CHAIN_PSEUDONYM_KEY, internal_id)` rather than a bare hash. Internal UUIDs appear in URLs, logs, and exports; with a bare hash, anyone holding a UUID could find and link all its on-chain events. With the key, linking requires a secret held only by the hospital. Changing the key breaks lookups of existing anchors, so it must be managed like the document encryption key: stored in a secrets manager, backed up, and rotated only with a re-anchoring plan.

## 6. HTTP Response Hardening

All API responses carry `Cache-Control: no-store` (they may contain PHI), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, and an `X-Request-ID` that is also stored on audit events. HSTS is added outside development.
