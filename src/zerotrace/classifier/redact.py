"""Redaction MUST run before a candidate reaches a prompt, a log, or disk."""
import re

def redact(value: str, kind: str) -> str:
    """Return a typed, length-hinted token. Never returns the raw value."""
    return f"<{kind.upper()} len={len(value)}>"

_SECRETISH = re.compile(r"(AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]+PRIVATE KEY-----)")

def scrub_window(window: str) -> str:
    """Redact anything secret-looking in the context window sent to the model."""
    return _SECRETISH.sub("<REDACTED>", window)
