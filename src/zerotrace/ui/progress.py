"""A tiered ASCII/CP437-block progress bar for long-running CLI steps (install).

Three tiers, richest-supported-first (same capability probe as ui/logo.py):
  1. shaded -- a full/dark/medium/light block gradient (the classic DOS/CP437
     "installer" look), framed top/bottom by upper/lower half-block rules
  2. ascii  -- plain #/- characters redrawn in place; any real tty that isn't
     Unicode-capable (legacy console, stripped locale, NO_COLOR)
  3. plain  -- discrete "zerotrace: [n/total] label" lines, no \\r at all; a
     redirected/CI/non-tty destination, where in-place redraw would just
     corrupt a log file
"""
import sys
from typing import IO

from rich.console import Console

from . import capability

_WIDTH = 24
_LABEL_WIDTH = 42

_FULL = "\u2588"         # (CP437 219) full block
_DARK = "\u2593"         # (CP437 178) dark shade
_MED = "\u2592"          # (CP437 177) medium shade
_LIGHT = "\u2591"        # (CP437 176) light shade
_TOP_RULE = "\u2580"     # (CP437 223) upper half block
_BOTTOM_RULE = "\u2584"  # (CP437 220) lower half block


class Bar:
    """Call .step(label) once per completed unit of work, then .finish()."""

    def __init__(self, total: int, file: IO[str] | None = None, console: Console | None = None):
        self.total = max(total, 1)
        self.done = 0
        self.file = file or sys.stdout
        self.tty = self.file.isatty()
        self.shaded = self.tty and capability.supports_unicode(console or Console(file=self.file))
        self._framed = False

    def _shaded_bar(self) -> str:
        exact = self.done * _WIDTH / self.total
        full_cells = int(exact)
        cells = [_FULL] * full_cells
        if full_cells < _WIDTH:
            frac = exact - full_cells
            cells.append(_FULL if frac >= 0.75 else _DARK if frac >= 0.5 else
                        _MED if frac >= 0.25 else _LIGHT)
            cells += [_LIGHT] * (_WIDTH - len(cells))
        return "".join(cells)

    def _ascii_bar(self) -> str:
        filled = self.done * _WIDTH // self.total
        return "#" * filled + "-" * (_WIDTH - filled)

    def step(self, label: str) -> None:
        self.done = min(self.done + 1, self.total)
        if not self.tty:
            self.file.write(f"zerotrace: [{self.done}/{self.total}] {label}\n")
            self.file.flush()
            return
        if self.shaded and not self._framed:
            self.file.write(_TOP_RULE * (_WIDTH + 2) + "\n")
            self._framed = True
        bar = self._shaded_bar() if self.shaded else self._ascii_bar()
        pct = self.done * 100 // self.total
        text = f"[{bar}] {pct:3d}%  {label[:_LABEL_WIDTH].ljust(_LABEL_WIDTH)}"
        self.file.write("\r" + text)
        self.file.flush()

    def finish(self) -> None:
        if not self.tty or not self.done:
            return
        self.file.write("\n")
        if self.shaded:
            self.file.write(_BOTTOM_RULE * (_WIDTH + 2) + "\n")
        self.file.flush()
