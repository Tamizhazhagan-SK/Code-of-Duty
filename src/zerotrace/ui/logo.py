"""Logo rendering with graceful terminal-capability fallback.

Three tiers, richest-supported-first:
  1. png   -- inline image via the Kitty graphics protocol or iTerm2's protocol
  2. ansi  -- truecolor Unicode half-block art (any modern UTF-8 + color TTY)
  3. ascii -- plain text; safe for CI logs, redirected output, dumb terminals

Auto-detected, or forced with ZEROTRACE_LOGO=png|ansi|ascii|off. CI and NO_COLOR
disable the png/ansi tiers even if the terminal would otherwise qualify.

Runtime stays stdlib + rich (no image library import here, ever -- this runs on
every commit). Regenerate the png/ansi/ascii assets offline from a source image
with scripts/render_logo_assets.py, which needs Pillow (a dev-only extra).
"""
import base64
import os
from importlib import resources

from rich.console import Console

from . import capability

_PACKAGE = "zerotrace.ui.assets"
_ENV_VAR = "ZEROTRACE_LOGO"
_CHUNK = 4096  # bytes of base64 per Kitty graphics-protocol chunk


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


def render(console: Console) -> str | None:
    """The richest logo rendering this terminal can show, or None to print nothing."""
    forced = _forced_mode()
    if forced == "off":
        return None

    if forced == "png" or (forced is None and capability.supports_image(console)):
        png = _read_bytes("logo.png")
        if png is not None:
            return _kitty_escape(png) if capability.is_kitty() else _iterm2_escape(png)

    if forced == "ansi" or (forced is None and capability.supports_unicode(console)):
        art = _read_text("logo.ans")
        if art is not None:
            return art

    return _read_text("logo.txt")
