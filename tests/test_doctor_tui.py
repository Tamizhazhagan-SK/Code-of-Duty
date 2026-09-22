"""The full-screen doctor, driven through Textual's Pilot against a sandboxed repo."""
import threading
import time

import pytest

pytest.importorskip("textual", reason="install the tui extra to test the full-screen doctor")
pytest.importorskip("pytest_asyncio", reason="pytest-asyncio drives the Textual Pilot")

from textual.widgets import Static

from zerotrace import doctor
from zerotrace.doctor import FAIL, OK, Check
from zerotrace.ui.tui_common import ConfirmScreen
from zerotrace.ui.tui_doctor import DoctorApp


def _plain(app) -> str:
    return str(app.query_one("#detail_body", Static).render())


async def _settle(pilot, app, timeout: float = 30.0) -> None:
    """Wait for the background checks to finish."""
    deadline = time.monotonic() + timeout
    while app.running:
        assert time.monotonic() < deadline, "the checks never finished"
        await pilot.pause(0.05)
    await pilot.pause()


def _go_to(app, name: str) -> None:
    app.table.move_cursor(row=[check.name for check in app.listed].index(name))


async def test_checks_arrive_and_an_unprotected_repo_fails(repo):
    app = DoctorApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await _settle(pilot, app)
        names = [check.name for check in app.checks]
        assert "python" in names and doctor.REPO_PROTECTED in names
        assert app.table.row_count == len(app.checks)
        assert "failed" in app.status_text
        await pilot.press("q")
        await pilot.pause()
    assert app.return_value == 1, "the same exit code as `zerotrace doctor`"


async def test_every_check_explains_what_it_means(repo):
    app = DoctorApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await _settle(pilot, app)
        assert [c.name for c in app.checks if c.name not in doctor.ABOUT] == []
        _go_to(app, doctor.REPO_PROTECTED)
        await pilot.pause()
        assert doctor.ABOUT[doctor.REPO_PROTECTED] in _plain(app)


async def test_repairing_the_repo_hook_asks_first_then_checks_again(repo):
    app = DoctorApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await _settle(pilot, app)
        assert "repair" in app.actions_for(app.current())
        await pilot.click("#do-repair")
        await pilot.pause()
        assert isinstance(app.screen, ConfirmScreen)
        await pilot.press("y")
        await pilot.pause()
        await _settle(pilot, app)
        protected = next(c for c in app.checks if c.name == doctor.REPO_PROTECTED)
        assert protected.status == OK
        await pilot.press("Q")
        await pilot.pause()
    assert app.return_value == 0


async def test_warm_and_pin_are_offered_only_when_the_model_answers(repo):
    """Nothing listens on the sandbox endpoint, so there is no model to warm or pin."""
    app = DoctorApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await _settle(pilot, app)
        available = app.actions_for(app.current())
        assert "warm" not in available and "pin" not in available
        await pilot.press("w")
        await pilot.pause()
        assert not app.running, "W refuses rather than starting a run that warms nothing"


async def test_enter_and_the_arrow_keys_reach_the_fixes(repo):
    app = DoctorApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await _settle(pilot, app)
        await pilot.press("enter")
        await pilot.pause()
        assert app.focused.id == "do-rerun"
        await pilot.press("down")
        await pilot.pause()
        assert app.focused.id == "do-repair", "hidden actions are skipped"
        await pilot.press("up", "enter")
        await pilot.pause()
        await _settle(pilot, app)
        assert app.checks, "Enter on the button ran the checks again"


async def test_leaving_before_the_checks_finish_is_not_a_pass(repo, monkeypatch):
    gate = threading.Event()

    def slow(pin_model=False, warm=False, listener=None):
        listener(Check(OK, "python", "here"))
        gate.wait(10)
        return doctor.Report()

    monkeypatch.setattr(doctor, "collect", slow)
    app = DoctorApp()
    try:
        async with app.run_test() as pilot:
            await pilot.pause(0.2)
            assert app.running and len(app.checks) == 1, "results show as they arrive"
            await pilot.press("q")
            await pilot.pause()
    finally:
        gate.set()
    assert app.return_value == 1


async def test_a_crashing_check_is_a_failure_and_its_text_is_not_markup(repo, monkeypatch):
    def broken(**_):
        raise RuntimeError("[/] exploded")

    monkeypatch.setattr(doctor, "collect", broken)
    app = DoctorApp()
    async with app.run_test() as pilot:
        await _settle(pilot, app)
        assert [check.status for check in app.checks] == [FAIL]
        assert "[/] exploded" in _plain(app)
        await pilot.press("q")
        await pilot.pause()
    assert app.return_value == 1
