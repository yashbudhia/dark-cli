import pytest


@pytest.fixture(autouse=True)
def isolate_cli_preferences(monkeypatch, tmp_path):
    monkeypatch.setenv("DARK_CONFIG_DIR", str(tmp_path / "cli-config"))
    monkeypatch.setenv("DARK_SERVER_URL", "")
    empty_environment = tmp_path / "test.env"
    empty_environment.write_text("")
    monkeypatch.setenv("DARK_ENV_FILE", str(empty_environment))
