"""Time-bound, reasoned exceptions keyed by finding fingerprint."""
import json
import os
from datetime import datetime, timedelta, timezone

_STORE_PATH = ".zerotrace/exceptions.json"


def _load() -> dict:
    if not os.path.exists(_STORE_PATH):
        return {}
    try:
        with open(_STORE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _save(data: dict) -> None:
    os.makedirs(os.path.dirname(_STORE_PATH), exist_ok=True)
    with open(_STORE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)


def add(fingerprint: str, reason: str, ttl_days: int) -> None:
    data = _load()
    expires_at = datetime.now(timezone.utc) + timedelta(days=ttl_days)
    data[fingerprint] = {"reason": reason, "expires_at": expires_at.isoformat()}
    _save(data)


def is_active(fingerprint: str) -> bool:
    entry = _load().get(fingerprint)
    if not entry:
        return False
    expires_at = datetime.fromisoformat(entry["expires_at"])
    return datetime.now(timezone.utc) < expires_at
