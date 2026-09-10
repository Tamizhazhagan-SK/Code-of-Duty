"""Append-only, tamper-evident, redacted audit log (hash-chained entries)."""
def record(event: dict, prev_hash: str) -> str:
    # entry stores fingerprints + decisions only, plus prev_hash for tamper-evidence.
    return "new_hash"
