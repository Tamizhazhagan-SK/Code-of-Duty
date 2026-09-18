"""Shared terminal-capability detection for every tiered renderer (logo, progress
bar, ...) so they all agree on what "this terminal can show more than plain
ASCII" means. CI and NO_COLOR opt out of image/Unicode rendering even on an
otherwise-capable tty.
"""
import os

from rich.console import Console


def is_kitty() -> bool:
    return bool(os.environ.get("KITTY_WINDOW_ID")) or \
        os.environ.get("TERM") == "xterm-kitty" or \
        os.environ.get("TERM_PROGRAM") == "WezTerm"


def is_iterm2() -> bool:
    return os.environ.get("TERM_PROGRAM") == "iTerm.app"


def decorations_allowed() -> bool:
    return not os.environ.get("CI") and not os.environ.get("NO_COLOR")


def supports_image(console: Console) -> bool:
    return console.is_terminal and decorations_allowed() and (is_kitty() or is_iterm2())


def supports_unicode(console: Console) -> bool:
    if not console.is_terminal or not decorations_allowed() or console.color_system is None:
        return False
    return "utf" in (console.encoding or "").lower()
