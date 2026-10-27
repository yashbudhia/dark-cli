"""Terminal feedback: a smooth spinner and per-tool-call status lines.

Everything draws on stderr, so JSON and other results on stdout stay machine-readable.
Nothing is drawn when stderr is not a terminal or DARK_NO_SPINNER is set.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from contextlib import contextmanager

from rich.console import Console, ConsoleOptions, RenderResult
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text

console = Console(stderr=True, highlight=False)

SPINNER = "dots"
REFRESH_PER_SECOND = 20


def enabled() -> bool:
    return (
        console.is_terminal
        and not console.is_dumb_terminal
        and not os.environ.get("DARK_NO_SPINNER")
    )


def clock_text(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, rest = divmod(int(seconds), 60)
    return f"{minutes}m{rest:02d}s"


class _Line:
    """Spinner, label and elapsed time; Rich re-renders it on every refresh tick."""

    def __init__(self, label: str) -> None:
        self.label = label
        self.started = time.monotonic()
        self.spinner = Spinner(SPINNER, style="cyan")

    def __rich_console__(self, rich_console: Console, options: ConsoleOptions) -> RenderResult:
        elapsed = clock_text(time.monotonic() - self.started)
        self.spinner.text = Text.assemble(self.label, ("  " + elapsed, "dim"))
        yield self.spinner


_live: Live | None = None
_line: _Line | None = None


@contextmanager
def progress(label: str) -> Iterator[None]:
    """Show a spinner while the block runs. Nested calls just swap the label."""
    global _live, _line
    if not enabled():
        yield
        return
    if _live is not None and _line is not None:
        previous = _line.label
        _line.label = label
        try:
            yield
        finally:
            _line.label = previous
        return
    _line = _Line(label)
    _live = Live(
        _line,
        console=console,
        refresh_per_second=REFRESH_PER_SECOND,
        transient=True,
    )
    try:
        with _live:
            yield
    finally:
        _live = _line = None


@contextmanager
def tool_call(name: str, detail: str = "") -> Iterator[None]:
    """Spin while a tool runs, then leave a ✓/✗ line with how long it took."""
    started = time.monotonic()
    shown = f"{name} {detail}".strip()
    ok = False
    try:
        with progress(shown):
            yield
        ok = True
    finally:
        if enabled():
            mark = Text("✓", style="green") if ok else Text("✗", style="red")
            line = Text.assemble(
                mark, " ", shown, ("  " + clock_text(time.monotonic() - started), "dim")
            )
            # While a Live is active, Rich draws printed lines above the spinner.
            console.print(line)
