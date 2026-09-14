"""The ONLY place that decides block/warn/allow. Pure + deterministic given its inputs.

Asymmetric trust in the model (docs/ADR/0002):
  * HIGH/CRITICAL never reach the model, so the model can't unblock a real leak.
  * For MEDIUM, the model may lower friction (placeholder -> allow) or raise it
    (REAL_SECRET -> block). Any model failure leaves the finding at WARN.
"""
from dataclasses import dataclass

_NOT_PROVIDED = object()


@dataclass(frozen=True)
class Decision:
    action: str          # block | warn | allow
    severity: str
    reason: str
    finding: object
    model_verdict: object = None


def decide(finding, cfg, verdict=_NOT_PROVIDED) -> "Decision":
    severity = finding.severity
    where = f"{finding.path}:{finding.line_no}" if finding.line_no else finding.path

    from ..audit import exceptions as audit_exceptions
    from ..audit.fingerprint import of_finding
    if audit_exceptions.is_active(of_finding(finding)):
        return Decision(
            "allow", severity,
            f"{finding.rule_id} is covered by a previously approved, time-bound exception.",
            finding,
        )

    # HIGH/CRITICAL -> block. The model is never consulted here.
    if severity in cfg.block_severity:
        return Decision(
            "block", severity,
            f"{finding.rule_id} matched with high confidence in {where}.",
            finding,
        )

    # MEDIUM/ambiguous -> optional local-model tie-break; anything uncertain warns.
    if severity in cfg.warn_severity:
        if cfg.model_enabled:
            if verdict is _NOT_PROVIDED:
                try:
                    # Lazy import: never touch the model unless a MEDIUM finding exists.
                    from ..classifier import llm
                    verdict = llm.classify(finding, cfg)
                except Exception:
                    verdict = None  # any classifier error fails closed to WARN

            if verdict is not None:
                cls = getattr(verdict, "classification", None)
                conf = float(getattr(verdict, "confidence", 0.0))
                why = getattr(verdict, "reason", "")
                if cls == "TEST_FIXTURE_OR_PLACEHOLDER" and conf >= cfg.model_allow_threshold:
                    return Decision(
                        "allow", severity,
                        f"AI tie-break: placeholder/test fixture ({conf:.2f}): {why}",
                        finding, verdict,
                    )
                if cls == "REAL_SECRET" and cfg.model_can_escalate \
                        and conf >= cfg.model_escalate_threshold:
                    return Decision(
                        "block", severity,
                        f"AI tie-break escalated to BLOCK: likely real secret ({conf:.2f}): {why}",
                        finding, verdict,
                    )
                return Decision(
                    "warn", severity,
                    f"{finding.rule_id}: AI tie-break says {cls} ({conf:.2f}): {why}",
                    finding, verdict,
                )
        return Decision(
            "warn", severity,
            f"{finding.rule_id} is ambiguous and could not be auto-classified; manual review required.",
            finding,
        )

    # LOW confidence -> allow, but recorded in the audit log.
    return Decision(
        "allow", severity,
        f"{finding.rule_id} looks like a placeholder/public example (low confidence).",
        finding,
    )
