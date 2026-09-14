"""rich rendering + interaction, with a headless fallback. Raw values are never printed."""
import sys

from rich.console import Console, Group
from rich.panel import Panel
from rich.prompt import Prompt
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from ..audit import exceptions as audit_exceptions
from ..audit import log as audit_log
from ..audit.fingerprint import of_finding
from ..classifier.redact import language_of, redact
from ..policy.engine import Decision
from ..remediation import applier, proposer

console = Console(stderr=False, highlight=False)

_SEVERITY_STYLE = {
    "critical": "bold white on red",
    "high": "bold red",
    "medium": "yellow",
    "low": "dim",
}
_ACTION_STYLE = {"block": "bold red", "warn": "yellow", "allow": "green"}
_LEXER = {"python": "python", "javascript": "javascript", "typescript": "typescript",
          "go": "go", "java": "java", "yaml": "yaml", "json": "json", "terraform": "terraform",
          "dotenv": "ini", "ini": "ini", "toml": "toml", "shell": "bash",
          "dockerfile": "docker", "csharp": "csharp", "ruby": "ruby", "php": "php",
          "rust": "rust", "kotlin": "kotlin", "xml": "xml", "markdown": "markdown"}


def is_interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


# Every value detected in the current changeset, so a line that carries two findings
# never shows the other one in clear text.
_ALL_VALUES: dict[str, str] = {}


def _remember(decisions) -> None:
    for d in decisions:
        f = d.finding
        if f.matched_value:
            _ALL_VALUES[f.matched_value] = redact(f.matched_value, f.kind)


def _masked(text: str, finding) -> str:
    """Never render a raw secret/PII value; show a typed, length-hinted token."""
    if finding.matched_value:
        text = text.replace(finding.matched_value, redact(finding.matched_value, finding.kind))
    for value in sorted(_ALL_VALUES, key=len, reverse=True):
        text = text.replace(value, _ALL_VALUES[value])
    return text


def _where(finding) -> str:
    return f"{finding.path}:{finding.line_no}" if finding.line_no else f"{finding.path} (whole file)"


def _summary_table(decisions) -> Table:
    table = Table(title="Staged findings", title_style="bold", expand=False)
    table.add_column("Location", overflow="fold")
    table.add_column("Rule")
    table.add_column("Severity")
    table.add_column("Decided by")
    table.add_column("Action")
    for decision in decisions:
        f = decision.finding
        sev = _SEVERITY_STYLE.get(f.severity, "")
        act = _ACTION_STYLE.get(decision.action, "")
        by = "AI tie-break" if decision.model_verdict is not None else \
            ("policy (exception)" if "exception" in decision.reason else "deterministic")
        table.add_row(_where(f), f.rule_id, f"[{sev}]{f.severity}[/]", by,
                      f"[{act}]{decision.action.upper()}[/]")
    return table


def _finding_panel(decision) -> Panel:
    f = decision.finding
    style = _SEVERITY_STYLE.get(f.severity, "")
    parts: list = [Text.from_markup(f"[bold]{f.rule_id}[/] ({f.severity})")]
    if f.explanation:
        parts.append(Text(f.explanation))
    parts.append(Text(f"Decision: {decision.reason}", style="italic"))
    if f.line_text:
        parts += ["", Syntax(_masked(f.line_text, f), _LEXER.get(language_of(f.path), "text"),
                             theme="ansi_dark", line_numbers=True, start_line=f.line_no)]
    return Panel(Group(*parts),
                 title=f"[{_ACTION_STYLE.get(decision.action, '')}]{decision.action.upper()}[/] "
                       f"{_where(f)}",
                 border_style=style.split()[-1] if style else "white")


def _fix_hint(decision, cfg) -> str:
    p = proposer.propose(decision, "reference", cfg)
    if p.mode == "unstage":
        return p.note
    return f"suggested: {_masked(p.new_line or '', decision.finding).strip()}"


def headless_report(decisions, cfg=None) -> None:
    _remember(decisions)
    console.print(_summary_table(decisions))
    for decision in decisions:
        console.print(_finding_panel(decision))
        console.print(f"  [green]fix[/] {_fix_hint(decision, cfg)}")


def _preview(decision, proposal) -> Panel:
    f = decision.finding
    if proposal.mode == "unstage":
        return Panel(proposal.note, title="Proposed fix", border_style="green")
    old = _masked(f.line_text, f)
    body = Text()
    body.append(f"- {old}\n", style="red")
    body.append(f"+ {_masked(proposal.new_line or '', f)}", style="green")
    if proposal.note:
        body.append(f"\n\n{proposal.note}", style="dim")
    return Panel(body, title="Proposed fix (applied to the staged copy only)", border_style="green")


def _apply_unstage(finding, cfg, resolved_paths: set[str]) -> bool:
    for action in applier.unstage_and_ignore(finding.path):
        console.print(f"  [green]✓[/] {action}")
    resolved_paths.add(finding.path)
    audit_log.append({"fingerprint": of_finding(finding), "path": finding.path,
                      "action": "remediated", "method": "unstage_ignore"})
    return True


def _apply_fix(finding, cfg, mode: str) -> bool:
    proposal = proposer.propose(Decision("block", finding.severity, "", finding), mode, cfg)
    try:
        where = applier.apply(finding.path, finding.line_no, proposal.new_line or "",
                              finding.line_text)
    except applier.StaleIndexError as exc:
        console.print(f"[red]{exc}[/red]")
        return False
    audit_log.append({"fingerprint": of_finding(finding), "path": finding.path,
                      "action": "remediated",
                      "method": "vault_reference" if mode == "reference" else "placeholder"})
    console.print(f"[green]✓ Fix applied to the {where.replace('+', ' and ')} "
                  "and re-staged.[/green]")
    return True


def _record_exception(finding, cfg) -> bool:
    reason = Prompt.ask("Reason for this exception (recorded in the audit log)")
    if not reason.strip():
        console.print("[red]An exception needs a reason.[/red]")
        return False
    fingerprint = of_finding(finding)
    audit_exceptions.add(fingerprint, reason, cfg.exceptions_ttl_days)
    audit_log.append({"fingerprint": fingerprint, "path": finding.path,
                      "action": "exception", "reason": reason})
    console.print(f"[yellow]Exception recorded for {cfg.exceptions_ttl_days} days "
                  "(scoped to this exact line).[/yellow]")
    return True


def _offer_choices(decision, cfg) -> tuple[list[str], str]:
    """Print the preview(s) for this finding and return the menu."""
    finding = decision.finding
    if finding.line_no == 0:
        console.print(_preview(decision, proposer.propose(decision, "unstage", cfg)))
        return ["u", "e", "a"], "[U]nstage + gitignore  [E]xception  [A]bort"
    console.print(_preview(decision, proposer.propose(decision, "reference", cfg)))
    placeholder = proposer.propose(decision, "placeholder", cfg)
    console.print(f"  [dim]or [R]: {_masked(placeholder.new_line or '', finding).strip()}[/]")
    return (["v", "r", "e", "a"],
            "[V] env/vault reference  [R] safe placeholder  [E]xception  [A]bort")


def _interactive_resolve(decision, cfg, resolved_paths: set[str]) -> bool:
    """Returns True if this finding is resolved (fixed or excepted), False if aborted."""
    finding = decision.finding
    console.print(_finding_panel(decision))
    choices, label = _offer_choices(decision, cfg)
    choice = Prompt.ask(label, choices=choices, default="a")

    if choice == "u":
        return _apply_unstage(finding, cfg, resolved_paths)
    if choice in ("v", "r"):
        return _apply_fix(finding, cfg, "reference" if choice == "v" else "placeholder")
    if choice == "e":
        return _record_exception(finding, cfg)
    console.print("[red]Aborted. Fix manually and re-stage before committing.[/red]")
    return False


def banner() -> None:
    console.print(Panel.fit(
        "[bold cyan]ZeroTrace[/] · pre-commit secret & PII guardrail · local-first",
        border_style="cyan",
    ))


def present(decisions, cfg, interactive: bool = True) -> int:
    banner()
    if not interactive:
        headless_report(decisions, cfg)
        return 1

    _remember(decisions)
    console.print(_summary_table(decisions))
    resolved_paths: set[str] = set()
    touched: set[tuple[str, int]] = set()
    deferred = 0
    for decision in decisions:
        f = decision.finding
        if f.path in resolved_paths:
            continue  # the whole file was already unstaged
        if (f.path, f.line_no) in touched:
            deferred += 1  # line already rewritten; the re-scan re-checks it
            continue
        if not _interactive_resolve(decision, cfg, resolved_paths):
            return 1  # abort stops the whole commit; nothing further is applied
        touched.add((f.path, f.line_no))
    if deferred:
        console.print(f"[dim]Re-scanning {deferred} finding(s) on lines that were just rewritten…[/]")
    return 0
