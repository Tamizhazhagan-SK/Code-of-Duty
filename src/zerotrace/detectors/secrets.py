"""Wrap detect-secrets. Online verification disabled -> fully offline."""
import json
import os
import re
import subprocess
import tempfile
from collections import defaultdict

from detect_secrets.core import scan as ds_scan
from detect_secrets.settings import default_settings

from . import Finding
from ..collectors.staged_diff import Unit

_BASELINE_PATH = ".secrets.baseline"

# Entropy-only plugins can't tell a real secret from a realistic-looking
# placeholder -> medium confidence, eligible for the LLM tie-break.
_MEDIUM_TYPES = {"Base64 High Entropy String", "Hex High Entropy String"}
# Informational only; not a credential by itself.
_LOW_TYPES = {"Public IP (ipv4)"}
_CRITICAL_TYPES = {"Private Key"}


def _severity_and_confidence(secret_type: str) -> tuple[str, float]:
    if secret_type in _CRITICAL_TYPES:
        return "critical", 0.95
    if secret_type in _MEDIUM_TYPES:
        return "medium", 0.55
    if secret_type in _LOW_TYPES:
        return "low", 0.3
    return "high", 0.9


def _slugify(secret_type: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", secret_type.lower()).strip("_")


def _load_baseline_hashes(path: str) -> dict[str, set[str]]:
    """Map of relative path -> set of already-reviewed secret hashes."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, set[str]] = defaultdict(set)
    for file_path, entries in data.get("results", {}).items():
        for entry in entries:
            hashed = entry.get("hashed_secret")
            if hashed:
                out[file_path].add(hashed)
    return out


def _staged_content(path: str) -> str | None:
    """The staged (index) version of a file, so unstaged edits are ignored."""
    result = subprocess.run(
        ["git", "show", f":{path}"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def scan(units: list[Unit], cfg) -> list[Finding]:
    baseline = _load_baseline_hashes(_BASELINE_PATH)

    by_path: dict[str, list[Unit]] = defaultdict(list)
    for unit in units:
        if unit.file_class == "generated":
            continue
        by_path[unit.path].append(unit)

    findings: list[Finding] = []
    with default_settings():
        for path, path_units in by_path.items():
            added_lines = {u.line_no: u for u in path_units}
            content = _staged_content(path)
            if content is None:
                continue

            suffix = os.path.splitext(path)[1] or ".txt"
            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=suffix, delete=False, encoding="utf-8",
            )
            try:
                tmp.write(content)
                tmp.close()
                known_hashes = baseline.get(path, set())
                for secret in ds_scan.scan_file(tmp.name):
                    if secret.line_number not in added_lines:
                        continue  # only flag lines actually being added
                    if secret.secret_hash in known_hashes:
                        continue  # already reviewed via .secrets.baseline
                    unit = added_lines[secret.line_number]
                    severity, confidence = _severity_and_confidence(secret.type)
                    findings.append(Finding(
                        rule_id=secret.type,
                        kind=_slugify(secret.type),
                        severity=severity,
                        confidence=confidence,
                        path=path,
                        line_no=secret.line_number,
                        file_class=unit.file_class,
                        line_text=unit.text,
                        context_snippet=unit.window,
                        matched_value=secret.secret_value or "",
                    ))
            finally:
                os.unlink(tmp.name)
    return findings
