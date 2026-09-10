"""Validate model output. Anything invalid -> discard verdict (fail closed)."""
from dataclasses import dataclass

ALLOWED = {"REAL_SECRET", "PII", "TEST_FIXTURE_OR_PLACEHOLDER", "UNKNOWN"}

@dataclass(frozen=True)
class Verdict:
    classification: str
    confidence: float
    reason: str

def parse(raw: str) -> "Verdict | None":
    # json.loads -> check keys, enum, 0<=conf<=1, reason len, no value echo.
    return None
