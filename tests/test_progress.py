"""Tiered progress bar: CP437 shaded blocks -> plain ASCII -> discrete log lines."""
import io

import pytest
from rich.console import Console

from zerotrace.ui import progress
from zerotrace.ui.progress import Bar

_ENV_KEYS = ("KITTY_WINDOW_ID", "TERM", "TERM_PROGRAM", "CI", "NO_COLOR")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    # This suite's own CI sets CI=true, which would otherwise force every
    # "shaded tier" test below into the ascii/plain fallback.
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


class _FakeTTY(io.StringIO):
    def isatty(self) -> bool:
        return True


def _shaded_console(file) -> Console:
    return Console(file=file, force_terminal=True, color_system="truecolor")


def _ascii_console(file) -> Console:
    return Console(file=file, force_terminal=True, color_system=None)


def test_non_tty_prints_discrete_step_lines_and_never_uses_carriage_return():
    out = io.StringIO()
    bar = Bar(3, file=out)
    bar.step("first")
    bar.step("second")
    bar.finish()
    assert "\r" not in out.getvalue()
    assert out.getvalue().splitlines() == ["zerotrace: [1/3] first", "zerotrace: [2/3] second"]


def test_tty_without_unicode_support_uses_plain_ascii_bar():
    out = _FakeTTY()
    bar = Bar(4, file=out, console=_ascii_console(out))
    bar.step("one")
    bar.finish()
    text = out.getvalue()
    assert "\r" in text
    assert progress._TOP_RULE not in text and progress._BOTTOM_RULE not in text
    assert progress._FULL not in text and progress._LIGHT not in text
    assert "#" in text and "-" in text


def test_tty_with_unicode_support_uses_shaded_blocks_framed_by_half_block_rules():
    out = _FakeTTY()
    bar = Bar(2, file=out, console=_shaded_console(out))
    bar.step("one")
    mid = out.getvalue()
    bar.step("two")
    bar.finish()
    text = out.getvalue()

    frame_rule = progress._TOP_RULE * (progress._WIDTH + 2)
    assert text.startswith(frame_rule + "\n")
    assert text.count(frame_rule) == 1  # framed once, not once per redraw
    assert text.endswith(progress._BOTTOM_RULE * (progress._WIDTH + 2) + "\n")
    assert "#" not in text and "-" not in text

    # the very first (half-done) redraw already used the shaded tier, not ascii
    assert progress._TOP_RULE in mid and progress._FULL in mid


def test_shaded_bar_uses_the_full_gradient_while_partially_filled():
    out = _FakeTTY()
    bar = Bar(7, file=out, console=_shaded_console(out))
    seen_shades: set[str] = set()
    for label in "abcdefg":
        bar.step(label)
        frame = out.getvalue().split("\r")[-1]
        seen_shades.update(ch for ch in frame if ch in (progress._FULL, progress._DARK,
                                                          progress._MED, progress._LIGHT))
    bar.finish()
    final_frame = out.getvalue().split("\r")[-1]
    # done == total -> solid full block, no shade characters left over
    assert {progress._FULL, progress._DARK, progress._MED, progress._LIGHT} & set(final_frame) \
        == {progress._FULL}
    # the gradient was genuinely exercised somewhere along the way, not just full/empty
    assert {progress._DARK, progress._MED, progress._LIGHT} & seen_shades


def test_shaded_bar_fills_proportionally_and_completes_at_full_block():
    out = _FakeTTY()
    bar = Bar(4, file=out, console=_shaded_console(out))
    bar.step("quarter")
    first = out.getvalue().split("\r")[-1]
    assert first.count(progress._FULL) == progress._WIDTH // 4
    bar.step("half")
    bar.step("three-quarter")
    bar.step("done")
    last = out.getvalue().split("\r")[-1]
    assert last.count(progress._FULL) == progress._WIDTH


def test_step_never_exceeds_total():
    out = io.StringIO()
    bar = Bar(2, file=out)
    for label in ("a", "b", "c", "d"):
        bar.step(label)
    assert bar.done == 2
    assert "zerotrace: [2/2] d" in out.getvalue()


def test_zero_total_is_clamped_to_avoid_division_by_zero():
    out = io.StringIO()
    bar = Bar(0, file=out)
    bar.step("only step")
    assert "zerotrace: [1/1] only step" in out.getvalue()


def test_finish_is_a_no_op_before_any_step():
    out = _FakeTTY()
    Bar(3, file=out, console=_shaded_console(out)).finish()
    assert out.getvalue() == ""

