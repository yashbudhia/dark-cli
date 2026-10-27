from datetime import timedelta

import httpx
import mongomock
import pytest
from app.auth import AuthError, AuthService, now
from app.email import CloudflareMailer, EmailDeliveryError
from app.main import create_app
from app.settings import Settings
from fastapi.testclient import TestClient
from pymongo.errors import ConnectionFailure, DuplicateKeyError


class CaptureMail:
    def __init__(self):
        self.code = ""

    def send_code(self, email, code):
        self.code = code


@pytest.fixture
def service():
    database = mongomock.MongoClient(tz_aware=True).dark
    settings = Settings(auth_secret="test-only-secret-for-readiness-" * 2)
    mailer = CaptureMail()
    auth = AuthService(database, settings, mailer)
    auth.indexes()
    return auth, mailer


def test_readiness_without_credentials_is_explicit_and_safe():
    with TestClient(create_app(Settings())) as client:
        response = client.get("/api/auth/readiness")
        assert response.status_code == 503
        assert response.json() == {
            "ready": False,
            "checks": {
                "database_configured": False,
                "auth_secret_configured": False,
                "email_configured": False,
                "mongodb_reachable": False,
            },
            "email_delivery_verified": False,
        }
        assert response.headers["cache-control"] == "no-store"


def test_readiness_pings_mongo_without_sending_mail_or_exposing_settings(
    service, monkeypatch
):
    auth, _mailer = service
    settings = Settings(
        auth_secret="private-auth-secret-" * 3,
        cloudflare_account_id="private-account",
        cloudflare_api_token="private-cloudflare-token",
        email_from="login@example.com",
    )
    with TestClient(create_app(settings, database=auth.db)) as client:
        response = client.get("/api/auth/readiness")
        assert response.status_code == 200 and response.json()["ready"] is True
        assert response.json()["email_delivery_verified"] is False
        assert (
            "private-" not in response.text and "login@example.com" not in response.text
        )

        def unavailable(*args, **kwargs):
            raise ConnectionFailure(
                "mongodb://private-user:private-password@private-host"
            )

        monkeypatch.setattr(auth.db, "command", unavailable)
        response = client.get("/api/auth/readiness")
        assert response.status_code == 503
        assert response.json()["checks"]["mongodb_reachable"] is False
        assert "private-" not in response.text


def test_lost_user_upsert_race_reuses_the_existing_account(service, monkeypatch):
    auth, mailer = service
    challenge = auth.request_email("race@example.com", "test")["challenge_id"]

    def concurrent_insert(query, update, **kwargs):
        auth.db.users.insert_one(
            {"_id": "existing", "email": query["email"], "created_at": now()}
        )
        raise DuplicateKeyError("Unique email inserted by another request")

    monkeypatch.setattr(auth.db.users, "find_one_and_update", concurrent_insert)
    user, token = auth.verify_email(challenge, mailer.code, "test")
    assert user["id"] == "existing"
    assert auth.authenticate(token)[0]["_id"] == "existing"
    assert auth.db.users.count_documents({}) == 1


def test_lost_rate_limit_upsert_race_still_counts_both_requests(service, monkeypatch):
    auth, _mailer = service
    original = auth.db.auth_limits.find_one_and_update

    def concurrent_insert(query, update, **kwargs):
        if kwargs.get("upsert"):
            auth.db.auth_limits.insert_one(
                {
                    "_id": query["_id"],
                    "count": 1,
                    "expires_at": now() + timedelta(minutes=2),
                }
            )
            raise DuplicateKeyError("Bucket inserted by another request")
        return original(query, update, **kwargs)

    monkeypatch.setattr(auth.db.auth_limits, "find_one_and_update", concurrent_insert)
    with pytest.raises(AuthError) as failure:
        auth.limit("shared", 1, 60)
    assert failure.value.status == 429
    assert 1 <= failure.value.retry_after <= 60
    assert auth.db.auth_limits.find_one()["count"] == 2


def test_retry_after_headers_match_actual_cooldown(service, monkeypatch):
    auth, mailer = service
    monkeypatch.setattr("app.auth.time.time", lambda: 100)
    with TestClient(
        create_app(auth.settings, database=auth.db, mailer=mailer)
    ) as client:
        origin = {"Origin": auth.settings.web_url}
        body = {"email": "cooldown@example.com"}
        assert (
            client.post(
                "/api/auth/email/request", headers=origin, json=body
            ).status_code
            == 200
        )
        limited = client.post("/api/auth/email/request", headers=origin, json=body)
        assert limited.status_code == 429 and limited.headers["retry-after"] == "20"
        pairing = client.post("/api/auth/device/code", json={"name": "Test"}).json()
        body = {"device_code": pairing["device_code"]}
        assert (
            client.post("/api/auth/device/token", json=body).json()["error"]
            == "authorization_pending"
        )
        response = client.post("/api/auth/device/token", json=body)
        assert (
            response.json()["error"] == "slow_down"
            and response.headers["retry-after"] == "5"
        )


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"success": True, "result": None},
        {"success": True, "result": {"delivered": "dev@example.com"}},
        {"success": "true", "result": {"delivered": ["dev@example.com"]}},
        {"success": True, "result": {"queued": None}},
        {
            "success": True,
            "result": {
                "delivered": ["dev@example.com"],
                "permanent_bounces": ["dev@example.com"],
            },
        },
    ],
)
def test_malformed_or_contradictory_delivery_response_never_counts_as_sent(payload):
    settings = Settings(
        cloudflare_account_id="account",
        cloudflare_api_token="private-token",
        email_from="login@example.com",
    )
    mailer = CloudflareMailer(
        settings, httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    )
    with pytest.raises(EmailDeliveryError):
        mailer.send_code("dev@example.com", "12345678")


@pytest.mark.parametrize(
    "values, field",
    [
        ({"web_url": "https://dark.example:wrong"}, "DARK_WEB_URL"),
        ({"web_url": "https://dark.example/path"}, "DARK_WEB_URL"),
        ({"web_url": "https://dark.example:0"}, "DARK_WEB_URL"),
        ({"web_url": "https://dark.ex ample"}, "DARK_WEB_URL"),
        ({"auth_secret": "private-short-secret"}, "DARK_AUTH_SECRET"),
        ({"mongo_uri": "https://private-user:private-password@host"}, "MONGODB_URI"),
        ({"mongo_database": "invalid/database"}, "MONGODB_DATABASE"),
        ({"cloudflare_account_id": "private/account"}, "CLOUDFLARE_ACCOUNT_ID"),
        ({"email_from": "private-invalid-email"}, "DARK_EMAIL_FROM"),
    ],
)
def test_invalid_configuration_names_fields_without_echoing_secrets(values, field):
    with pytest.raises(ValueError) as failure:
        Settings(**values).validate()
    assert field in str(failure.value) and "private-" not in str(failure.value)


def test_environment_values_are_trimmed(monkeypatch, tmp_path):
    monkeypatch.setenv("MONGODB_URI", " mongodb://127.0.0.1:27017 \n")
    monkeypatch.setenv("DARK_AUTH_SECRET", " " + "test-secret-" * 4 + " ")
    monkeypatch.setenv("DARK_WEB_URL", " http://127.0.0.1:3000/ ")
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")
    config = Settings.from_env(env_file)
    config.validate()
    assert config.mongo_uri == "mongodb://127.0.0.1:27017"
    assert config.auth_secret == "test-secret-" * 4
    assert config.web_url == "http://127.0.0.1:3000"


def test_device_request_rejects_empty_label_and_non_boolean_decision(service):
    auth, _mailer = service
    with TestClient(create_app(auth.settings, database=auth.db)) as client:
        assert (
            client.post("/api/auth/device/code", json={"name": "  "}).status_code == 422
        )
        auth.db.users.insert_one(
            {"_id": "user", "email": "user@example.com", "created_at": now()}
        )
        token, _ = auth.issue_session("user", "web", "Browser")
        client.cookies.set("dark_session", token, path="/api")
        result = client.post(
            "/api/auth/device/decision",
            headers={"Origin": auth.settings.web_url},
            json={"user_code": "ABCD-EFGH", "approve": "true"},
        )
        assert result.status_code == 422
