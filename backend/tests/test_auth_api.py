from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import httpx
import mongomock
import pytest
from app.auth import AuthError, now
from app.email import CloudflareMailer, EmailDeliveryError
from app.main import create_app
from app.settings import Settings
from fastapi.testclient import TestClient

ORIGIN = "http://127.0.0.1:3000"
WEB = {"Origin": ORIGIN}


class CaptureMail:
    def __init__(self):
        self.sent = []

    def send_code(self, email, code):
        self.sent.append((email, code))


@pytest.fixture
def system():
    db = mongomock.MongoClient(tz_aware=True).dark
    mail = CaptureMail()
    config = Settings(auth_secret="test-only-secret-" * 3, web_url=ORIGIN)
    app = create_app(config, database=db, mailer=mail)
    with TestClient(app) as client:
        yield client, db, mail, app.state.auth


def sign_in(client, mail, email="dev@example.com"):
    response = client.post(
        "/api/auth/email/request", headers=WEB, json={"email": email}
    )
    assert response.status_code == 200, response.text
    challenge = response.json()["challenge_id"]
    response = client.post(
        "/api/auth/email/verify",
        headers=WEB,
        json={
            "challenge_id": challenge,
            "code": mail.sent[-1][1],
        },
    )
    assert response.status_code == 200, response.text
    return response, challenge


def pair(client, db, *, approve=True):
    response = client.post("/api/auth/device/code", json={"name": "Test laptop"})
    assert response.status_code == 200, response.text
    pairing = response.json()
    assert (
        client.get(
            "/api/auth/device", params={"user_code": pairing["user_code"]}
        ).status_code
        == 200
    )
    response = client.post(
        "/api/auth/device/decision",
        headers=WEB,
        json={
            "user_code": pairing["user_code"],
            "approve": approve,
        },
    )
    assert response.status_code == 204, response.text
    return pairing


def test_signup_cookie_single_use_and_hashes(system):
    client, db, mail, _auth = system
    response, challenge = sign_in(client, mail, "DEV@example.com")
    assert response.json()["user"]["email"] == "dev@example.com"
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Path=/api" in cookie
    assert "access_token" not in response.text
    assert client.get("/api/auth/me").json()["session"]["kind"] == "web"
    token = client.cookies.get("dark_session")
    assert token not in str(list(db.sessions.find()))
    replay = client.post(
        "/api/auth/email/verify",
        headers=WEB,
        json={"challenge_id": challenge, "code": mail.sent[-1][1]},
    )
    assert replay.status_code == 400
    assert db.users.count_documents({}) == 1


def test_email_code_lockout_expiry_and_throttle(system):
    client, db, mail, _auth = system
    challenge = client.post(
        "/api/auth/email/request", headers=WEB, json={"email": "dev@example.com"}
    ).json()["challenge_id"]
    assert mail.sent[-1][1] not in str(list(db.email_codes.find()))
    assert (
        client.post(
            "/api/auth/email/request", headers=WEB, json={"email": "dev@example.com"}
        ).status_code
        == 429
    )
    actual = mail.sent[-1][1]
    wrong = "11111111" if actual != "11111111" else "22222222"
    for _ in range(5):
        assert (
            client.post(
                "/api/auth/email/verify",
                headers=WEB,
                json={"challenge_id": challenge, "code": wrong},
            ).status_code
            == 400
        )
    assert (
        client.post(
            "/api/auth/email/verify",
            headers=WEB,
            json={"challenge_id": challenge, "code": actual},
        ).status_code
        == 400
    )
    response = client.post(
        "/api/auth/email/request", headers=WEB, json={"email": "other@example.com"}
    )
    challenge = response.json()["challenge_id"]
    db.email_codes.update_many(
        {}, {"$set": {"expires_at": now() - timedelta(seconds=1)}}
    )
    assert (
        client.post(
            "/api/auth/email/verify",
            headers=WEB,
            json={"challenge_id": challenge, "code": mail.sent[-1][1]},
        ).status_code
        == 400
    )


def test_concurrent_email_verification_only_issues_one_session(system):
    _client, db, mail, auth = system
    challenge = auth.request_email("race@example.com", "one")["challenge_id"]

    def verify(_):
        try:
            return auth.verify_email(challenge, mail.sent[-1][1], "one")
        except AuthError:
            return None

    with ThreadPoolExecutor(max_workers=6) as executor:
        assert sum(result is not None for result in executor.map(verify, range(6))) == 1
    assert db.sessions.count_documents({}) == 1


def test_csrf_email_validation_and_no_unconfigured_fallback(system):
    client, _db, _mail, _auth = system
    for headers in ({}, {"Origin": "https://evil.example"}):
        assert (
            client.post(
                "/api/auth/email/request",
                headers=headers,
                json={"email": "dev@example.com"},
            ).status_code
            == 403
        )
    assert (
        client.post(
            "/api/auth/email/request", headers=WEB, json={"email": "not-email"}
        ).status_code
        == 422
    )
    with TestClient(create_app(Settings())) as unconfigured:
        assert unconfigured.get("/health").json()["auth_configured"] is False
        assert (
            unconfigured.post(
                "/api/auth/email/request",
                headers=WEB,
                json={"email": "dev@example.com"},
            ).status_code
            == 503
        )
        assert unconfigured.get("/api/runs").status_code == 503


def test_device_pending_polling_approval_and_replay(system):
    client, db, mail, _auth = system
    sign_in(client, mail)
    pairing = client.post("/api/auth/device/code", json={"name": "My laptop"}).json()
    assert pairing["verification_uri_complete"].startswith(ORIGIN + "/connect?")
    body = {"device_code": pairing["device_code"]}
    assert (
        client.post("/api/auth/device/token", json=body).json()["error"]
        == "authorization_pending"
    )
    assert (
        client.post("/api/auth/device/token", json=body).json()["error"] == "slow_down"
    )
    assert (
        client.post(
            "/api/auth/device/decision",
            json={"user_code": pairing["user_code"], "approve": True},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/auth/device/decision",
            headers=WEB,
            json={"user_code": pairing["user_code"], "approve": True},
        ).status_code
        == 204
    )
    db.device_codes.update_many(
        {}, {"$set": {"last_poll_at": now() - timedelta(seconds=6)}}
    )
    token = client.post("/api/auth/device/token", json=body).json()["access_token"]
    assert (
        client.post("/api/auth/device/token", json=body).json()["access_token"] == token
    )
    assert db.sessions.count_documents({"kind": "cli"}) == 1
    cli_headers = {"Authorization": f"Bearer {token}"}
    assert (
        client.get("/api/auth/me", headers=cli_headers).json()["session"]["kind"]
        == "cli"
    )
    assert client.get("/api/auth/devices").json()[0]["name"] == "My laptop"
    assert pairing["device_code"] not in str(list(db.device_codes.find()))
    # A CLI credential cannot approve another CLI or inspect browser device management.
    client.cookies.clear()
    assert client.get("/api/auth/devices", headers=cli_headers).status_code == 401


def test_recovered_pairing_cannot_resurrect_a_revoked_session(system):
    client, db, mail, _auth = system
    sign_in(client, mail)
    pairing = pair(client, db)
    body = {"device_code": pairing["device_code"]}
    token = client.post("/api/auth/device/token", json=body).json()["access_token"]
    # Simulate a lost first response: retrying returns the same session, not a new one.
    assert (
        client.post("/api/auth/device/token", json=body).json()["access_token"] == token
    )
    device = client.get("/api/auth/devices").json()[0]
    assert (
        client.delete(f"/api/auth/devices/{device['id']}", headers=WEB).status_code
        == 204
    )
    assert (
        client.post("/api/auth/device/token", json=body).json()["error"]
        == "expired_token"
    )
    assert db.sessions.count_documents({"kind": "cli"}) == 0
    assert token not in str(list(db.device_codes.find()))


def test_fast_polling_is_negotiated_without_changing_older_clients(system):
    client, _db, _mail, _auth = system
    old = client.post("/api/auth/device/code", json={"name": "old"}).json()
    new = client.post(
        "/api/auth/device/code", json={"name": "new", "poll_interval": 2}
    ).json()
    assert old["interval"] == 5 and new["interval"] == 2
    body = {"device_code": new["device_code"]}
    assert (
        client.post("/api/auth/device/token", json=body).json()["error"]
        == "authorization_pending"
    )
    response = client.post("/api/auth/device/token", json=body)
    assert (
        response.json()["error"] == "slow_down"
        and response.headers["Retry-After"] == "2"
    )


@pytest.mark.parametrize("approved", [False, True])
def test_denied_or_expired_pairing_never_issues_a_token(system, approved):
    client, db, mail, _auth = system
    sign_in(client, mail)
    pairing = pair(client, db, approve=approved)
    if approved:
        db.device_codes.update_many(
            {}, {"$set": {"expires_at": now() - timedelta(seconds=1)}}
        )
    response = client.post(
        "/api/auth/device/token", json={"device_code": pairing["device_code"]}
    )
    assert response.json()["error"] == (
        "expired_token" if approved else "access_denied"
    )
    assert db.sessions.count_documents({"kind": "cli"}) == 0


def test_revocation_owner_isolation_and_run_persistence(system):
    client, db, mail, auth = system
    sign_in(client, mail)
    pairing = pair(client, db)
    token = client.post(
        "/api/auth/device/token", json={"device_code": pairing["device_code"]}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    run = client.post(
        "/api/runs", headers=headers, json={"target": "fixture", "goal": "Read Ready"}
    ).json()
    assert client.get("/api/runs").json()[0]["id"] == run["id"]
    assert (
        client.post(
            f"/api/runs/{run['id']}/findings",
            headers=headers,
            json={"run_id": run["id"], "title": "Test finding"},
        ).status_code
        == 201
    )
    device = client.get("/api/auth/devices").json()[0]
    assert (
        client.delete(f"/api/auth/devices/{device['id']}", headers=WEB).status_code
        == 204
    )
    assert client.get("/api/auth/me", headers=headers).status_code == 401
    # A new app process reads persisted sessions and runs from the same Mongo database.
    with TestClient(create_app(auth.settings, database=db, mailer=mail)) as restarted:
        restarted.cookies.update(client.cookies)
        assert restarted.get("/api/runs").json()[0]["id"] == run["id"]
    client.cookies.clear()
    sign_in(client, mail, "other@example.com")
    assert client.get("/api/runs").json() == []
    for suffix in ("", "/findings", "/refusals"):
        assert client.get(f"/api/runs/{run['id']}{suffix}").status_code == 404
    assert (
        client.delete(f"/api/auth/devices/{device['id']}", headers=WEB).status_code
        == 404
    )


def test_expired_sessions_and_logout(system):
    client, db, mail, _auth = system
    sign_in(client, mail)
    assert client.post("/api/auth/logout").status_code == 403
    assert client.post("/api/auth/logout", headers=WEB).status_code == 204
    assert client.get("/api/auth/me").status_code == 401
    sign_in(client, mail, "other@example.com")
    db.sessions.update_many({}, {"$set": {"expires_at": now() - timedelta(seconds=1)}})
    assert client.get("/api/auth/me").status_code == 401


def test_email_failure_removes_challenge(system):
    client, db, _mail, auth = system

    class FailingMail:
        def send_code(self, email, code):
            raise EmailDeliveryError("Delivery unavailable.")

    auth.mailer = FailingMail()
    response = client.post(
        "/api/auth/email/request", headers=WEB, json={"email": "dev@example.com"}
    )
    assert response.status_code == 503
    assert db.email_codes.count_documents({}) == 0


@pytest.mark.parametrize("mode", ["delivered", "queued", "bounce", "unauthorized"])
def test_cloudflare_rest_contract(mode):
    import json

    config = Settings(
        cloudflare_account_id="account",
        cloudflare_api_token="test-token",
        email_from="login@example.com",
    )

    def handler(request):
        assert (
            str(request.url)
            == "https://api.cloudflare.com/client/v4/accounts/account/email/sending/send"
        )
        assert request.headers["authorization"] == "Bearer test-token"
        body = json.loads(request.content)
        assert body["from"] == "login@example.com" and body["to"] == ["dev@example.com"]
        assert "12345678" in body["text"]
        if mode == "unauthorized":
            return httpx.Response(403, json={"success": False})
        return httpx.Response(
            200,
            json={
                "success": True,
                "result": {
                    "delivered": ["dev@example.com"] if mode == "delivered" else [],
                    "queued": ["dev@example.com"] if mode == "queued" else [],
                    "permanent_bounces": ["dev@example.com"]
                    if mode == "bounce"
                    else [],
                },
            },
        )

    mailer = CloudflareMailer(config, httpx.MockTransport(handler))
    if mode in ("bounce", "unauthorized"):
        with pytest.raises(EmailDeliveryError):
            mailer.send_code("dev@example.com", "12345678")
    else:
        mailer.send_code("dev@example.com", "12345678")


def test_https_cookie_and_configuration(system):
    _client, db, mail, _auth = system
    config = Settings(
        auth_secret="test-only-secret-" * 3, web_url="https://dark.example"
    )
    with TestClient(
        create_app(config, database=db, mailer=mail), base_url="https://dark.example"
    ) as secure:
        origin = {"Origin": config.web_url}
        challenge = secure.post(
            "/api/auth/email/request",
            headers=origin,
            json={"email": "secure@example.com"},
        ).json()["challenge_id"]
        response = secure.post(
            "/api/auth/email/verify",
            headers=origin,
            json={"challenge_id": challenge, "code": mail.sent[-1][1]},
        )
        assert "Secure" in response.headers["set-cookie"]
        assert response.headers["cache-control"] == "no-store"
    with pytest.raises(ValueError):
        Settings(web_url="http://public.example").validate()
