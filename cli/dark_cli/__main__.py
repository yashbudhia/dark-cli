"""Allow python -m dark_cli after an ordinary package installation."""

from .cli import app

app(prog_name="dark")
