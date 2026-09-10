"""Wrap detect-secrets. Online verification disabled -> fully offline."""
from ..collectors.staged_diff import Unit

def scan(units: list[Unit], cfg) -> list:
    # Use detect_secrets.SecretsCollection over staged content, compare to the
    # hashed .secrets.baseline, emit Finding(rule_id, kind, severity, confidence).
    return []
