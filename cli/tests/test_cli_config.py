import json

import pytest
from typer.testing import CliRunner

from dark_cli.cli import app
from dark_cli.config import (
    ConfigError,
    configured_server,
    load_environment,
    remember_server,
    settings_path,
)


def test_working_directory_env_loading_preserves_explicit_environment(tmp_path, monkeypatch):
    monkeypatch.delenv("DARK_ENV_FILE")
    monkeypatch.delenv("DARK_SERVER_URL", raising=False)
    root = tmp_path / "workspace"
    nested = root / "nested"
    nested.mkdir(parents=True)
    (root / ".env").write_text(
        "DARK_SERVER_URL=https://workspace.example\nEXISTING_SETTING=from-file\n"
    )
    monkeypatch.setenv("EXISTING_SETTING", "from-shell")
    monkeypatch.chdir(nested)
    load_environment()
    import os

    assert os.environ["DARK_SERVER_URL"] == "https://workspace.example"
    assert os.environ["EXISTING_SETTING"] == "from-shell"


def test_cli_preferences_remember_only_the_server_and_can_be_overridden():
    remember_server("https://dark.example")
    assert configured_server(None) == "https://dark.example"
    assert configured_server("https://other.example") == "https://other.example"
    assert json.loads(settings_path().read_text()) == {"server": "https://dark.example"}
    settings_path().write_text("broken-json")
    assert configured_server("https://explicit.example") == "https://explicit.example"
    with pytest.raises(ConfigError):
        configured_server(None)


def test_invalid_environment_file_is_actionable_without_traceback(monkeypatch, tmp_path):
    monkeypatch.setenv("DARK_ENV_FILE", str(tmp_path / "missing.env"))
    result = CliRunner().invoke(app, ["whoami"])
    assert result.exit_code == 2
    assert "DARK_ENV_FILE" in result.output and "Traceback" not in result.output
    assert CliRunner().invoke(app, ["--version"]).exit_code == 0


def test_unimplemented_modes_do_not_claim_success():
    runner = CliRunner()
    assert runner.invoke(app, ["scan", "http://localhost", "--goal", "Demo"]).exit_code == 2
    assert runner.invoke(app, ["ctf", "solve", "fixture"]).exit_code == 2
    assert runner.invoke(app, ["--version"]).output.startswith("dark ")


def test_environment_file_is_loaded_before_command_server_resolution(monkeypatch, tmp_path):
    import httpx

    from dark_cli import auth

    path = tmp_path / "service.env"
    path.write_text("DARK_SERVER_URL=https://configured.example\n")
    monkeypatch.setenv("DARK_ENV_FILE", str(path))
    monkeypatch.delenv("DARK_SERVER_URL", raising=False)
    selected = []
    client_class = auth.AccountClient

    def client(server):
        selected.append(server)
        return client_class(
            server,
            httpx.MockTransport(
                lambda request: httpx.Response(
                    503,
                    json={
                        "ready": False,
                        "checks": {
                            name: False
                            for name in (
                                "database_configured",
                                "auth_secret_configured",
                                "email_configured",
                                "mongodb_reachable",
                            )
                        },
                    },
                )
            ),
        )

    monkeypatch.setattr(auth, "AccountClient", client)
    result = CliRunner().invoke(app, ["doctor"])
    assert result.exit_code == 2 and selected == ["https://configured.example"]


def test_environment_server_overrides_saved_preference(monkeypatch):
    remember_server("https://saved.example")
    monkeypatch.setenv("DARK_SERVER_URL", "https://environment.example")
    assert configured_server(None) == "https://environment.example"
    assert configured_server("https://explicit.example") == "https://explicit.example"


def test_account_cli_import_does_not_load_desktop_model_or_mcp_dependencies():
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import dark_cli.cli; assert 'mcp' not in sys.modules; assert 'openai' not in sys.modules",
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
