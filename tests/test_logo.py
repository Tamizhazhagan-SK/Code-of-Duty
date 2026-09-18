"""Terminal-capability fallback for the logo: png -> ansi -> ascii, plus overrides."""
import base64
import io

import pytest
from rich.console import Console

from zerotrace.ui import logo

_ENV_KEYS = ("ZEROTRACE_LOGO", "KITTY_WINDOW_ID", "TERM", "TERM_PROGRAM", "CI", "NO_COLOR")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    # The real CI (this suite's own pipeline) sets CI=true, which would otherwise
    # leak into these tests and force every "auto mode" case into the ascii tier.
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _console(*, terminal: bool, color: str | None = "truecolor") -> Console:
    return Console(file=io.StringIO(), force_terminal=terminal, color_system=color)


def _stub_assets(monkeypatch, **available: bytes | str) -> None:
    def fake_read_bytes(name: str) -> bytes | None:
        value = available.get(name)
        if value is None:
            return None
        return value if isinstance(value, bytes) else value.encode("utf-8")
    monkeypatch.setattr(logo, "_read_bytes", fake_read_bytes)


def test_forced_off_returns_none(monkeypatch):
    monkeypatch.setenv("ZEROTRACE_LOGO", "off")
    _stub_assets(monkeypatch, **{"logo.txt": "ascii-art"})
    assert logo.render(_console(terminal=True)) is None


def test_forced_ascii_ignores_terminal_capability(monkeypatch):
    monkeypatch.setenv("ZEROTRACE_LOGO", "ascii")
    monkeypatch.setenv("KITTY_WINDOW_ID", "1")
    _stub_assets(monkeypatch, **{"logo.png": b"fake", "logo.ans": "ansi-art", "logo.txt": "ascii-art"})
    assert logo.render(_console(terminal=True)) == "ascii-art"


def test_auto_mode_no_terminal_falls_back_to_ascii(monkeypatch):
    _stub_assets(monkeypatch, **{"logo.png": b"fake", "logo.ans": "ansi-art", "logo.txt": "ascii-art"})
    assert logo.render(_console(terminal=False)) == "ascii-art"


def test_auto_mode_ci_forces_ascii_even_on_a_real_terminal(monkeypatch):
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("KITTY_WINDOW_ID", "1")
    _stub_assets(monkeypatch, **{"logo.png": b"fake", "logo.ans": "ansi-art", "logo.txt": "ascii-art"})
    assert logo.render(_console(terminal=True)) == "ascii-art"


def test_no_color_disables_ansi_tier(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    _stub_assets(monkeypatch, **{"logo.ans": "ansi-art", "logo.txt": "ascii-art"})
    assert logo.render(_console(terminal=True)) == "ascii-art"


def test_console_without_color_system_falls_back_to_ascii(monkeypatch):
    _stub_assets(monkeypatch, **{"logo.ans": "ansi-art", "logo.txt": "ascii-art"})
    assert logo.render(_console(terminal=True, color=None)) == "ascii-art"


def test_auto_mode_uses_kitty_image_when_supported(monkeypatch):
    monkeypatch.setenv("KITTY_WINDOW_ID", "1")
    _stub_assets(monkeypatch, **{"logo.png": b"fake-bytes", "logo.ans": "ansi-art", "logo.txt": "ascii"})
    out = logo.render(_console(terminal=True))
    assert out is not None and out.startswith("\033_G")


def test_auto_mode_uses_iterm2_image_when_supported(monkeypatch):
    monkeypatch.setenv("TERM_PROGRAM", "iTerm.app")
    _stub_assets(monkeypatch, **{"logo.png": b"fake-bytes", "logo.ans": "ansi-art", "logo.txt": "ascii"})
    out = logo.render(_console(terminal=True))
    assert out is not None and out.startswith("\033]1337;File=")


def test_auto_mode_falls_back_to_ansi_when_no_image_protocol_detected(monkeypatch):
    _stub_assets(monkeypatch, **{"logo.ans": "ansi-art", "logo.txt": "ascii-art"})
    assert logo.render(_console(terminal=True)) == "ansi-art"


def test_auto_mode_returns_none_when_no_assets_ship_at_all(monkeypatch):
    _stub_assets(monkeypatch)
    assert logo.render(_console(terminal=True)) is None


def test_real_ascii_asset_ships_and_loads_via_the_package():
    # No stubbing: proves the packaged src/zerotrace/ui/assets/logo.txt actually
    # loads through importlib.resources, even before logo.png/logo.ans exist.
    art = logo.render(_console(terminal=False))
    assert art == "ZEROTRACE\nno trace. no leaks. stays safe.\n"


def test_kitty_escape_single_chunk_has_m0_immediately():
    escaped = logo._kitty_escape(b"tiny")
    b64 = base64.b64encode(b"tiny").decode("ascii")
    assert escaped == f"\033_Ga=T,f=100,m=0;{b64}\033\\"


def test_kitty_escape_chunks_long_payloads_and_terminates_with_m0():
    escaped = logo._kitty_escape(b"x" * 10000)
    segments = escaped.split("\033\\")[:-1]
    assert len(segments) > 1
    assert segments[0].startswith("\033_Ga=T,f=100,m=1;")
    assert segments[-1].startswith("\033_Gm=0;")


def test_iterm2_escape_format():
    escaped = logo._iterm2_escape(b"tiny")
    b64 = base64.b64encode(b"tiny").decode("ascii")
    assert escaped == f"\033]1337;File=inline=1;width=40;preserveAspectRatio=1;size=4:{b64}\a"
