import json

import httpx
import pytest
from typer.testing import CliRunner

from dark_cli import runs
from dark_cli.auth import LoginError
from dark_cli.cli import app


@pytest.fixture
def directory(tmp_path):
    body = {
        "status": "failed",
        "finished_at": "2026-10-26T11:25:43+00:00",
        "verified_finding": True,
        "evidence_dir": "C:/private/path",
        "window": {"title": "Disposable fixture", "handle": "session-specific-handle"},
        "scenario": "Reject negative quantity",
        "snapshot": {"secret": "raw-snapshot"},
        "assertions": [
            {
                "expected_text": "Rejected",
                "passed": False,
                "step": 5,
                "match": "exact",
                "observed": {
                    "text": "Saved quantity: -2",
                    "internal_metadata": "private-tool-metadata",
                },
            }
        ],
    }
    (tmp_path / "report.json").write_text(json.dumps(body), encoding="utf-8")
    (tmp_path / "events.jsonl").write_text("RAW-EVENT-SECRET", encoding="utf-8")
    (tmp_path / "snapshot.json").write_text("RAW-SNAPSHOT-SECRET", encoding="utf-8")
    return tmp_path


def test_upload_projection_excludes_raw_evidence_and_is_deterministic(directory):
    fingerprint, payload = runs.prepare_upload(directory)
    assert runs.prepare_upload(directory) == (fingerprint, payload)
    assert len(fingerprint) == 64
    assert payload["verified_finding"] is False
    assert payload["assertions"][0]["observed_text"] == "Saved quantity: -2"
    serialized = json.dumps(payload)
    for private in (
        "C:/private",
        "raw-snapshot",
        "internal_metadata",
        "session-specific-handle",
        "RAW-EVENT",
    ):
        assert private not in serialized


def test_dry_run_never_uses_network_or_credentials(directory, monkeypatch):
    def forbidden(*args):
        raise AssertionError("Dry run must stay offline")

    monkeypatch.setattr(runs, "AccountClient", forbidden)
    result = CliRunner().invoke(app, ["runs", "upload", str(directory), "--dry-run"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["assertions"][0]["passed"] is False


def test_upload_sends_stable_put_and_opens_only_its_own_report(directory, monkeypatch):
    fingerprint, payload = runs.prepare_upload(directory)
    opened = []

    def handler(request):
        assert request.method == "PUT"
        assert request.url.path == f"/api/runs/import/{fingerprint}"
        assert request.headers["Authorization"] == "Bearer test-token"
        assert json.loads(request.content) == payload
        return httpx.Response(200, json={"id": f"desktop_{fingerprint}"})

    client_class = runs.AccountClient
    monkeypatch.setattr(
        runs, "AccountClient", lambda server: client_class(server, httpx.MockTransport(handler))
    )
    monkeypatch.setattr(runs.Credentials, "get", lambda self: "test-token")
    monkeypatch.setattr(runs.webbrowser, "open", opened.append)
    result = CliRunner().invoke(
        app, ["runs", "upload", str(directory), "--server", "https://dark.example", "--open"]
    )
    assert result.exit_code == 0, result.output
    assert opened == [f"https://dark.example/dashboard/runs/desktop_{fingerprint}"]
    assert "test-token" not in result.output


def test_upload_missing_login_does_not_send_report(directory, monkeypatch):
    monkeypatch.setattr(runs.Credentials, "get", lambda self: None)
    monkeypatch.setattr(
        runs.AccountClient,
        "request",
        lambda *args, **kwargs: pytest.fail("Unexpected network call"),
    )
    result = CliRunner().invoke(app, ["runs", "upload", str(directory)])
    assert result.exit_code == 1 and "dark login" in result.output


def test_upload_size_and_malformed_report_are_rejected_locally(directory):
    (directory / "report.json").write_text("x" * (runs.MAX_REPORT_BYTES + 1))
    with pytest.raises(LoginError, match="256 KiB"):
        runs.prepare_upload(directory)
    (directory / "report.json").write_text('{"status":"verified"}')
    with pytest.raises(LoginError, match="valid completed"):
        runs.prepare_upload(directory)


def test_upload_errors_do_not_open_the_browser(directory, monkeypatch):
    client_class = runs.AccountClient
    transport = httpx.MockTransport(lambda request: httpx.Response(401))
    monkeypatch.setattr(runs, "AccountClient", lambda server: client_class(server, transport))
    monkeypatch.setattr(runs.Credentials, "get", lambda self: "expired-token")
    monkeypatch.setattr(
        runs.webbrowser, "open", lambda *args: pytest.fail("Unexpected browser opening")
    )
    result = CliRunner().invoke(app, ["runs", "upload", str(directory), "--open"])
    assert result.exit_code == 1 and "expired or revoked" in result.output


def test_runs_list_show_and_empty_states(monkeypatch):
    record = {
        "id": "desktop_test",
        "target": "Fixture",
        "goal": "Read Ready",
        "status": "passed",
        "kind": "desktop",
        "desktop_report": {"verified_finding": False},
    }
    client_class = runs.AccountClient

    def handler(request):
        assert request.headers["Authorization"] == "Bearer test-token"
        return httpx.Response(200, json=[record] if request.url.path == "/api/runs" else record)

    monkeypatch.setattr(
        runs, "AccountClient", lambda server: client_class(server, httpx.MockTransport(handler))
    )
    monkeypatch.setattr(runs.Credentials, "get", lambda self: "test-token")
    runner = CliRunner()
    listing = runner.invoke(app, ["runs", "list"])
    assert listing.exit_code == 0 and "desktop_test" in listing.output
    listing_json = runner.invoke(app, ["runs", "list", "--json"])
    assert json.loads(listing_json.output)[0]["id"] == "desktop_test"
    detail = runner.invoke(app, ["runs", "show", "desktop_test"])
    assert (
        detail.exit_code == 0
        and json.loads(detail.output)["desktop_report"]["verified_finding"] is False
    )
    bad_id = runner.invoke(app, ["runs", "show", "../auth/me"])
    assert bad_id.exit_code == 1 and "Invalid run ID" in bad_id.output


@pytest.mark.parametrize("body", [{}, [None], [{"id": "bad/id"}], [{"id": "missing_fields"}]])
def test_malformed_run_list_is_actionable(monkeypatch, body):
    client_class = runs.AccountClient
    monkeypatch.setattr(
        runs,
        "AccountClient",
        lambda server: client_class(
            server, httpx.MockTransport(lambda request: httpx.Response(200, json=body))
        ),
    )
    monkeypatch.setattr(runs.Credentials, "get", lambda self: "test-token")
    result = CliRunner().invoke(app, ["runs", "list"])
    assert result.exit_code == 1
    assert "invalid" in result.output and "Traceback" not in result.output
