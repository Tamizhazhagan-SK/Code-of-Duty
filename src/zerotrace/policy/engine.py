"""The ONLY place that decides block/warn/allow. Pure + deterministic."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Decision:
    action: str          # block | warn | allow
    severity: str
    reason: str
    finding: object


def decide(finding, cfg) -> "Decision":
    severity = finding.severity

    from ..audit import exceptions as audit_exceptions
    from ..audit.fingerprint import of_finding
    if audit_exceptions.is_active(of_finding(finding)):
        return Decision(
            "allow", severity,
            f"{finding.rule_id} is covered by a previously approved, time-bound exception.",
            finding,
        )

    # HIGH/CRITICAL secret -> block. The model is never consulted here, so it
    # can never unblock a real leak (docs/ADR/0002).
    if severity in cfg.block_severity:
        return Decision(
            "block", severity,
            f"{finding.rule_id} matched with high confidence in {finding.path}:{finding.line_no}.",
            finding,
        )

    # MEDIUM/ambiguous -> optional local LLM tie-break; anything uncertain warns.
    if severity in cfg.warn_severity:
        if cfg.model_enabled:
            try:
                # Lazy import: never load the model unless a MEDIUM finding exists.
                from ..classifier import llm
                verdict = llm.classify(
                    finding.matched_value, finding.kind, finding.context_snippet, cfg,
                )
            except Exception:
                verdict = None  # any classifier error fails closed to WARN

            if verdict is not None and verdict.classification == "TEST_FIXTURE_OR_PLACEHOLDER" \
                    and verdict.confidence >= 0.6:
                return Decision(
                    "allow", severity,
                    f"Local model classified as a placeholder/test fixture: {verdict.reason}",
                    finding,
                )
            if verdict is not None:
                return Decision(
                    "warn", severity,
                    f"{finding.rule_id}: local model says {verdict.classification} "
                    f"({verdict.reason})",
                    finding,
                )
        return Decision(
            "warn", severity,
            f"{finding.rule_id} is ambiguous and could not be auto-classified; manual review required.",
            finding,
        )

    # LOW confidence -> allow, but recorded as an auditable exception.
    return Decision(
        "allow", severity,
        f"{finding.rule_id} looks like a placeholder/public example (low confidence).",
        finding,
    )
