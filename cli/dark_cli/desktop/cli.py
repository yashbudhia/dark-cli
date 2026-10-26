"""Desktop commands. Discovery and model previews never inject input."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

import typer

from .decisions import choose_route
from .evidence import Evidence
from .scenario import exercise, load_scenario
from .windows import REQUIRED_TOOLS, connect, executable, repository_root, snapshot_text

app = typer.Typer(
    help="Inspect Windows apps, record evidence, and run explicit desktop exercises.",
    no_args_is_help=True,
)


def emit(value: Any) -> None:
    typer.echo(json.dumps(value, ensure_ascii=False, indent=2))


def error_message(exc: BaseException) -> str:
    if isinstance(exc, BaseExceptionGroup):
        return "; ".join(error_message(item) for item in exc.exceptions)
    return str(exc) or type(exc).__name__


def run(coro: Coroutine[Any, Any, Any], evidence: Evidence | None = None) -> Any:
    try:
        return asyncio.run(coro)
    except Exception as exc:
        message = error_message(exc)
        result = (
            evidence.finish("error", error=message)
            if evidence
            else {"status": "error", "error": message}
        )
        emit(result)
        raise typer.Exit(2) from exc


def recorder(output: Path | None) -> Evidence:
    return Evidence(output or repository_root() / ".dark" / "runs")


@app.command()
def doctor() -> None:
    """Check the actual executable and MCP tool handshake; no API key needed."""

    async def check() -> dict[str, Any]:
        async with connect() as desktop:
            return {
                "status": "ready",
                "executable": executable(),
                "required_tools": sorted(REQUIRED_TOOLS),
                "available_tools": len(desktop.tools),
            }

    emit(run(check()))


@app.command()
def windows() -> None:
    """List observable windows. Select an exact title for subsequent commands."""

    async def collect() -> Any:
        async with connect() as desktop:
            return await desktop.windows()

    emit(run(collect()))


@app.command()
def probe(
    title: str = typer.Option(
        ..., "--title", help="Exact, unique title returned by desktop windows."
    ),
    expect: list[str] = typer.Option(
        [], "--expect", help="Text that must appear in the accessibility snapshot; repeatable."
    ),
    screenshot: bool = typer.Option(
        False, "--screenshot", help="Save a PNG of only the selected window."
    ),
    output: Path | None = typer.Option(
        None, "--output", help="Parent directory for local evidence."
    ),
) -> None:
    """Observe an app and check text expectations without clicking or typing."""
    evidence = recorder(output)

    async def inspect() -> dict[str, Any]:
        async with connect(evidence) as desktop:
            window = await desktop.select(title)
            state = await desktop.snapshot(str(window["handle"]))
            evidence.save("snapshot.json", state)
            if screenshot:
                image = await desktop.call(
                    "screenshot_control",
                    {
                        "action": "capture",
                        "target": "window",
                        "windowHandle": str(window["handle"]),
                        "annotate": False,
                        "includeImage": False,
                        "imageFormat": "png",
                        "outputMode": "file",
                        "outputPath": str((evidence.path / "screenshot.png").resolve()),
                    },
                )
                evidence.save("screenshot-result.json", image)
            text = snapshot_text(state).casefold()
            checks = [
                {"expected_text": item, "passed": bool(item.strip()) and item.casefold() in text}
                for item in expect
            ]
            for check in checks:
                evidence.event("assertion", **check)
            status = (
                "observed"
                if not checks
                else "passed"
                if all(check["passed"] for check in checks)
                else "failed"
            )
            return evidence.finish(status, window=window, assertions=checks)

    result = run(inspect(), evidence)
    emit(result)
    if result["status"] == "failed":
        raise typer.Exit(1)


@app.command()
def decide(
    title: str = typer.Option(..., "--title", help="Exact title of the window to inspect."),
    goal: str = typer.Option(..., "--goal", help="Task for Jev's bounded next-step preview."),
    output: Path | None = typer.Option(None, "--output"),
) -> None:
    """Ask Jev which kind of step to take. Never execute its choice."""
    evidence = recorder(output)

    async def preview() -> dict[str, Any]:
        async with connect(evidence) as desktop:
            window = await desktop.select(title)
            state = await desktop.snapshot(str(window["handle"]))
            evidence.save("snapshot.json", state)
            decision = await choose_route(goal, state)
            evidence.event("decision_preview", goal=goal, decision=decision)
            return evidence.finish("preview", window=window, decision=decision)

    emit(run(preview(), evidence))


@app.command("exercise")
def run_exercise(
    scenario: Path = typer.Argument(..., exists=True, dir_okay=False),
    apply: bool = typer.Option(
        False, "--apply", help="Execute the scenario's explicit clicks and typing."
    ),
    output: Path | None = typer.Option(None, "--output"),
) -> None:
    """Validate or execute a JSON scenario. Re-running re-discovers every control."""
    try:
        spec = load_scenario(scenario)
    except (ValueError, OSError) as exc:
        emit({"status": "error", "error": str(exc)})
        raise typer.Exit(2) from exc
    if not apply:
        emit({"status": "preview", "executed": False, "scenario": spec.model_dump(mode="json")})
        return
    evidence = recorder(output)

    async def execute() -> dict[str, Any]:
        async with connect(evidence) as desktop:
            return await exercise(desktop, spec, evidence)

    result = run(execute(), evidence)
    emit(result)
    if result["status"] == "failed":
        raise typer.Exit(1)
