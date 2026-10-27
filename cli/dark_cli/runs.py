"""Explicit export of a bounded desktop report; raw tool evidence stays local."""

from __future__ import annotations

import hashlib
import json
import re
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Literal

import typer
from pydantic import BaseModel, Field, StrictBool, ValidationError

from . import ui
from .auth import AccountClient, Credentials, LoginError

app = typer.Typer(help="Upload, list, and inspect saved desktop reports.", no_args_is_help=True)
MAX_REPORT_BYTES = 256 * 1024


class ObservedText(BaseModel):
    text: str | None = Field(default=None, max_length=10000)


class Assertion(BaseModel):
    expected_text: str = Field(max_length=10000)
    passed: StrictBool
    step: int | None = Field(default=None, ge=1, le=1000)
    match: Literal["exact", "contains"] = "contains"
    observed: ObservedText | None = None


class Window(BaseModel):
    title: str = Field(default="Unknown window", max_length=1000)


class LocalReport(BaseModel):
    status: Literal["observed", "passed", "failed", "error", "preview"]
    finished_at: datetime
    window: Window = Field(default_factory=Window)
    scenario: str | None = Field(default=None, max_length=2000)
    assertions: list[Assertion] = Field(default_factory=list, max_length=100)
    reason: str | None = Field(default=None, max_length=10000)
    error: str | None = Field(default=None, max_length=10000)


class SavedRun(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    target: str
    goal: str
    status: str = Field(pattern=r"^[a-z_]{1,40}$")
    started_at: datetime | None = None
    finished_at: datetime | None = None
    kind: Literal["scan", "desktop"] = "scan"
    desktop_report: dict | None = None


def display_text(value: str) -> str:
    return " ".join(
        "".join(
            character for character in value if character.isprintable() or character.isspace()
        ).split()
    )


def connected_token(client: AccountClient) -> str:
    token = Credentials(client.server).get()
    if not token:
        raise LoginError("Not connected. Run dark login before accessing saved reports.")
    return token


@app.command("list")
def list_runs(
    server: str | None = typer.Option(None, envvar="DARK_SERVER_URL"),
    json_output: bool = typer.Option(False, "--json", help="Print the latest saved runs as JSON."),
) -> None:
    """List the latest 100 saved runs in your account."""
    client = None
    try:
        client = AccountClient(server)
        token = connected_token(client)
        with ui.tool_call("runs", "list"):
            rows = client.require_success(
                client.request("GET", "/api/runs", token=token), expect_list=True
            )
        try:
            records = [SavedRun.model_validate(row) for row in rows]
        except ValidationError as exc:
            raise LoginError("Dark server returned an invalid run list.") from exc
        if json_output:
            typer.echo(
                json.dumps(
                    [row.model_dump(mode="json") for row in records], ensure_ascii=False, indent=2
                )
            )
        elif not records:
            typer.echo("No uploaded runs yet. Use dark runs upload <run-directory>.")
        else:
            for row in records:
                typer.echo(f"{row.id}  {row.status}  {display_text(row.goal)}")
    except LoginError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    finally:
        if client:
            client.close()


@app.command()
def show(
    run_id: str = typer.Argument(..., help="Run ID printed by upload or runs list."),
    server: str | None = typer.Option(None, envvar="DARK_SERVER_URL"),
    open_report: bool = typer.Option(False, "--open", help="Also open this report on the website."),
) -> None:
    """Print a saved run and its exported evidence as JSON."""
    client = None
    try:
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", run_id):
            raise LoginError("Invalid run ID. Use an ID returned by dark runs list.")
        client = AccountClient(server)
        token = connected_token(client)
        with ui.tool_call("runs", f"show {run_id}"):
            data = client.require_success(
                client.request("GET", f"/api/runs/{run_id}", token=token)
            )
        try:
            record = SavedRun.model_validate(data)
        except ValidationError as exc:
            raise LoginError("Dark server returned an invalid run report.") from exc
        if record.id != run_id:
            raise LoginError("Dark server returned an unexpected report ID.")
        typer.echo(json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2))
        if open_report:
            url = f"{client.server}/dashboard/runs/{run_id}"
            try:
                if webbrowser.open(url) is False:
                    typer.echo(f"Could not open the browser. Open {url} manually.", err=True)
            except (webbrowser.Error, OSError):
                typer.echo(f"Could not open the browser. Open {url} manually.", err=True)
    except LoginError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    finally:
        if client:
            client.close()


def prepare_upload(directory: Path) -> tuple[str, dict]:
    try:
        with (directory / "report.json").open("rb") as stream:
            raw = stream.read(MAX_REPORT_BYTES + 1)
        if len(raw) > MAX_REPORT_BYTES:
            raise LoginError("report.json exceeds the 256 KiB upload limit.")
        report = LocalReport.model_validate_json(raw)
    except OSError as exc:
        raise LoginError("Cannot read report.json in the selected run directory.") from exc
    except ValidationError as exc:
        raise LoginError("report.json is not a valid completed Dark desktop report.") from exc
    payload = {
        "status": report.status,
        "finished_at": report.finished_at.isoformat(),
        "window_title": report.window.title,
        "scenario": report.scenario,
        "reason": report.reason,
        "error": report.error,
        "verified_finding": False,
        "assertions": [
            {
                "expected_text": item.expected_text,
                "passed": item.passed,
                "step": item.step,
                "match": item.match,
                "observed_text": item.observed.text if item.observed else None,
            }
            for item in report.assertions
        ],
    }
    fingerprint = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return fingerprint, payload


@app.command()
def upload(
    directory: Path = typer.Argument(
        ..., exists=True, file_okay=False, help="A saved .dark/runs/<run> directory."
    ),
    server: str | None = typer.Option(None, envvar="DARK_SERVER_URL"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show the exact export without signing in or uploading."
    ),
    open_report: bool = typer.Option(
        False, "--open", help="Open the uploaded report in your browser."
    ),
) -> None:
    """Upload a report summary and assertions; excludes snapshots, screenshots and events."""
    client = None
    try:
        fingerprint, payload = prepare_upload(directory)
        if dry_run:
            typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
            return
        client = AccountClient(server)
        token = Credentials(client.server).get()
        if not token:
            raise LoginError("Not connected. Run dark login before uploading.")
        with ui.tool_call("runs", "upload"):
            response = client.request(
                "PUT", f"/api/runs/import/{fingerprint}", token=token, json=payload
            )
            result = client.require_success(response)
        expected_id = f"desktop_{fingerprint}"
        if result.get("id") != expected_id:
            raise LoginError("The server returned an unexpected report ID.")
        url = f"{client.server}/dashboard/runs/{expected_id}"
        typer.echo(f"Report uploaded: {url}")
        if open_report:
            try:
                if webbrowser.open(url) is False:
                    typer.echo("Could not open the browser. Use the URL above.")
            except (webbrowser.Error, OSError):
                typer.echo("Could not open the browser. Use the URL above.")
    except LoginError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    finally:
        if client:
            client.close()
