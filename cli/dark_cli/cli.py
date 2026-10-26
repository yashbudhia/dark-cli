"""dark — AI red-teaming CLI for authorized security testing."""

from __future__ import annotations

from dotenv import load_dotenv
import typer

load_dotenv()

app = typer.Typer(
    name="dark",
    help="Find and prove security bugs in software you're authorized to test.",
    no_args_is_help=True,
)

ctf_app = typer.Typer(help="Sanctioned CTF challenges.", no_args_is_help=True)
app.add_typer(ctf_app, name="ctf")


@app.command()
def scan(
    target: str = typer.Argument(..., help="Target to test (must be one you are authorized to test)"),
    goal: str = typer.Option(..., "--goal", help="What to test, e.g. 'Test the archive workflow'"),
) -> None:
    """Explore, challenge, verify, and report on an authorized target."""
    # Pipeline lands with weekend milestone 2+ — see docs/PLAN.md.
    typer.echo(f"scan: target={target} goal={goal!r}")
    typer.echo("Not implemented yet — see docs/PLAN.md for the build order.")


@ctf_app.command("solve")
def ctf_solve(
    challenge: str = typer.Argument(..., help="Challenge dir or URL (sanctioned contest only)"),
) -> None:
    """Attempt a sanctioned CTF challenge and log refusal telemetry."""
    typer.echo(f"ctf solve: {challenge}")
    typer.echo("Not implemented yet — lands with milestone 4.")


if __name__ == "__main__":
    app()
