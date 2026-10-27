"""Non-secret CLI preferences and explicit working-directory environment loading."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

DEFAULT_SERVER = "https://dark-cli-web.vercel.app"


class ConfigError(Exception):
    pass


def load_environment() -> None:
    try:
        explicit = os.getenv("DARK_ENV_FILE")
        if explicit:
            path = Path(explicit).expanduser()
            if not path.is_file():
                raise ConfigError("DARK_ENV_FILE does not point to a readable environment file.")
            load_dotenv(path, override=False)
        else:
            # Installed packages live outside the workspace; search from the caller's cwd.
            load_dotenv(find_dotenv(usecwd=True), override=False)
    except (OSError, UnicodeError) as exc:
        raise ConfigError("Cannot read the CLI environment file.") from exc


def app_directory() -> Path:
    """The folder click.get_app_dir chooses, without importing Typer for the chat."""
    if os.name == "nt":
        return Path(os.environ.get("APPDATA") or Path.home()) / "dark-cli"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "dark-cli"
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "dark-cli"


def settings_path() -> Path:
    directory = os.getenv("DARK_CONFIG_DIR")
    return (Path(directory).expanduser() if directory else app_directory()) / "config.json"


def configured_server(explicit: str | None) -> str:
    if explicit is not None:
        return explicit
    environment = os.getenv("DARK_SERVER_URL")
    if environment:
        return environment
    path = settings_path()
    try:
        if not path.exists():
            return DEFAULT_SERVER
        if path.stat().st_size > 8192:
            raise ValueError("Settings too large")
        value = json.loads(path.read_text(encoding="utf-8"))
        server = value.get("server") if isinstance(value, dict) else None
        if not isinstance(server, str) or not server:
            raise ValueError("Missing server")
        return server
    except (OSError, ValueError) as exc:
        raise ConfigError(
            "CLI preferences are unreadable. Pass --server to select the website explicitly."
        ) from exc


def remember_server(server: str) -> None:
    path = settings_path()
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            json.dump({"server": server}, stream)
            stream.write("\n")
        temporary.replace(path)
    except OSError as exc:
        raise ConfigError(
            "Could not save the default server. Continue using --server for this website."
        ) from exc
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                # A failed cleanup can leave only a non-secret server preference.
                pass
