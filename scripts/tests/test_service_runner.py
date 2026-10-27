import importlib.util
import socket
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from dotenv import dotenv_values

module_spec = importlib.util.spec_from_file_location(
    "dark_service_runner", Path(__file__).parents[1] / "service.py"
)
service = importlib.util.module_from_spec(module_spec)
sys.modules[module_spec.name] = service
module_spec.loader.exec_module(service)


def test_env_initialization_preserves_existing_credentials_and_auth_secret(tmp_path):
    template = tmp_path / "template"
    template.write_text(
        "MONGODB_URI=\nDARK_AUTH_SECRET=\nDARK_WEB_URL=http://127.0.0.1:3000\n"
    )
    destination = tmp_path / ".env"
    destination.write_text(
        "MONGODB_URI='mongodb://private-credential@example.invalid'\n"
    )
    assert service.initialize_env(template, destination) is False
    first = dotenv_values(destination)
    assert first["MONGODB_URI"] == "mongodb://private-credential@example.invalid"
    assert len(first["DARK_AUTH_SECRET"]) >= 32
    assert first["DARK_WEB_URL"] == "http://127.0.0.1:3000"
    service.initialize_env(template, destination)
    assert dotenv_values(destination)["DARK_AUTH_SECRET"] == first["DARK_AUTH_SECRET"]


def test_env_initialization_creates_file_and_keeps_an_existing_secret(tmp_path):
    template = tmp_path / "template"
    template.write_text(
        "DARK_AUTH_SECRET='user-supplied-secret-12345678901234567890'\n"
    )
    destination = tmp_path / ".env"
    assert service.initialize_env(template, destination) is True
    assert (
        dotenv_values(destination)["DARK_AUTH_SECRET"]
        == "user-supplied-secret-12345678901234567890"
    )


def test_environment_variables_override_file_without_printing_secrets(
    tmp_path, monkeypatch
):
    path = tmp_path / ".env"
    path.write_text("DARK_AUTH_SECRET='file-value'\nMONGODB_URI=\n")
    monkeypatch.setenv("DARK_AUTH_SECRET", "environment-value")
    result = service.environment(path)
    assert result["DARK_AUTH_SECRET"] == "environment-value"
    assert "MONGODB_URI" in service.missing_config(result)
    assert "DARK_AUTH_SECRET" not in service.missing_config(result)


def test_local_ports_update_origin_but_preserve_public_https_origin():
    assert (
        service.local_origin("http://127.0.0.1:3000", 3012) == "http://127.0.0.1:3012"
    )
    assert service.local_origin("https://dark.example", 3012) == "https://dark.example"
    assert (
        service.local_origin("http://localhost:3000", 3012) == "http://localhost:3012"
    )


def test_port_guard_refuses_occupied_port():
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        with pytest.raises(ValueError, match="in use"):
            service.check_port(occupied.getsockname()[1])
    for value in (0, -1, 65536):
        with pytest.raises(ValueError, match="between"):
            service.check_port(value)


def test_runner_preserves_configured_local_origin_and_cleans_up_failed_start(
    tmp_path, monkeypatch, capsys
):
    executable = tmp_path / "frontend/node_modules/next/dist/bin/next"
    executable.parent.mkdir(parents=True)
    executable.touch()
    monkeypatch.setattr(service, "ROOT", tmp_path)
    monkeypatch.setattr(
        service,
        "environment",
        lambda path: {
            "DARK_WEB_URL": "http://localhost:3012",
            "DARK_BACKEND_PORT": "8012",
            "CLOUDFLARE_API_TOKEN": "synthetic-backend-secret",
        },
    )
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "synthetic-global-secret")
    monkeypatch.setattr(service.shutil, "which", lambda name: "node")
    ports, calls, stopped = [], [], []
    monkeypatch.setattr(service, "check_port", ports.append)
    monkeypatch.setattr(service, "wait_for_api", lambda *args: None)

    def launch(command, cwd, values):
        process = SimpleNamespace(poll=lambda: 1)
        calls.append((command, values, process))
        return process

    monkeypatch.setattr(service, "spawn", launch)
    monkeypatch.setattr(service, "stop_process", stopped.append)
    options = SimpleNamespace(
        allow_unconfigured=True, backend_port=None, frontend_port=None, production=False
    )
    with pytest.raises(RuntimeError, match="process exited"):
        service.start(options)
    assert ports == [3012, 8012]
    assert calls[0][1]["DARK_WEB_URL"] == "http://localhost:3012"
    assert "CLOUDFLARE_API_TOKEN" not in calls[1][1]
    assert calls[1][1]["DARK_BACKEND_URL"] == "http://127.0.0.1:8012"
    assert stopped == [calls[1][2], calls[0][2]]
    output = capsys.readouterr().out
    assert "Dark website: http://localhost:3012" in output
    assert (
        "synthetic-backend-secret" not in output
        and "synthetic-global-secret" not in output
    )
