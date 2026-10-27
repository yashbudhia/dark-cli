import io

import pytest
from rich.console import Console

from dark_cli import ui


@pytest.fixture
def tty(monkeypatch):
    monkeypatch.setenv("TERM", "xterm")
    stream = io.StringIO()
    console = Console(file=stream, force_terminal=True, width=80, color_system=None)
    monkeypatch.setattr(ui, "console", console)
    monkeypatch.delenv("DARK_NO_SPINNER", raising=False)
    return stream


def test_silent_when_not_a_terminal(monkeypatch):
    stream = io.StringIO()
    monkeypatch.setattr(ui, "console", Console(file=stream, force_terminal=False))
    with ui.tool_call("window_management", "list"):
        pass
    assert stream.getvalue() == ""


def test_opt_out_environment_variable(tty, monkeypatch):
    monkeypatch.setenv("DARK_NO_SPINNER", "1")
    with ui.tool_call("ui_snapshot"):
        pass
    assert tty.getvalue() == ""


def test_tool_call_reports_success_and_failure(tty):
    with ui.tool_call("window_management", "list"):
        pass
    with pytest.raises(RuntimeError):
        with ui.tool_call("ui_find"):
            raise RuntimeError("boom")
    output = tty.getvalue()
    assert "✓ window_management list" in output
    assert "✗ ui_find" in output


def test_nested_progress_restores_state(tty):
    with ui.progress("outer"):
        with ui.tool_call("inner"):
            pass
        assert ui._line is not None and ui._line.label == "outer"
    assert ui._live is None and ui._line is None
    assert "✓ inner" in tty.getvalue()
