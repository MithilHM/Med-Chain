# Real-time Clinical Integration (HL7 v2 and FHIR)

This guide is for the hospital integration team connecting an interface engine (Mirth Connect, Rhapsody, Infor Cloverleaf, or similar) to MedChain. MedChain is still a prototype: connect it only to a test feed carrying synthetic or properly approved data until the gates in [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) are met.

## Transports

| Transport | Endpoint | Authentication | Use when |
| --- | --- | --- | --- |
| MLLP over TCP | `python -m src.integration.mllp_server` (default `127.0.0.1:2575`) | Network isolation; TLS with `MLLP_TLS_CERT_FILE`/`MLLP_TLS_KEY_FILE`; client certificates with `MLLP_TLS_CLIENT_CA_FILE` | Standard ADT/ORU feeds from the interface engine |
| HTTPS | `POST /api/v1/integration/hl7v2` (body: one ER7 message, `Content-Type: x-application/hl7-v2+er7`) | `X-Integration-Key` header | Engines that prefer HTTP destinations |
| FHIR R4 | `POST /api/v1/fhir/import` (Bundle) | Clinician or admin session | Batch or document-style exchange |

Both HL7 transports run the same processing code and return an HL7 `ACK`.

### Issuing an integration key

Keys are configured per source system; only their SHA-256 hashes are stored:

```bash
python -c "import secrets,hashlib;k=secrets.token_urlsafe(32);print('key :',k);print('hash:',hashlib.sha256(k.encode()).hexdigest())"
# .env
INTEGRATION_API_KEYS=mirth-main:<hash>,lab-lis:<hash2>
```

Give the key to the engine; the source name (`mirth-main`) becomes the ledger's `source_system`. Rotate by adding the new hash, switching the engine, then removing the old hash.

## Supported messages

| Message | Effect | Patient may be created? |
| --- | --- | --- |
| `ADT^A01` admit, `ADT^A04` register | Match or create the patient, upsert the visit by `PV1-19`, put the `PV1-7` attending doctor on the care team | Yes, if `PID-7` DOB and `PID-8` sex are present |
| `ADT^A02` transfer | Update the visit location (`PV1-3`) and, if `PV1-7` changed, add the new attending doctor to the care team | No |
| `ADT^A03` discharge | Set the discharge time (`PV1-45`, else `EVN-2`); admission-based access ends `CARE_TEAM_POST_DISCHARGE_DAYS` later | No |
| `ADT^A08` update | Update DOB, sex, and name of an identifier-matched patient | No |
| `ADT^A11` cancel admit | Mark the visit `CANCELLED` and end its care-team access. Refused (review) if results, diagnoses, or documents are attached | No |
| `ADT^A13` cancel discharge | Clear the discharge time and reopen care-team access | No |
| `ADT^A40` merge | Record a merge request (`PID-3` survivor, `MRG-1` duplicate). Nothing is merged until an administrator approves it | No |
| `ORU^R01` results | Upsert numeric (`NM`/`SN`) `OBX` results on the `PV1-19` visit; `OBX-11 = C` corrects an existing result | No |

Anything else is rejected with `AR`. Non-numeric `OBX` values are reported as warnings; narrative results should be sent as documents.

## Field mapping

| HL7 field | MedChain use |
| --- | --- |
| `MSH-4` sending facility (or `PV1-3.4`, else `INTEGRATION_DEFAULT_FACILITY`) | `hospital.facility_code` |
| `MSH-10` control ID | Idempotency key, unique per source system |
| `PID-3` (repeating CX: `id^^^authority^type`) | `patient_identifier (system = authority, value = id)` |
| `PID-5` (XPN `family^given`) | Patient name, AES-GCM encrypted, with a keyed blind index for exact family-name search. Shown to care roles only |
| `PID-7`, `PID-8` | Date of birth, sex (M/F/O; U is ignored) |
| `MRG-1` | Prior (duplicate) identifier in `A40` |
| `PV1-2` | Visit type (I inpatient, O outpatient, E emergency, ...) |
| `PV1-7.1` | `doctor.external_provider_id` (NPI or staff number) |
| `PV1-19.1` | `visit.external_visit_number`, unique per hospital |
| `PV1-44` / `PV1-45` | Admit / discharge time |
| `OBX-3` (code^text^system) | `lab_test.code` (created on first sight with `OBX-6` unit and `OBX-7` range) |
| `OBX-5`, `OBX-8`, `OBX-11`, `OBX-14` | Value, abnormal flag (`H/L/HH/LL/A/AA`), status, observation time |

Before go-live, register every facility code and provider ID that will appear in the feed, and set `HOSPITAL_FACILITY_CODES` to the facilities this installation serves. Messages for any other facility are rejected with `AR`, so another hospital's data can never land in this database.

## Merges

`A40` and operator-proposed merges create a request in **Operations → Patient merge approvals** (`GET /api/v1/integration/merges`). Approval:
- requires a different administrator from the one who proposed it, and identical dates of birth;
- moves visits, documents, adverse events, coverage, consents, access requests, identifiers, care-team assignments, and emergency grants to the surviving record, in one transaction;
- leaves the duplicate as a read-only `MERGED` record pointing at the survivor (writes return 409; FHIR exports include `link: replaced-by`);
- leaves audit history untouched.

Unmerge (`A37`) is not automated; correct it in the source system and contact support.

## Patient matching rules

Wrong-patient matches are a patient-safety event, so matching is deliberately conservative:

1. Match only on an exact `(assigning authority, identifier)` pair from `PID-3`.
2. Identifiers that resolve to two different patients → review.
3. A match whose DOB or sex disagrees (except on `A08`) → review; records are never merged automatically.
4. Lab results and discharges never create patients.
5. Nothing is defaulted: a new patient needs a real DOB and sex, and an event needs a real timestamp.

Probabilistic matching on name and address is not implemented. If the hospital runs an EMPI, send its identifier as another `PID-3` repetition with its own assigning authority.

## Acknowledgements

| `MSA-1` | Meaning | Engine action |
| --- | --- | --- |
| `AA` | Processed, a duplicate, or stored and queued for manual review | Do not resend |
| `AR` | Unparseable, unsupported, invalid content, or a reused control ID with different content | Fix the message, then resend with a new control ID |
| `AE` | Temporary internal problem (for example, the database is down) | Retry with backoff |

`MSA-3` carries a short reason. Over HTTPS the same values are in the `X-MedChain-Ack-Code` and `X-MedChain-Message-Status` headers; add `?format=json` for a JSON summary while testing.

## Operations

- **Ledger:** every message is stored once in `inbound_message` with an AES-GCM-encrypted raw copy and a SHA-256 of the content. An HMAC commitment of each processed message is anchored on-chain through the outbox as provenance.
- **Review queue:** `GET /api/v1/integration/messages?status=NEEDS_REVIEW` (admin) lists messages that need a decision and why. Fix the cause (register the provider or facility, reconcile the patient), then `POST /api/v1/integration/messages/{id}/reprocess`.
- **Status:** `GET /api/v1/integration/status` shows counts by status and the last message time. A rising `NEEDS_REVIEW` count, or a stale last-message time during working hours, should page the integration on-call.
- **Real-time delivery:** processed messages publish events (`encounter.admitted`, `lab_result.created` with `abnormal`/`critical` flags, `integration.needs_review`) to `GET /api/v1/events/stream` for authorized users.

## Example

```text
MSH|^~\&|EPIC|MAMC|MEDCHAIN|MEDCHAIN|20261120083000||ADT^A01^ADT_A01|MSG00001|P|2.5.1
EVN|A01|20261120083000
PID|1||MRN12345^^^MAMC^MR||DOE^JANE||19700101|F
PV1|1|I|ICU^101^A^MAMC||||PRV-1001^CHEN^SARAH|||||||||||V-778899
```

```bash
curl -X POST "https://medchain.example.org/api/v1/integration/hl7v2?format=json" \
  -H "X-Integration-Key: $MEDCHAIN_KEY" -H "Content-Type: x-application/hl7-v2+er7" \
  --data-binary @adt_a01.hl7
```

## Known limits

- Addresses, phone numbers, and next of kin (`PID-11`, `PID-13`, `NK1`) are not stored.
- Only numeric observations are stored as lab results. Orders (`ORM`/`OML`), pharmacy (`RDE`/`RAS`), scheduling (`SIU`), and unmerge (`A37`) are not handled.
- Real-time events reach every API replica and the MLLP listener through PostgreSQL `LISTEN/NOTIFY`. With the SQLite development fallback, events from a separately running MLLP listener do not reach the API.
