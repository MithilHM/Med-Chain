"""Builders for HL7 v2 test messages (each value placed at its exact field number)."""
import uuid
from datetime import datetime, timezone


def ts(dt: datetime | None = None) -> str:
    return (dt or datetime.now(timezone.utc)).strftime("%Y%m%d%H%M%S")


def segment(name: str, values: dict) -> str:
    fields = [""] * (max(values) + 1)
    fields[0] = name
    for number, value in values.items():
        fields[number] = value
    return "|".join(fields)


def control_id(prefix: str = "T") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def adt(event: str, mrn: str, visit_number: str, *, provider: str = "PRV-1001", dob: str = "19700101",
        sex: str = "F", name: str = "DOE^JANE", location: str = "ICU^101^A^MAMC", extra_pv1: dict | None = None,
        extra_segments: list | None = None) -> str:
    pv1 = {1: "1", 2: "I", 3: location, 7: f"{provider}^CHEN^SARAH", 19: visit_number}
    pv1.update(extra_pv1 or {})
    return "\r".join([
        f"MSH|^~\\&|EPIC|MAMC|MEDCHAIN|MEDCHAIN|{ts()}||ADT^{event}^ADT_A01|{control_id(event)}|P|2.5.1",
        f"EVN|{event}|{ts()}",
        f"PID|1||{mrn}^^^MAMC^MR||{name}||{dob}|{sex}",
        segment("PV1", pv1),
        *(extra_segments or []),
    ])


def oru(mrn: str, visit_number: str, code: str = "2823-3", value: str = "4.1", flag: str = "N") -> str:
    return "\r".join([
        f"MSH|^~\\&|LAB|MAMC|MEDCHAIN|MEDCHAIN|{ts()}||ORU^R01^ORU_R01|{control_id('ORU')}|P|2.5.1",
        f"PID|1||{mrn}^^^MAMC^MR",
        segment("PV1", {1: "1", 2: "I", 3: "ICU^101^A^MAMC", 7: "PRV-1001", 19: visit_number}),
        f"OBR|1|ORD1|FIL1|{code}^Test^LN|||{ts()}",
        f"OBX|1|NM|{code}^Test^LN||{value}|mmol/L|3.5-5.1|{flag}|||F|||{ts()}",
    ])


async def post_hl7(client, headers, message: str) -> dict:
    res = await client.post("/api/v1/integration/hl7v2?format=json", content=message.encode("utf-8"),
                            headers={**headers, "Content-Type": "x-application/hl7-v2+er7"})
    assert res.status_code == 200, res.text
    return res.json()
