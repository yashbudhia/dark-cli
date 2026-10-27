"""Allow python -m dark_cli after an ordinary package installation."""

import sys

args = sys.argv[1:]
RESUME = {"--resume", "--continue"}
# Opening the chat needs no command parsing. Skipping Typer and the command modules
# shows the prompt sooner; everything else, including --help, goes through Typer.
chat_fast = not args or args == ["chat"] or (set(args) <= RESUME and len(args) == 1)
chat_fast = chat_fast or (len(args) == 2 and args[0] == "chat" and args[1] in RESUME)
run_fast = len(args) == 2 and args[0] == "run" and args[1][:1] != "-"
if chat_fast or run_fast:
    from .config import ConfigError, load_environment

    try:
        load_environment()
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(2) from exc
    from .chat import launch

    succeeded = launch(args[1] if run_fast else None, resume=bool(set(args) & RESUME))
    raise SystemExit(0 if succeeded or not run_fast else 1)
if args == ["--version"]:
    from . import __version__

    print(f"dark {__version__}")
    raise SystemExit(0)

from .cli import app  # noqa: E402

app(prog_name="dark")
