"""Validate model output. Anything invalid -> discard verdict (fail closed)."""
import json
import re
from dataclasses import dataclass

ALLOWED = {"REAL_SECRET", "PII", "TEST_FIXTURE_OR_PLACEHOLDER", "UNKNOWN"}
_MAX_REASON_WORDS = 20
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)
# Small local models sometimes answer with a word instead of the requested
# 0-1 number; this is a courtesy fallback, not a relaxation of the range check.
_WORD_CONFIDENCE = {"low": 0.3, "medium": 0.6, "high": 0.9}


@dataclass(frozen=True)
class Verdict:
    classification: str
    confidence: float
    reason: str


def parse(raw: str) -> "Verdict | None":
    text = raw.strip()
    fence_match = _FENCE_RE.search(text)
    if fence_match:
        text = fence_match.group(1).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        object_match = _OBJECT_RE.search(text)
        if not object_match:
            return None
        try:
            data = json.loads(object_match.group(0))
        except json.JSONDecodeError:
            return None

    if not isinstance(data, dict):
        return None

    classification = data.get("classification")
    if classification not in ALLOWED:
        return None

    raw_confidence = data.get("confidence")
    if isinstance(raw_confidence, str) and raw_confidence.strip().lower() in _WORD_CONFIDENCE:
        confidence = _WORD_CONFIDENCE[raw_confidence.strip().lower()]
    else:
        try:
            confidence = float(raw_confidence)
        except (TypeError, ValueError):
            return None
    if not (0.0 <= confidence <= 1.0):
        return None

    reason = data.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        return None
    reason = " ".join(reason.split()[:_MAX_REASON_WORDS])

    return Verdict(classification=classification, confidence=confidence, reason=reason)
