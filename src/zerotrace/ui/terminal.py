"""rich rendering + interaction, with a headless fallback."""
import sys

from rich.console import Console, Group
from rich.panel import Panel
from rich.prompt import Prompt
from rich.syntax import Syntax
from rich.table import Table

from ..audit import exceptions as audit_exceptions
from ..audit import log as audit_log
from ..audit.fingerprint import of_finding
from ..classifier.redact import redact
from ..remediation import applier, proposer

console = Console()

_SEVERITY_STYLE = {
    "critical": "bold white on red",
    "high": "bold red",
    "medium": "yellow",
    "low": "dim",
}
_LEXERS = {
    ".py": "python", ".yml": "yaml", ".yaml": "yaml", ".json": "json",
    ".ts": "typescript", ".js": "javascript", ".md": "markdown",
}


def is_interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _lexer_for(path: str) -> str:
    for ext, lexer in _LEXERS.items():
        if path.endswith(ext):
            return lexer
    return "ini" if ".env" in path else "text"


def _masked_line(decision) -> str:
    """Never render the raw secret/PII value; show a typed, length-hinted token."""
    finding = decision.finding
    line = finding.line_text or finding.context_snippet
    if not finding.matched_value:
        return line
    return line.replace(finding.matched_value, redact(finding.matched_value, finding.kind))


def _summary_table(decisions) -> Table:
    table = Table(title="Staged findings")
    table.add_column("File")
    table.add_column("Line", justify="right")
    table.add_column("Rule")
    table.add_column("Severity")
    table.add_column("Confidence", justify="right")
    table.add_column("Action")
    for decision in decisions:
        finding = decision.finding
        style = _SEVERITY_STYLE.get(finding.severity, "")
        table.add_row(
            finding.path, str(finding.line_no), finding.rule_id,
            f"[{style}]{finding.severity}[/{style}]", f"{finding.confidence:.2f}",
            f"[{style}]{decision.action.upper()}[/{style}]",
        )
    return table


def _finding_panel(decision) -> Panel:
    finding = decision.finding
    style = _SEVERITY_STYLE.get(finding.severity, "")
    body = Group(
        f"[bold]{finding.rule_id}[/] — {decision.reason}",
        "",
        Syntax(_masked_line(decision), _lexer_for(finding.path), theme="ansi_dark"),
    )
    return Panel(
        body,
        title=f"[{style}]{decision.action.upper()}[/{style}] {finding.path}:{finding.line_no}",
        border_style=style.split()[-1] if style else "white",
    )


def _headless_report(decisions) -> None:
    console.print(_summary_table(decisions))
    for decision in decisions:
        console.print(_finding_panel(decision))


def _interactive_resolve(decision, cfg) -> bool:
    """Returns True if this finding is resolved (fixed or excepted), False if aborted."""
    finding = decision.finding
    console.print(_finding_panel(decision))

    preview = proposer.propose(decision)
    console.print(Panel(preview, title="Proposed replacement", border_style="green"))

    choice = Prompt.ask(
        "[R]eplace  [V]ault/env reference  [E]xception  [A]bort",
        choices=["r", "v", "e", "a"], default="a",
    )

    if choice in ("r", "v"):
        applier.apply(finding.path, finding.line_no, preview)
        audit_log.append({
            "fingerprint": of_finding(finding), "path": finding.path,
            "action": "remediated", "method": "replace" if choice == "r" else "vault_reference",
        })
        console.print("[green]Replacement applied and restaged.[/green]")
        return True

    if choice == "e":
        reason = Prompt.ask("Reason for this exception")
        fingerprint = of_finding(finding)
        audit_exceptions.add(fingerprint, reason, cfg.exceptions_ttl_days)
        audit_log.append({
            "fingerprint": fingerprint, "path": finding.path,
            "action": "exception", "reason": reason,
        })
        console.print(f"[yellow]Exception recorded for {cfg.exceptions_ttl_days} days.[/yellow]")
        return True

    console.print("[red]Aborted. Fix manually and re-stage before committing.[/red]")
    return False


def present(decisions, cfg, interactive: bool = True) -> int:
    console.print(Panel.fit(
        "[bold cyan]ZeroTrace[/] — pre-commit secret & PII guardrail", border_style="cyan",
    ))

    if not interactive:
        _headless_report(decisions)
        return 1

    console.print(_summary_table(decisions))
    all_resolved = True
    for decision in decisions:
        if not _interactive_resolve(decision, cfg):
            all_resolved = False
            break  # abort stops the whole commit; nothing further is auto-applied

    return 0 if all_resolved else 1
