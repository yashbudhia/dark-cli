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
    monkeypatch.delenv("MONGODB_URI", raising=False)
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


@pytest.mark.parametrize("provider", ["", "resend", " RESEND "])
def test_resend_configuration_needs_no_cloudflare_credentials(provider):
    values = {
        "MONGODB_URI": "mongodb://synthetic.invalid",
        "DARK_AUTH_SECRET": "synthetic-auth-secret-" * 3,
        "DARK_EMAIL_FROM": "login@example.com",
        "DARK_EMAIL_PROVIDER": provider,
        "RESEND_API_KEY": "synthetic-resend-key",
    }
    assert service.missing_config(values) == []


def test_explicit_provider_requires_its_own_keys_without_fallback():
    values = {
        "MONGODB_URI": "mongodb://synthetic.invalid",
        "DARK_AUTH_SECRET": "synthetic-auth-secret-" * 3,
        "DARK_EMAIL_FROM": "login@example.com",
        "DARK_EMAIL_PROVIDER": "resend",
        "CLOUDFLARE_ACCOUNT_ID": "synthetic-account",
        "CLOUDFLARE_API_TOKEN": "synthetic-cloudflare-token",
    }
    assert service.missing_config(values) == ["RESEND_API_KEY"]
    values["RESEND_API_KEY"] = "synthetic-resend-key"
    values["DARK_EMAIL_PROVIDER"] = "cloudflare"
    assert service.missing_config(values) == []
    values["CLOUDFLARE_API_TOKEN"] = " "
    assert service.missing_config(values) == ["CLOUDFLARE_API_TOKEN"]


def test_default_provider_is_cloudflare_without_a_resend_key():
    values = {
        "MONGODB_URI": "mongodb://synthetic.invalid",
        "DARK_AUTH_SECRET": "synthetic-auth-secret-" * 3,
        "DARK_EMAIL_FROM": "login@example.com",
        "RESEND_API_KEY": " ",
    }
    assert service.missing_config(values) == [
        "CLOUDFLARE_ACCOUNT_ID",
        "CLOUDFLARE_API_TOKEN",
    ]
    values["DARK_EMAIL_FROM"] = ""
    assert "DARK_EMAIL_FROM" in service.missing_config(values)


def test_unknown_provider_is_rejected_without_printing_its_value():
    with pytest.raises(ValueError, match="must be resend or cloudflare") as failure:
        service.missing_config({"DARK_EMAIL_PROVIDER": "synthetic-private-value"})
    assert "synthetic-private-value" not in str(failure.value)


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


@pytest.mark.parametrize("production", [False, True])
def test_all_email_provider_secrets_are_excluded_from_frontend_and_build(
    tmp_path, monkeypatch, capsys, production
):
    executable = tmp_path / "frontend/node_modules/next/dist/bin/next"
    executable.parent.mkdir(parents=True)
    executable.touch()
    secret_keys = (
        "RAZORPAY_KEY_ID",
        "RAZORPAY_KEY_SECRET",
        "RAZORPAY_WEBHOOK_SECRET",
        "MONGODB_URI",
        "DARK_AUTH_SECRET",
        "DARK_EMAIL_FROM",
        "RESEND_API_KEY",
        "CLOUDFLARE_ACCOUNT_ID",
        "CLOUDFLARE_API_TOKEN",
    )
    values = {key: f"synthetic-file-{key}" for key in secret_keys}
    values.update(
        {
            "DARK_WEB_URL": "http://127.0.0.1:3012",
            "DARK_BACKEND_PORT": "8012",
            "DARK_EMAIL_PROVIDER": "resend",
        }
    )
    for key in secret_keys:
        monkeypatch.setenv(key, f"synthetic-environment-{key}")
    monkeypatch.setenv("DARK_EMAIL_PROVIDER", "resend")
    monkeypatch.setattr(service, "ROOT", tmp_path)
    monkeypatch.setattr(service, "environment", lambda path: dict(values))
    monkeypatch.setattr(service.shutil, "which", lambda name: "node")
    monkeypatch.setattr(service, "check_port", lambda port: None)
    monkeypatch.setattr(service, "wait_for_api", lambda *args: None)
    calls, builds = [], []

    def launch(command, cwd, environment):
        calls.append(environment)
        return SimpleNamespace(poll=lambda: 1)

    monkeypatch.setattr(service, "spawn", launch)
    monkeypatch.setattr(service, "stop_process", lambda process: None)
    monkeypatch.setattr(
        service.subprocess,
        "run",
        lambda command, **kwargs: builds.append(kwargs["env"]),
    )
    options = SimpleNamespace(
        allow_unconfigured=False,
        backend_port=None,
        frontend_port=None,
        production=production,
    )
    with pytest.raises(RuntimeError, match="process exited"):
        service.start(options)
    assert all(calls[0][key] == values[key] for key in secret_keys)
    for frontend_environment in [calls[1], *builds]:
        assert not (set(secret_keys) & frontend_environment.keys())
        assert "DARK_EMAIL_PROVIDER" not in frontend_environment
        assert frontend_environment["DARK_BACKEND_URL"] == "http://127.0.0.1:8012"
    assert len(builds) == int(production)
    output = capsys.readouterr().out
    assert not any(f"synthetic-file-{key}" in output for key in secret_keys)
    assert not any(f"synthetic-environment-{key}" in output for key in secret_keys)
