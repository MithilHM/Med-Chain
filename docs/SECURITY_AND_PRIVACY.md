# MedChain Security & Privacy Architecture

## 1. Threat Model & Security Boundaries

MedChain operates under a zero-trust model between client layers and healthcare data backends:

1. **Client Isolation:** The UI is an untrusted presentation layer. Frontend route guards or hidden buttons are not security boundaries. Every API route independently authenticates the JWT bearer token and enforces granular RBAC and ownership constraints.
2. **Horizontal Privilege Escalation Prevention:** Doctors can only query patients assigned to their hospital or care team. Patients can only retrieve their own record. URL identifier manipulation (`/patients/<arbitrary-uuid>`) strictly fails with `403 Forbidden` if ownership does not match.
3. **Vertical Privilege Escalation Prevention:** Researchers and Insurance Analysts are strictly barred from clinical narrative endpoints (`/documents/*`).
4. **Data Minimization:** Research query endpoints return aggregate metrics or de-identified feature records with synthetic pseudonyms; direct identifiers are stripped prior to SQL projection.

---

## 2. Off-Chain Commitment & Integrity Scheme

Storing healthcare records, diagnostic codes, or patient identities on a public or semi-private blockchain introduces catastrophic privacy and regulatory vulnerabilities (GDPR right to erasure, HIPAA violations, re-identification attacks).

### The MedChain Cryptographic Commitment Protocol:
1. **Deterministic Canonicalization:** The record object (or document JSON) is transformed into RFC 8785 canonical JSON with sorted keys and normalized whitespace.
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
- If a research project requests data without an explicit, active `consent` record for the target patient cohort, the engine rejects the request immediately.
- If the current UTC time exceeds `valid_until`, the policy engine treats the consent as expired and raises HTTP 403.
- Every decision (`GRANTED` or `DENIED`) is recorded immutably in PostgreSQL's `access_event` table and mirrored to the local chain.
