"""Detect -> post-process -> (optional, batched) classify -> decide. One path for every mode."""
import hashlib
import json
import os
from collections import defaultdict
from dataclasses import replace

from .collectors.staged_diff import Changeset
from .detectors import SEVERITY_ORDER, Finding, downgrade
from .detectors import code_assign, pii as pii_det, rulepack, secrets as secret_det
from .detectors import sensitive_files
from .detectors.filters import (
    is_hash_context, is_lockfile, is_placeholder, is_uuid, looks_like_prose,
)
from .policy.engine import Decision, decide

_SOURCE_PRIORITY = {"sensitive_files": 5, "rulepack": 4, "code_assign": 3,
                    "detect_secrets": 2, "pii": 1}
_ENTROPY_ONLY = {"Base64 High Entropy String", "Hex High Entropy String"}


def detect(changeset: Changeset, cfg) -> list[Finding]:
    findings: list[Finding] = []
    findings += sensitive_files.scan(changeset, cfg)
    findings += rulepack.scan(changeset.units, cfg)
    findings += code_assign.scan(changeset.units, cfg)
    findings += secret_det.scan(changeset, cfg)
    findings += pii_det.scan(changeset.units, cfg)
    return postprocess(findings, cfg)


def _load_baseline(root: str) -> dict[str, set[str]]:
    """detect-secrets baseline: path -> set of sha1(secret). Honoured by every detector."""
    path = os.path.join(root, ".secrets.baseline")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, set[str]] = defaultdict(set)
    for file_path, entries in (data.get("results") or {}).items():
        for entry in entries:
            if entry.get("hashed_secret"):
                out[file_path].add(entry["hashed_secret"])
    return out


def postprocess(findings: list[Finding], cfg) -> list[Finding]:
    baseline = _load_baseline(getattr(cfg, "repo_root", "") or os.getcwd())
    kept: list[Finding] = []
    for f in findings:
        value = f.matched_value
        if f.severity != "critical" and f.source != "sensitive_files" and value:
            if is_placeholder(value) or is_uuid(value):
                continue
            if f.source in ("detect_secrets", "code_assign") and looks_like_prose(value):
                continue  # "A password is required." is a message, not a password
            if f.rule_id in _ENTROPY_ONLY and (is_lockfile(f.path) or is_hash_context(f.line_text)):
                continue
        if value and hashlib.sha1(value.encode("utf-8")).hexdigest() in baseline.get(f.path, ()):
            continue  # reviewed and accepted via .secrets.baseline
        # Test/docs context lowers heuristic findings one level; provider formats stay.
        if f.file_class in ("test", "docs") and f.source in ("code_assign", "detect_secrets") \
                and f.severity != "critical":
            f = replace(f, severity=downgrade(f.severity))
        kept.append(f)
    return dedupe(kept)


def dedupe(findings: list[Finding]) -> list[Finding]:
    """One secret finding per (path, line); PII findings per (path, line, value)."""
    best: dict[tuple, Finding] = {}
    for f in findings:
        key: tuple = (f.path, f.line_no, "pii", f.matched_value) if f.source == "pii" \
            else (f.path, f.line_no, "secret")
        cur = best.get(key)
        rank = (SEVERITY_ORDER.get(f.severity, 0), _SOURCE_PRIORITY.get(f.source, 0))
        if cur is None or rank > (SEVERITY_ORDER.get(cur.severity, 0),
                                  _SOURCE_PRIORITY.get(cur.source, 0)):
            best[key] = f
    # File-level findings first (they can resolve the whole file), then by path/line.
    return sorted(best.values(), key=lambda f: (f.line_no != 0, f.path, f.line_no))


def decide_all(findings: list[Finding], cfg, use_model: bool = True) -> list[Decision]:
    verdicts: dict = {}
    if use_model and cfg.model_enabled:
        from .classifier import batch
        verdicts = batch.classify_medium(findings, cfg)
    decisions = []
    for i, f in enumerate(findings):
        if i in verdicts:
            decisions.append(decide(f, cfg, verdict=verdicts[i]))
        elif not use_model and f.severity in cfg.warn_severity:
            decisions.append(decide(f, replace(cfg, model_enabled=False)))
        else:
            decisions.append(decide(f, cfg))
    return decisions


def scan(changeset: Changeset, cfg, use_model: bool = True) -> list[Decision]:
    return decide_all(detect(changeset, cfg), cfg, use_model=use_model)
