"""Time-bound, reasoned exceptions keyed by finding fingerprint.

Two stores, read in this order:

1. `.zerotrace-exceptions.json` in the repo root, **committed and reviewed like code**. An
   exception silences a security control, so it belongs in a pull request where a second person
   sees the reason and the expiry, not in a file only its author can see.
2. `.git/zerotrace/exceptions.json`, private to the developer. This is where the interactive
   `[E]` flow writes, so nobody is forced to commit a file mid-commit; `zerotrace exceptions
   --promote` moves entries into the shared file when they are ready to be reviewed.

Both store fingerprints only (rule + path + hash of the line), never values, and both expire.
"""
import json
import os
from datetime import UTC, datetime, timedelta

from .. import gitutil

SHARED_FILE = ".zerotrace-exceptions.json"


def shared_path() -> str:
    return os.path.join(gitutil.repo_root(), SHARED_FILE)


def local_path() -> str:
    return os.path.join(gitutil.state_dir(), "exceptions.json")


def _read(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    entries = data.get("exceptions", data)          # tolerate both shapes
    return entries if isinstance(entries, dict) else {}


def _write(path: str, entries: dict, shared: bool) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    payload: dict = {"exceptions": entries}
    if shared:
        payload = {
            "note": "Reviewed exceptions. Each one silences a finding until it expires; "
                    "fingerprints only, never values. Changes belong in a pull request.",
            "exceptions": entries,
        }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")


def _entry(reason: str, ttl_days: int) -> dict:
    now = datetime.now(UTC)
    return {
        "reason": reason,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(days=ttl_days)).isoformat(),
    }


def add(fingerprint: str, reason: str, ttl_days: int, shared: bool = False) -> str:
    """Record an exception. Returns the path it was written to."""
    path = shared_path() if shared else local_path()
    entries = _read(path)
    entries[fingerprint] = _entry(reason, ttl_days)
    _write(path, entries, shared)
    return path


def _active(entry: dict) -> bool:
    try:
        return datetime.now(UTC) < datetime.fromisoformat(entry["expires_at"])
    except (KeyError, TypeError, ValueError):
        return False        # an unparseable exception is not an exception


def is_active(fingerprint: str) -> bool:
    for path in (shared_path(), local_path()):
        entry = _read(path).get(fingerprint)
        if entry and _active(entry):
            return True
    return False


def listing() -> list[dict]:
    """Every exception in both stores, newest first, for `zerotrace exceptions`."""
    rows = []
    for scope, path in (("shared", shared_path()), ("local", local_path())):
        for fingerprint, entry in _read(path).items():
            rows.append({
                "scope": scope, "fingerprint": fingerprint,
                "reason": entry.get("reason", ""),
                "expires_at": entry.get("expires_at", ""),
                "active": _active(entry),
            })
    return sorted(rows, key=lambda row: row["expires_at"], reverse=True)


def promote() -> tuple[int, str]:
    """Move every still-active local exception into the shared, reviewable file."""
    local = _read(local_path())
    movable = {k: v for k, v in local.items() if _active(v)}
    if not movable:
        return 0, shared_path()
    shared = _read(shared_path())
    shared.update(movable)
    _write(shared_path(), shared, shared=True)
    _write(local_path(), {k: v for k, v in local.items() if k not in movable}, shared=False)
    return len(movable), shared_path()


def prune() -> int:
    """Drop expired entries from both stores. Returns how many were removed."""
    removed = 0
    for path, shared in ((shared_path(), True), (local_path(), False)):
        entries = _read(path)
        if not entries:
            continue
        keep = {k: v for k, v in entries.items() if _active(v)}
        removed += len(entries) - len(keep)
        if len(keep) != len(entries):
            _write(path, keep, shared)
    return removed
