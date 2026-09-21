"""The full-screen review app (`zerotrace review`), built with Textual.

Why this is NOT what the git hook runs: Textual takes over the whole screen and costs a
noticeable import on every start. A pre-commit hook must be fast, must work when git gives it
no terminal, and must not repaint a developer's scrollback. So the hook keeps the inline
rich output, and this richer experience is what `zerotrace review` opens when a terminal is
available. Both drive the same detectors, policy engine and remediation code.

Keys are accepted in either case: `v` and `V` do the same thing, because the menu shows the
capital letter.
"""
from dataclasses import dataclass

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button, DataTable, Footer, Header, Input, Label, Static,
)
from textual.widgets import Markdown as MarkdownView

from ..audit import exceptions as audit_exceptions
from ..audit import log as audit_log
from ..audit.fingerprint import of_finding
from ..classifier.redact import redact
from ..policy.engine import Decision
from ..remediation import applier, proposer
from .terminal import decided_by

_SEVERITY_COLOUR = {"critical": "bold white on red", "high": "bold red",
                    "medium": "yellow", "low": "dim"}
_ACTION_COLOUR = {"block": "bold red", "warn": "yellow", "allow": "green"}


def _clip(text: str, width: int) -> str:
    """Mark a truncation. A silently cut rule id reads as a different rule."""
    return text if len(text) <= width else text[:width - 1] + "\u2026"


def _short_where(finding) -> str:
    """basename:line. The directory is usually the same for every row and eats the column."""
    name = finding.path.rsplit("/", 1)[-1]
    return f"{name}:{finding.line_no}" if finding.line_no else f"{name} (file)"


def _verdict(decision) -> str:
    """BLOCK or WARN, coloured by severity: the two facts are read as one."""
    style = _SEVERITY_COLOUR.get(decision.finding.severity) or \
        _ACTION_COLOUR.get(decision.action, "")
    return f"[{style}]{decision.action.upper()}[/]"


@dataclass
class Row:
    """One finding plus what has happened to it in this session."""
    decision: Decision
    state: str = "open"          # open | fixed | excepted
    note: str = ""


class ReasonScreen(ModalScreen[str]):
    """An exception silences a security control, so it must carry a reason."""

    CSS = """
    ReasonScreen { align: center middle; }
    #box { width: 70; max-width: 90%; height: auto; border: round $warning; padding: 1 2;
           background: $surface; }
    #box Label { width: 100%; }
    #row { height: auto; margin-top: 1; }
    Button { margin-right: 1; }
    """
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(id="box"):
            yield Label("Why is this finding acceptable?")
            yield Label("[dim]Recorded in the audit log and expires; fingerprint only.[/]")
            yield Input(placeholder="e.g. vendor sample key, rotated 2026-09-01", id="reason")
            with Horizontal(id="row"):
                yield Button("Record exception", variant="warning", id="ok")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        self.query_one("#reason", Input).focus()

    @on(Button.Pressed, "#ok")
    @on(Input.Submitted, "#reason")
    def _accept(self) -> None:
        reason = self.query_one("#reason", Input).value.strip()
        if reason:
            self.dismiss(reason)

    @on(Button.Pressed, "#cancel")
    def action_cancel(self) -> None:
        self.dismiss("")


_HELP = """\
## Resolving a finding

| Key | What it does |
| --- | --- |
| `V` | Replace the value with an environment or vault reference, in this file's language |
| `R` | Replace it with a safe placeholder (for examples and fixtures) |
| `U` | Unstage the whole file and add it to `.gitignore` |
| `E` | Record a time-bound exception — a written reason is required |
| `F` | Apply the `V` fix to every remaining finding that has one |

## Moving around

| Key | What it does |
| --- | --- |
| `J` / `K`, arrows | Next / previous finding (the mouse works too) |
| `O` | Show only the findings that are still open |
| `A` or `Q` | Leave. Anything still open keeps the commit blocked |

Upper and lower case both work everywhere. Every fix is written to the staged copy
only: your unstaged edits are left alone.
"""


class HelpScreen(ModalScreen[None]):
    """The full key list. A toast is too small to hold it and disappears while you read."""

    CSS = """
    HelpScreen { align: center middle; }
    #help_box { width: 80%; max-width: 86; height: auto; max-height: 80%;
                border: round $accent; background: $surface; padding: 1 2; }
    """
    BINDINGS = [Binding("escape,question_mark,q", "dismiss_help", "Close")]

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="help_box"):
            yield MarkdownView(_HELP)

    def action_dismiss_help(self) -> None:
        self.dismiss(None)


class ConfirmScreen(ModalScreen[bool]):
    """Used for the batch fix: several files change at once, so it is worth a question."""

    CSS = """
    ConfirmScreen { align: center middle; }
    #confirm_box { width: 64; max-width: 90%; height: auto; border: round $accent;
                   padding: 1 2; background: $surface; }
    #confirm_row { height: auto; margin-top: 1; }
    /* Without an explicit width a Label sizes to its content and the question is cut off. */
    #confirm_box Label { width: 100%; }
    Button { margin-right: 1; }
    """
    BINDINGS = [Binding("escape,n", "refuse", "Cancel"), Binding("y", "accept", "Yes")]

    def __init__(self, question: str) -> None:
        super().__init__()
        self.question = question

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm_box"):
            yield Label(self.question)
            with Horizontal(id="confirm_row"):
                yield Button("Apply", variant="primary", id="yes")
                yield Button("Cancel", id="no")

    @on(Button.Pressed, "#yes")
    def action_accept(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#no")
    def action_refuse(self) -> None:
        self.dismiss(False)


class ReviewApp(App[int]):
    """Browse the staged findings and resolve them one at a time."""

    CSS = """
    #body { height: 1fr; }
    #list { width: 52%; border-right: solid $panel; }
    #detail { width: 48%; padding: 0 1; }
    DataTable { height: 1fr; }
    /* Not docked: the footer already docks to the bottom, and two docked widgets fight
       over the same row — the status line simply never appeared. */
    #status { height: 1; padding: 0 1; background: $panel; }

    /* Under 80 columns a 48% detail pane is four words wide, so the panes stack instead.
       Split IDE terminals and 80x24 SSH sessions land here. */
    #body.narrow { layout: vertical; }
    #body.narrow #list { width: 100%; height: 45%; border-right: none;
                         border-bottom: solid $panel; }
    #body.narrow #detail { width: 100%; height: 1fr; }
    """
    NARROW_AT = 80
    BINDINGS = [
        Binding("v,V", "fix_reference", "env/vault ref"),
        Binding("r,R", "fix_placeholder", "placeholder"),
        Binding("u,U", "unstage", "unstage file"),
        Binding("e,E", "exception", "exception"),
        Binding("f,F", "fix_all", "fix all"),
        Binding("o,O", "toggle_resolved", "only open"),
        Binding("a,A,q,escape", "abort", "abort"),
        Binding("j,down", "next_row", "next", show=False),
        Binding("k,up", "previous_row", "prev", show=False),
        Binding("question_mark", "help", "help"),
    ]

    def __init__(self, decisions: list, cfg) -> None:
        super().__init__()
        self.rows = [Row(decision) for decision in decisions]
        self.cfg = cfg
        # The rows the table is currently showing, in table order. Filtering means a table
        # index is not a self.rows index, so every lookup goes through this list.
        self.listed: list[Row] = list(self.rows)
        self.hide_resolved = False
        # What the two panes currently say. Kept as plain text so the app can be asserted
        # against without scraping widgets.
        self.detail_text = ""
        self.status_text = ""

    # --- layout -----------------------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal(id="body"):
            with Vertical(id="list"):
                yield DataTable(id="findings", cursor_type="row", zebra_stripes=True)
            with VerticalScroll(id="detail"):
                yield Static(id="detail_body")
        yield Static(id="status")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "ZeroTrace review"
        self.sub_title = f"{len(self.rows)} finding(s) holding this commit"
        table = self.query_one("#findings", DataTable)
        # Four columns, not six: the list pane is under half the window, and a clipped
        # severity is worse than no severity. The full path and the "decided by" line live
        # in the detail pane, where there is room for them.
        # Fixed widths: DataTable will happily grow past its pane and clip the last column,
        # and the last column is the verdict — the one thing that must always be readable.
        table.add_column(" ", width=1)
        table.add_column("Where", width=16)
        table.add_column("Rule", width=17)
        table.add_column("Verdict", width=7)
        self._refresh_table()
        table.focus()
        self._apply_layout()
        self._show_detail()
        self._update_status()

    # --- rendering ---------------------------------------------------------------------
    def _state_mark(self, row: Row) -> str:
        return {"open": "  ", "fixed": "[green]✓[/]", "excepted": "[yellow]≈[/]"}[row.state]

    def _refresh_table(self, keep: Row | None = None) -> None:
        """Redraw the list. `keep` is the row to leave the cursor on, if it is still shown."""
        table = self.query_one("#findings", DataTable)
        previous = table.cursor_row or 0
        table.clear()
        self.listed = [row for row in self.rows
                        if not self.hide_resolved or row.state == "open"]
        for row in self.listed:
            finding = row.decision.finding
            table.add_row(self._state_mark(row), _clip(_short_where(finding), 16),
                          _clip(finding.rule_id, 17), _verdict(row.decision))
        if not table.row_count:
            return
        target = self.listed.index(keep) if keep in self.listed else previous
        table.move_cursor(row=max(0, min(target, table.row_count - 1)))

    def _advance(self) -> None:
        """After a fix, land on the next finding that still needs a decision.

        Re-reading the list to find where you were is the tedious part of a long review, so
        the cursor does it. It only moves forward, never past the end.
        """
        current = self.query_one("#findings", DataTable).cursor_row or 0
        for index in range(current + 1, len(self.listed)):
            if self.listed[index].state == "open":
                self.query_one("#findings", DataTable).move_cursor(row=index)
                return
        for index, row in enumerate(self.listed):     # wrap: earlier ones may be open
            if row.state == "open":
                self.query_one("#findings", DataTable).move_cursor(row=index)
                return

    def _masked(self, text: str, finding) -> str:
        """Never show a raw value, not even in the pane the developer is reading."""
        for row in self.rows:
            other = row.decision.finding
            if other.matched_value:
                text = text.replace(other.matched_value, redact(other.matched_value, other.kind))
        return text

    def _current(self) -> Row | None:
        table = self.query_one("#findings", DataTable)
        index = table.cursor_row
        if index is None or not (0 <= index < len(self.listed)):
            return None
        return self.listed[index]

    def _show_detail(self) -> None:
        row = self._current()
        body = self.query_one("#detail_body", Static)
        if row is None:
            self.detail_text = "Nothing to review."
            body.update(self.detail_text)
            return
        finding = row.decision.finding
        lines = [
            f"[bold]{finding.rule_id}[/] "
            f"([{_SEVERITY_COLOUR.get(finding.severity, '')}]{finding.severity}[/])",
            f"[dim]{finding.path}"
            + (f":{finding.line_no}" if finding.line_no else " (whole file)")
            + f" · decided by {decided_by(row.decision)}[/]",
            "",
            finding.explanation or "",
            "",
            f"[dim]{row.decision.reason}[/]",
        ]
        if finding.line_text:
            lines += ["", "[bold]Staged line[/]",
                      f"  {self._masked(finding.line_text, finding)}"]

        reference = proposer.propose(row.decision, "reference", self.cfg)
        if reference.mode == "unstage":
            lines += ["", "[bold]Fix[/]", f"  [green]{reference.note}[/]", "",
                      "[dim]Press U to unstage and gitignore it.[/]"]
        elif reference.mode == "manual":
            lines += ["", "[bold]Fix by hand[/]", f"  [yellow]{reference.note}[/]", "",
                      "[dim]No safe automatic rewrite: E records an exception, A aborts.[/]"]
        else:
            placeholder = proposer.propose(row.decision, "placeholder", self.cfg)
            lines += [
                "", "[bold]Proposed fix[/]",
                f"  [red]- {self._masked(finding.line_text, finding)}[/]",
                f"  [green]+ {self._masked(reference.new_line or '', finding)}[/]",
                f"  [dim]{reference.note}[/]",
                "", f"[dim]or R:  {self._masked(placeholder.new_line or '', finding)}[/]",
            ]
        if row.note:
            lines += ["", f"[green]{row.note}[/]"]
        self.detail_text = "\n".join(lines)
        body.update(self.detail_text)

    def _update_status(self) -> None:
        open_rows = sum(1 for row in self.rows if row.state == "open")
        done = len(self.rows) - open_rows
        filtered = " · showing open only" if self.hide_resolved else ""
        self.status_text = (
            f"[green]{done} resolved[/] · [bold]{open_rows} open[/] of {len(self.rows)}"
            f"{filtered} · [dim]? for keys[/]"
            if open_rows else
            "[green]all findings resolved — press Q to finish the commit[/]")
        self.query_one("#status", Static).update(self.status_text)

    def on_resize(self) -> None:
        self._apply_layout()

    def _apply_layout(self) -> None:
        self.query_one("#body").set_class(self.size.width < self.NARROW_AT, "narrow")

    @on(DataTable.RowHighlighted)
    def _row_changed(self) -> None:
        self._show_detail()

    # --- actions -----------------------------------------------------------------------
    def _resolve(self, row: Row, state: str, note: str, method: str,
                 advance: bool = True) -> None:
        row.state, row.note = state, note
        audit_log.append({"fingerprint": of_finding(row.decision.finding),
                          "path": row.decision.finding.path,
                          "action": "remediated" if state == "fixed" else "exception",
                          "method": method})
        self._refresh_table(keep=row)
        if advance:
            self._advance()
        self._show_detail()
        self._update_status()
        if all(r.state != "open" for r in self.rows):
            self.notify("Every finding is resolved. Press Q to finish.", timeout=6)

    def _apply_to(self, row: Row, mode: str, quiet: bool = False) -> bool:
        """Rewrite one finding. Returns whether it was resolved."""
        finding = row.decision.finding
        proposal = proposer.propose(row.decision, mode, self.cfg)
        if proposal.mode in ("unstage", "manual"):
            if not quiet:
                self.notify("This finding has no automatic rewrite; use U or E.",
                            severity="warning")
            return False
        try:
            where = applier.apply(finding.path, finding.line_no, proposal.new_line or "",
                                  finding.line_text)
        except applier.StaleIndexError as exc:
            if not quiet:
                self.notify(str(exc), severity="error", timeout=8)
            return False
        self._resolve(row, "fixed", f"Applied to the {where.replace('+', ' and ')}.",
                      "vault_reference" if mode == "reference" else "placeholder",
                      advance=not quiet)
        return True

    def _apply(self, mode: str) -> None:
        row = self._current()
        if row is None or row.state != "open":
            return
        self._apply_to(row, mode)

    def action_fix_reference(self) -> None:
        self._apply("reference")

    def action_fix_placeholder(self) -> None:
        self._apply("placeholder")

    def action_unstage(self) -> None:
        row = self._current()
        if row is None or row.state != "open":
            return
        finding = row.decision.finding
        try:
            actions = applier.unstage_and_ignore(finding.path)
        except Exception as exc:                       # git refused: say so, change nothing
            self.notify(f"{exc}", severity="error", timeout=8)
            return
        for other in self.rows:                        # the whole file is out of the commit
            if other.decision.finding.path == finding.path and other.state == "open":
                other.state, other.note = "fixed", "; ".join(actions)
        self._resolve(row, "fixed", "; ".join(actions), "unstage_ignore")

    def action_exception(self) -> None:
        row = self._current()
        if row is None or row.state != "open":
            return

        def record(reason: str | None) -> None:
            if not reason:
                return
            audit_exceptions.add(of_finding(row.decision.finding), reason,
                                 self.cfg.exceptions_ttl_days)
            self._resolve(row, "excepted",
                          f"Exception for {self.cfg.exceptions_ttl_days} days: {reason}",
                          "exception")

        self.push_screen(ReasonScreen(), record)

    def action_fix_all(self) -> None:
        """Apply the env/vault rewrite to every open finding that has one.

        A long review is mostly the same decision repeated, but it still changes several
        files at once, so it asks first and reports exactly how many it could not do.
        """
        candidates = [row for row in self.rows if row.state == "open"
                      and proposer.propose(row.decision, "reference",
                                           self.cfg).mode not in ("unstage", "manual")]
        if not candidates:
            self.notify("Nothing here can be rewritten automatically.", severity="warning")
            return

        def go(confirmed: bool | None) -> None:
            if not confirmed:
                return
            fixed = sum(1 for row in candidates if self._apply_to(row, "reference", quiet=True))
            self._refresh_table()
            self._advance()
            self._show_detail()
            self._update_status()
            missed = len(candidates) - fixed
            self.notify(f"{fixed} rewritten"
                        + (f", {missed} could not be applied — review them individually."
                           if missed else "."),
                        severity="warning" if missed else "information", timeout=8)

        self.push_screen(
            ConfirmScreen(f"Rewrite {len(candidates)} finding(s) as environment or vault "
                          "references? The staged copy changes; your unstaged edits do not."),
            go)

    def action_toggle_resolved(self) -> None:
        """Hide what is already done. On a big changeset the open ones are what matter."""
        self.hide_resolved = not self.hide_resolved
        self._refresh_table(keep=self._current())
        self._show_detail()
        self._update_status()

    def action_next_row(self) -> None:
        self.query_one("#findings", DataTable).action_cursor_down()

    def action_previous_row(self) -> None:
        self.query_one("#findings", DataTable).action_cursor_up()

    def action_help(self) -> None:
        if not isinstance(self.screen, HelpScreen):
            self.push_screen(HelpScreen())

    def action_abort(self) -> None:
        """Exit 0 only when nothing is left open: the commit proceeds on a clean review."""
        self.exit(0 if all(row.state != "open" for row in self.rows) else 1)

    async def action_quit(self) -> None:
        """Textual binds ctrl+q to a plain exit(), which returns None and reads as success.

        ctrl+q is muscle memory, so it must mean exactly what A and Q mean here: leaving with
        findings open keeps the commit blocked.
        """
        self.action_abort()


def review(decisions: list, cfg) -> int:
    """Run the review app. Returns 0 if every finding was resolved, 1 otherwise."""
    return ReviewApp(decisions, cfg).run() or 0
