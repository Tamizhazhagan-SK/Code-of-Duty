"""Shared detector output type. Detectors only find; they never decide policy."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Finding:
    rule_id: str            # e.g. "AWS Access Key", "pii_email_internal"
    kind: str                # slug used by policy/remediation, e.g. "aws_access_key"
    severity: str             # critical | high | medium | low
    confidence: float
    path: str
    line_no: int
    file_class: str          # code | config | test | docs | generated
    line_text: str = ""      # the exact staged line, used to build a fix diff
    context_snippet: str = ""
    # In-memory only: never logged, printed, or sent anywhere unredacted.
    matched_value: str = field(default="", repr=False, compare=False)
