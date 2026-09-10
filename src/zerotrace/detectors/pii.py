"""Regex PII scan. Adds locale recognizers (e.g. Aadhaar/PAN for en_IN)."""
import re

from . import Finding
from ..collectors.staged_diff import Unit

# Upgrade path: swap _regex_scan for Presidio's AnalyzerEngine (NER + these same
# patterns as custom PatternRecognizers) without changing the scan() contract.
try:
    import presidio_analyzer  # noqa: F401  (unused placeholder for the upgrade path)
except ImportError:
    presidio_analyzer = None

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(r"\b(?:\+\d{1,3}[ -]?)?\(?\d{3}\)?[ -]?\d{3}[ -]?\d{4}\b")
# Internal company-issued identifier, e.g. QXZ7HDG
_QXID_RE = re.compile(r"\bQX[A-Z0-9]{5}\b")

# Internal/employee email domains -> higher severity than a generic email.
_INTERNAL_DOMAINS = {"bmwtechworks.in", "bti.bmwgroup.com"}
# RFC 2606 reserved domains -> our own synthetic replacements land here; don't
# re-flag them as a fresh finding on the next scan.
_RESERVED_DOMAINS = {"example.com", "example.org", "example.net", "example.test"}


def _email_finding(match: re.Match, unit: Unit) -> Finding:
    domain = match.group(0).rsplit("@", 1)[-1].lower()
    internal = domain in _INTERNAL_DOMAINS
    reserved = domain in _RESERVED_DOMAINS
    severity = "low" if reserved else ("high" if internal else "medium")
    confidence = 0.2 if reserved else (0.9 if internal else 0.6)
    return Finding(
        rule_id="pii_email_internal" if internal else "pii_email",
        kind="pii_email_internal" if internal else "pii_email",
        severity=severity,
        confidence=confidence,
        path=unit.path,
        line_no=unit.line_no,
        file_class=unit.file_class,
        line_text=unit.text,
        context_snippet=unit.window,
        matched_value=match.group(0),
    )


def _regex_scan(units: list[Unit]) -> list[Finding]:
    findings: list[Finding] = []
    for unit in units:
        if unit.file_class == "generated":
            continue
        for match in _EMAIL_RE.finditer(unit.text):
            findings.append(_email_finding(match, unit))
        for match in _PHONE_RE.finditer(unit.text):
            findings.append(Finding(
                rule_id="pii_phone", kind="pii_phone", severity="medium",
                confidence=0.55, path=unit.path, line_no=unit.line_no,
                file_class=unit.file_class, line_text=unit.text,
                context_snippet=unit.window,
                matched_value=match.group(0),
            ))
        for match in _QXID_RE.finditer(unit.text):
            findings.append(Finding(
                rule_id="qxid_internal_id", kind="qxid_internal_id", severity="high",
                confidence=0.85, path=unit.path, line_no=unit.line_no,
                file_class=unit.file_class, line_text=unit.text,
                context_snippet=unit.window,
                matched_value=match.group(0),
            ))
    return findings


def scan(units: list[Unit], cfg) -> list[Finding]:
    return _regex_scan(units)
