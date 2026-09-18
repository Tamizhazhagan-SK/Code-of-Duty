"""Logo rendering: the mark on the left, the ZEROTRACE wordmark to its right.

Tiers, richest-supported-first:
  1. png     inline image via the Kitty or iTerm2 graphics protocol
  2. unicode shaded mark (`mark*.uni.txt`, a " ░▒▓█" ramp) + wordmark, drawn in white
  3. ascii   the same composition from `mark*.ascii.txt`; safe on cp437/cp1252 consoles
  4. text    just the wordmark lines, when the terminal is too narrow for any mark

Auto-detected, or forced with ZEROTRACE_LOGO=png|unicode|ascii|text|off. CI and NO_COLOR
drop to the ascii tier, and a redirected/non-tty destination never gets image escapes.

Assets are generated offline by scripts/render_logo_assets.py (needs Pillow); nothing
here imports an image library, because this runs on every commit.
"""
import base64
import os
from importlib import resources

from rich.console import Console

from . import capability

_PACKAGE = "zerotrace.ui.assets"
_ENV_VAR = "ZEROTRACE_LOGO"
_CHUNK = 4096            # bytes of base64 per Kitty graphics-protocol chunk
_GUTTER = "   "
_WHITE, _RESET = "\033[1;97m", "\033[0m"

_WORDMARK = "ZEROTRACE"
_TAGLINE = ("secret & PII guardrail", "commits · AI agents · local-first",
            "no trace. no leaks. stays safe.")

# 5-row block letters, only the glyphs ZEROTRACE needs.
_FONT = {
    "Z": ["█████", "   ██", "  ██ ", " ██  ", "█████"],
    "E": ["█████", "██   ", "████ ", "██   ", "█████"],
    "R": ["████ ", "██ ██", "████ ", "██ ██", "██ ██"],
    "O": ["█████", "██ ██", "██ ██", "██ ██", "█████"],
    "T": ["█████", "  ██ ", "  ██ ", "  ██ ", "  ██ "],
    "A": [" ███ ", "██ ██", "█████", "██ ██", "██ ██"],
    "C": ["█████", "██   ", "██   ", "██   ", "█████"],
}


def _forced_mode() -> str | None:
    return os.environ.get(_ENV_VAR, "").strip().lower() or None


def _read_bytes(name: str) -> bytes | None:
    try:
        return (resources.files(_PACKAGE) / name).read_bytes()
    except (FileNotFoundError, OSError):
        return None


def _read_text(name: str) -> str | None:
    data = _read_bytes(name)
    # Normalize CRLF -> LF: a Windows checkout (core.autocrlf) must not leak stray
    # \r into an escape/art payload written straight to the terminal.
    return data.decode("utf-8").replace("\r\n", "\n") if data is not None else None


def _kitty_escape(png: bytes) -> str:
    data = base64.b64encode(png).decode("ascii")
    chunks = [data[i:i + _CHUNK] for i in range(0, len(data), _CHUNK)] or [""]
    parts = []
    for i, chunk in enumerate(chunks):
        more = 0 if i == len(chunks) - 1 else 1
        control = f"a=T,f=100,m={more}" if i == 0 else f"m={more}"
        parts.append(f"\033_G{control};{chunk}\033\\")
    return "".join(parts)


def _iterm2_escape(png: bytes) -> str:
    data = base64.b64encode(png).decode("ascii")
    return f"\033]1337;File=inline=1;width=40;preserveAspectRatio=1;size={len(png)}:{data}\a"


def _block_wordmark() -> list[str]:
    return ["  ".join(_FONT[ch][row] for ch in _WORDMARK) for row in range(5)]


def _ascii_safe(text: str) -> str:
    """cp437/cp1252 consoles cannot print "·"; never send them a character they lack."""
    return text.replace("·", "-").encode("ascii", "replace").decode("ascii")


def _text_lines(width: int, ascii_only: bool = False) -> list[str]:
    tagline = [_ascii_safe(line) if ascii_only else line for line in _TAGLINE]
    return [_WORDMARK, "", *[line for line in tagline if len(line) <= width]]


def _mark_lines(name: str) -> list[str]:
    art = _read_text(name)
    if art is None:
        return []
    lines = [line.rstrip("\n") for line in art.split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def _compose(mark: list[str], right: list[str]) -> list[str]:
    """Mark on the left, right-hand block vertically centred against it."""
    if not mark:
        return right
    mark_width = max((len(line) for line in mark), default=0)
    height = max(len(mark), len(right))
    top_mark = (height - len(mark)) // 2
    top_right = (height - len(right)) // 2

    out = []
    for i in range(height):
        left = mark[i - top_mark] if top_mark <= i < top_mark + len(mark) else ""
        text = right[i - top_right] if top_right <= i < top_right + len(right) else ""
        out.append((left.ljust(mark_width) + _GUTTER + text).rstrip())
    return out


def _paint(lines: list[str], console: Console) -> str:
    body = "\n".join(lines)
    if console.color_system is None or not capability.decorations_allowed():
        return body + "\n"
    return "\n".join(f"{_WHITE}{line}{_RESET}" for line in lines) + "\n"


def _composition(console: Console, unicode_tier: bool) -> list[str]:
    """Widest layout the terminal can take: big mark + block wordmark, down to text only."""
    width = console.width or 80
    suffix = "uni" if unicode_tier else "ascii"
    big = _mark_lines(f"mark.{suffix}.txt")
    small = _mark_lines(f"mark.small.{suffix}.txt")
    big_width = max((len(line) for line in big), default=0)
    small_width = max((len(line) for line in small), default=0)
    block = _block_wordmark()
    block_width = max(len(line) for line in block)

    ascii_only = not unicode_tier
    if big and unicode_tier and width >= big_width + len(_GUTTER) + block_width:
        return _compose(big, block + ["", _TAGLINE[-1]])
    if big and width >= big_width + len(_GUTTER) + 24:
        return _compose(big, _text_lines(width - big_width - len(_GUTTER), ascii_only))
    if small and width >= small_width + len(_GUTTER) + 24:
        return _compose(small, _text_lines(width - small_width - len(_GUTTER), ascii_only))
    if small and width >= small_width:
        return small + ["", *_text_lines(width, ascii_only)]
    return _text_lines(width, ascii_only)


def render(console: Console) -> str | None:
    """The richest logo rendering this terminal can show, or None to print nothing."""
    forced = _forced_mode()
    if forced == "off":
        return None

    if forced == "png" or (forced is None and capability.supports_image(console)):
        png = _read_bytes("logo.png")
        if png is not None:
            return _kitty_escape(png) if capability.is_kitty() else _iterm2_escape(png)

    if forced == "text":
        return _paint(_text_lines(console.width or 80, not capability.supports_unicode(console)),
                      console)

    unicode_tier = forced == "unicode" or (forced is None and capability.supports_unicode(console))
    return _paint(_composition(console, unicode_tier), console)
