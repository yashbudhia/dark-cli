"""Configuration tests use only synthetic files and never echo configuration values."""

import os
import subprocess
import sys

from app.settings import Settings


def test_settings_read_private_dotenv_without_mutating_process_env(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("MONGODB_URI", raising=False)
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("DARK_WEB_URL", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "MONGODB_URI=mongodb://127.0.0.1:27017/synthetic\n"
        "RESEND_API_KEY=test-only-synthetic-key\n"
        "DARK_WEB_URL=http://127.0.0.1:3008\n",
        encoding="utf-8-sig",
    )
    before = dict(os.environ)
    settings = Settings.from_env(env_file)
    if dict(os.environ) != before:
        raise AssertionError(
            "Reading backend configuration changed the process environment"
        )
    assert settings.mongo_uri == "mongodb://127.0.0.1:27017/synthetic"
    assert settings.resend_api_key == "test-only-synthetic-key"
    assert settings.web_url == "http://127.0.0.1:3008"


def test_process_env_overrides_file_without_being_replaced(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DARK_WEB_URL=http://127.0.0.1:3008\nMONGODB_URI=mongodb://127.0.0.1:27017/synthetic\n"
    )
    monkeypatch.setenv("DARK_WEB_URL", "http://127.0.0.1:3012")
    monkeypatch.setenv("MONGODB_URI", "")
    settings = Settings.from_env(env_file)
    assert settings.web_url == "http://127.0.0.1:3012"
    assert settings.mongo_uri == ""
    assert os.environ["MONGODB_URI"] == ""


def test_fresh_backend_import_does_not_load_dotenv_into_process_env(tmp_path):
    (tmp_path / ".env").write_text(
        "MONGODB_URI=mongodb://127.0.0.1:27017/synthetic\n"
        "DARK_AUTH_SECRET=synthetic-import-test-secret-1234567890\n"
        "RESEND_API_KEY=test-only-synthetic-key\n"
        "DARK_EMAIL_FROM=login@example.com\n"
        "DARK_EMAIL_PROVIDER=resend\n",
        encoding="utf-8",
    )
    # A subprocess also protects this test from CLI callbacks mutating test-runner env.
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("DARK_", "MONGODB_", "RESEND_", "CLOUDFLARE_"))
    }
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import os; before = dict(os.environ); "
                "from app.main import app; "
                "from app.settings import Settings; config = Settings.from_env(); "
                "unchanged = dict(os.environ) == before; "
                "configured = config.mongo_uri.endswith('/synthetic'); "
                "raise SystemExit(0 if unchanged and configured else 1)"
            ),
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if result.returncode != 0:
        # Never attach captured output or the process environment to an assertion.
        raise AssertionError(
            "Fresh backend import unexpectedly changed environment or failed"
        )
