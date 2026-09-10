"""CLI / hook entrypoint. `zerotrace run` is what pre-commit invokes."""
import sys

from .audit import log as audit_log
from .audit.fingerprint import of_finding
from .config import load_config
from .collectors.staged_diff import collect_staged
from .detectors import secrets as secret_det, pii as pii_det
from .policy.engine import decide
from .ui.terminal import present, is_interactive


def _record_decision(decision) -> None:
    finding = decision.finding
    audit_log.append({
        "fingerprint": of_finding(finding),
        "path": finding.path,
        "line_no": finding.line_no,
        "rule_id": finding.rule_id,
        "severity": finding.severity,
        "action": decision.action,
        "reason": decision.reason,
    })


def _decide_staged(cfg) -> list:
    units = collect_staged()                       # only added lines
    findings = secret_det.scan(units, cfg) + pii_det.scan(units, cfg)
    decisions = [decide(f, cfg) for f in findings]
    for decision in decisions:
        _record_decision(decision)
    return decisions


def run(argv=None) -> int:
    cfg = load_config()
    decisions = _decide_staged(cfg)

    blocking = [d for d in decisions if d.action in ("block", "warn")]
    if not blocking:
        return 0                                    # commit proceeds

    if is_interactive():
        return present(blocking, cfg)               # explain -> preview -> apply
    # Headless (IDE/GUI): never guess approval. Block with instructions.
    present(blocking, cfg, interactive=False)
    print("\nRun `zerotrace review` in a terminal to remediate.", file=sys.stderr)
    return 1


def review(argv=None) -> int:
    """Re-run interactively, e.g. after a headless block. Meant for a real terminal."""
    cfg = load_config()
    decisions = _decide_staged(cfg)
    blocking = [d for d in decisions if d.action in ("block", "warn")]
    if not blocking:
        print("zerotrace: no blocking findings in the staged diff.")
        return 0
    return present(blocking, cfg, interactive=True)


def main() -> None:
    argv = sys.argv[1:]
    command, rest = (argv[0], argv[1:]) if argv and argv[0] in ("run", "review") else ("run", argv)
    if command == "review":
        raise SystemExit(review(rest))
    raise SystemExit(run(rest))
