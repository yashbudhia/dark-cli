"""dark — AI red-teaming CLI for authorized security testing."""

from __future__ import annotations

import typer

from . import __version__
from .auth import register as register_auth
from .config import ConfigError, load_environment
from .desktop.cli import app as desktop_app
from .runs import app as runs_app

app = typer.Typer(
    name="dark",
    help="Connect your account, inspect authorized Windows apps, and manage saved test reports.",
    no_args_is_help=True,
)

ctf_app = typer.Typer(help="Sanctioned CTF challenges.", no_args_is_help=True)
app.add_typer(ctf_app, name="ctf")
app.add_typer(desktop_app, name="desktop")
app.add_typer(runs_app, name="runs")
register_auth(app)


@app.callback(invoke_without_command=True)
def main(
    version: bool = typer.Option(
        False, "--version", is_eager=True, help="Print the installed CLI version."
    ),
) -> None:
    if version:
        typer.echo(f"dark {__version__}")
        raise typer.Exit()
    try:
        load_environment()
    except ConfigError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc


@app.command()
def scan(
    target: str = typer.Argument(
        ..., help="Target to test (must be one you are authorized to test)"
    ),
    goal: str = typer.Option(..., "--goal", help="What to test, e.g. 'Test the archive workflow'"),
) -> None:
    """Explore, challenge, verify, and report on an authorized target."""
    # Pipeline lands with weekend milestone 2+ — see docs/PLAN.md.
    typer.echo(f"scan: target={target} goal={goal!r}")
    typer.echo("Not implemented yet — see docs/PLAN.md for the build order.")
    raise typer.Exit(2)


@ctf_app.command("solve")
def ctf_solve(
    challenge: str = typer.Argument(..., help="Challenge dir or URL (sanctioned contest only)"),
) -> None:
    """Attempt a sanctioned CTF challenge and log refusal telemetry."""
    typer.echo(f"ctf solve: {challenge}")
    typer.echo("Not implemented yet — lands with milestone 4.")
    raise typer.Exit(2)


if __name__ == "__main__":
    app()
