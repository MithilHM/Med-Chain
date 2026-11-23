"""Minimal, dependency-free HL7 v2.x (ER7 pipe-delimited) parser and ACK builder.

Supports what MedChain consumes: MSH, EVN, PID, PV1, OBR, OBX segments, repetitions (~),
components (^), subcomponents (&), and the standard escape sequences. Field numbering follows
the HL7 standard (MSH-9 is the message type, PID-3 the identifier list, and so on).
"""
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import List, Optional

START_BLOCK = b"\x0b"
END_BLOCK = b"\x1c\x0d"


class HL7ParseError(ValueError):
    pass


@dataclass
class Segment:
    name: str
    fields: List[str]  # fields[n] is SEG-n (for MSH, fields[1] is MSH-1, the field separator)


@dataclass
class HL7Message:
    segments: List[Segment]
    field_sep: str = "|"
    component_sep: str = "^"
    repetition_sep: str = "~"
    escape_char: str = "\\"
    subcomponent_sep: str = "&"
    raw: str = field(default="", repr=False)

    def segments_named(self, name: str) -> List[Segment]:
        return [segment for segment in self.segments if segment.name == name]

    def first(self, name: str) -> Optional[Segment]:
        found = self.segments_named(name)
        return found[0] if found else None

    def _unescape(self, value: str) -> str:
        if self.escape_char not in value:
            return value
        e = self.escape_char
        replacements = {
            f"{e}F{e}": self.field_sep, f"{e}S{e}": self.component_sep, f"{e}T{e}": self.subcomponent_sep,
            f"{e}R{e}": self.repetition_sep, f"{e}E{e}": e, f"{e}.br{e}": "\n",
        }
        for token, replacement in replacements.items():
            value = value.replace(token, replacement)
        return value

    def value(self, segment: Optional[Segment], field_no: int, component: int = 1,
              repetition: int = 0, subcomponent: int = 1) -> str:
        """Return one atomic value (1-based component/subcomponent, 0-based repetition)."""
        if segment is None or field_no >= len(segment.fields):
            return ""
        reps = segment.fields[field_no].split(self.repetition_sep)
        if segment.name == "MSH" and field_no in (1, 2):
            return segment.fields[field_no]
        if repetition >= len(reps):
            return ""
        comps = reps[repetition].split(self.component_sep)
        if component > len(comps):
            return ""
        subs = comps[component - 1].split(self.subcomponent_sep)
        if subcomponent > len(subs):
            return ""
        return self._unescape(subs[subcomponent - 1]).strip()

    def repetitions(self, segment: Optional[Segment], field_no: int) -> int:
        if segment is None or field_no >= len(segment.fields) or not segment.fields[field_no]:
            return 0
        return len(segment.fields[field_no].split(self.repetition_sep))

    # Convenience accessors for the message header
    @property
    def msh(self) -> Segment:
        return self.segments[0]

    @property
    def message_type(self) -> str:
        code, trigger = self.value(self.msh, 9, 1), self.value(self.msh, 9, 2)
        return f"{code}^{trigger}" if trigger else code

    @property
    def control_id(self) -> str:
        return self.value(self.msh, 10)

    @property
    def sending_application(self) -> str:
        return self.value(self.msh, 3)

    @property
    def sending_facility(self) -> str:
        return self.value(self.msh, 4)

    @property
    def version(self) -> str:
        return self.value(self.msh, 12)


def parse_message(raw: str) -> HL7Message:
    if not raw or not raw.strip():
        raise HL7ParseError("Empty HL7 message.")
    text = raw.strip().strip("\x0b\x1c")
    lines = [line for line in text.replace("\r\n", "\r").replace("\n", "\r").split("\r") if line.strip()]
    if not lines or not lines[0].startswith("MSH") or len(lines[0]) < 8:
        raise HL7ParseError("Message must start with an MSH segment.")

    header = lines[0]
    field_sep = header[3]
    encoding = header[4:8]
    if len(encoding) < 4:
        raise HL7ParseError("MSH-2 encoding characters are incomplete.")
    component_sep, repetition_sep, escape_char, subcomponent_sep = encoding[0], encoding[1], encoding[2], encoding[3]

    segments = []
    for line in lines:
        parts = line.split(field_sep)
        name = parts[0].strip()
        if len(name) != 3 or not name.isalnum():
            raise HL7ParseError(f"Invalid segment name: {name[:10]!r}")
        if name == "MSH":
            # MSH-1 is the separator itself, so shift: fields[1] = "|", fields[2] = encoding chars.
            parts = ["MSH", field_sep] + parts[1:]
        segments.append(Segment(name, parts))

    message = HL7Message(segments, field_sep, component_sep, repetition_sep, escape_char, subcomponent_sep, raw)
    if not message.control_id:
        raise HL7ParseError("MSH-10 message control ID is required.")
    if not message.value(message.msh, 9, 1):
        raise HL7ParseError("MSH-9 message type is required.")
    return message


def parse_hl7_datetime(value: str) -> Optional[datetime]:
    """Parse HL7 DTM (YYYY[MM[DD[HH[MM[SS[.S+]]]]]][+/-ZZZZ]); naive values are treated as UTC."""
    if not value:
        return None
    value = value.strip()
    offset = None
    for sign in ("+", "-"):
        idx = value.find(sign, 8)
        if idx > 0:
            value, offset = value[:idx], value[idx:]
            break
    value = value.split(".")[0]
    formats = {4: "%Y", 6: "%Y%m", 8: "%Y%m%d", 10: "%Y%m%d%H", 12: "%Y%m%d%H%M", 14: "%Y%m%d%H%M%S"}
    fmt = formats.get(len(value))
    if not fmt:
        return None
    try:
        parsed = datetime.strptime(value, fmt)
    except ValueError:
        return None
    if offset and len(offset) == 5:
        try:
            parsed = datetime.strptime(value + offset, fmt + "%z")
            return parsed.astimezone(timezone.utc)
        except ValueError:
            pass
    return parsed.replace(tzinfo=timezone.utc)


def parse_hl7_date(value: str) -> Optional[date]:
    parsed = parse_hl7_datetime(value[:8] if value else value)
    return parsed.date() if parsed and len(value.strip()) >= 8 else None


def build_ack(message: Optional[HL7Message], ack_code: str, text: str, receiving_app: str = "MEDCHAIN",
              receiving_facility: str = "MEDCHAIN", original_control_id: str = "") -> str:
    """Build an HL7 v2 ACK. ack_code: AA (accepted), AE (error, sender may retry), AR (rejected)."""
    now = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    clean = text.replace("|", " ").replace("^", " ").replace("~", " ").replace("\\", " ").replace("&", " ")[:200]
    if message is not None:
        trigger = message.value(message.msh, 9, 2)
        sending_app, sending_facility = message.sending_application, message.sending_facility
        control_id = message.control_id
        version = message.version or "2.5.1"
    else:
        trigger, sending_app, sending_facility, control_id, version = "", "", "", original_control_id, "2.5.1"
    msh = "|".join([
        "MSH", "^~\\&", receiving_app, receiving_facility, sending_app, sending_facility, now, "",
        f"ACK^{trigger}^ACK" if trigger else "ACK", uuid.uuid4().hex[:20].upper(), "P", version,
    ])
    msa = "|".join(["MSA", ack_code, control_id, clean])
    return f"{msh}\r{msa}\r"


def frame_mllp(payload: str) -> bytes:
    return START_BLOCK + payload.encode("utf-8") + END_BLOCK
