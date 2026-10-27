import mongomock
import pytest
from app.auth import now
from app.main import create_app
from app.settings import Settings
from fastapi.testclient import TestClient


@pytest.fixture
def api():
    db = mongomock.MongoClient(tz_aware=True).dark
    settings = Settings(auth_secret="reports-test-only-secret-" * 3)
    with TestClient(create_app(settings, database=db)) as client:
        db.users.insert_one(
            {"_id": "owner", "email": "owner@example.com", "created_at": now()}
        )
        token, _ = client.app.state.auth.issue_session("owner", "cli", "Test CLI")
        yield client, db, {"Authorization": f"Bearer {token}"}


def report():
    return {
        "status": "failed",
        "finished_at": "2026-10-26T11:25:43+00:00",
        "window_title": "Disposable fixture",
        "scenario": "Reject negative quantity",
        "assertions": [
            {
                "step": 5,
                "expected_text": "Rejected",
                "observed_text": "Saved quantity: -2",
                "match": "exact",
                "passed": False,
            }
        ],
        "verified_finding": False,
    }


def test_report_import_retry_detail_and_small_list_response(api):
    client, db, headers = api
    path = "/api/runs/import/" + "a" * 64
    first = client.put(path, headers=headers, json=report())
    assert first.status_code == 200, first.text
    result = first.json()
    assert result["kind"] == "desktop" and result["status"] == "failed"
    assert result["desktop_report"]["verified_finding"] is False
    assert (
        result["desktop_report"]["assertions"][0]["observed_text"]
        == "Saved quantity: -2"
    )
    assert client.put(path, headers=headers, json=report()).json()["id"] == result["id"]
    assert db.runs.count_documents({}) == 1
    detail = client.get(f"/api/runs/{result['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["desktop_report"] == result["desktop_report"]
    listing = client.get("/api/runs", headers=headers).json()
    assert listing[0]["id"] == result["id"] and listing[0]["desktop_report"] is None


def test_report_import_requires_login_and_isolates_accounts(api):
    client, db, headers = api
    path = "/api/runs/import/" + "b" * 64
    assert client.put(path, json=report()).status_code in (401, 403)
    result = client.put(path, headers=headers, json=report()).json()
    db.users.insert_one(
        {"_id": "other", "email": "other@example.com", "created_at": now()}
    )
    token, _ = client.app.state.auth.issue_session("other", "cli", "Other CLI")
    other_headers = {"Authorization": f"Bearer {token}"}
    assert (
        client.get(f"/api/runs/{result['id']}", headers=other_headers).status_code
        == 404
    )
    assert client.get("/api/runs", headers=other_headers).json() == []
    # Identical evidence from another account stays a separate owner-scoped record.
    assert client.put(path, headers=other_headers, json=report()).status_code == 200
    assert db.runs.count_documents({}) == 2


@pytest.mark.parametrize(
    "change",
    [
        {"verified_finding": True},
        {"evidence_dir": "C:/private"},
        {"status": "verified"},
        {"finished_at": "yesterday"},
        {"assertions": [{"expected_text": "Ready", "passed": "false"}]},
        {"assertions": [{"expected_text": "Ready", "passed": True}] * 101},
    ],
)
def test_report_schema_rejects_extra_content_and_false_verification(api, change):
    client, _db, headers = api
    body = {**report(), **change}
    assert (
        client.put(
            "/api/runs/import/" + "c" * 64, headers=headers, json=body
        ).status_code
        == 422
    )


def test_import_rejects_arbitrary_identifiers(api):
    client, _db, headers = api
    assert (
        client.put(
            "/api/runs/import/arbitrary-id", headers=headers, json=report()
        ).status_code
        == 422
    )
