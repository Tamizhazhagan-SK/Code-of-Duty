"""Time-bound, reasoned exceptions keyed by finding fingerprint."""
import json
import os
from datetime import datetime, timedelta, UTC

from .. import gitutil


def _store_path() -> str:
    return os.path.join(gitutil.state_dir(), "exceptions.json")


def _load() -> dict:
    path = _store_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _save(data: dict) -> None:
    path = _store_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)


def add(fingerprint: str, reason: str, ttl_days: int) -> None:
    data = _load()
    expires_at = datetime.now(UTC) + timedelta(days=ttl_days)
    data[fingerprint] = {"reason": reason, "expires_at": expires_at.isoformat()}
    _save(data)


def is_active(fingerprint: str) -> bool:
    entry = _load().get(fingerprint)
    if not entry:
        return False
    expires_at = datetime.fromisoformat(entry["expires_at"])
    return datetime.now(UTC) < expires_at
