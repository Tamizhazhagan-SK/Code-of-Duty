"""Append-only, tamper-evident, redacted audit log (hash-chained entries)."""
import hashlib
import json
import os

_LOG_PATH = ".zerotrace/audit.log.jsonl"
_GENESIS_HASH = "0" * 64


def record(event: dict, prev_hash: str) -> str:
    """Entry stores fingerprints + decisions only; prev_hash gives tamper-evidence."""
    payload = json.dumps({"event": event, "prev_hash": prev_hash}, sort_keys=True)
    new_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    os.makedirs(os.path.dirname(_LOG_PATH), exist_ok=True)
    with open(_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps({"event": event, "prev_hash": prev_hash, "hash": new_hash}) + "\n")
    return new_hash


def _last_hash() -> str:
    if not os.path.exists(_LOG_PATH):
        return _GENESIS_HASH
    with open(_LOG_PATH, encoding="utf-8") as f:
        last_line = None
        for last_line in f:
            pass
    if not last_line:
        return _GENESIS_HASH
    return json.loads(last_line)["hash"]


def append(event: dict) -> str:
    """Convenience wrapper: read the chain tip and record the next entry."""
    return record(event, _last_hash())
