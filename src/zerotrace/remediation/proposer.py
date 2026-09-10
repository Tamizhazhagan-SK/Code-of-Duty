"""Build a human-readable fix PREVIEW. Never edits files here."""
import re

_ASSIGNMENT_RE = re.compile(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*)\s*[:=]\s*(.*)$")
_SYNTHETIC_EMAIL = "user@example.test"
_SYNTHETIC_PHONE = "+1-555-0100"


def propose(decision) -> str:
    """Return the suggested replacement LINE (env-ref | synthetic PII | placeholder)."""
    finding = decision.finding
    line = finding.line_text or ""
    value = finding.matched_value

    if finding.kind in ("pii_email", "pii_email_internal"):
        replacement = _SYNTHETIC_EMAIL if finding.file_class == "test" else "${CUSTOMER_EMAIL}"
        return line.replace(value, replacement) if value else line

    if finding.kind == "pii_phone":
        return line.replace(value, _SYNTHETIC_PHONE) if value else line

    if finding.kind == "qxid_internal_id":
        return line.replace(value, "QX_PLACEHOLDER") if value else line

    # Secret-shaped finding -> environment-variable reference.
    match = _ASSIGNMENT_RE.match(line)
    if match and match.group(3).strip() == value.strip():
        indent, key, _ = match.groups()
        var_name = key.upper()
        return f"{indent}{var_name}=${{{var_name}}}"

    var_name = finding.kind.upper()
    return line.replace(value, f"${{{var_name}}}") if value else line
