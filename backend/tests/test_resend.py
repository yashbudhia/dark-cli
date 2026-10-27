import json

import httpx
import mongomock
import pytest
from app.email import CloudflareMailer, EmailDeliveryError, ResendMailer, make_mailer
from app.main import create_app
from app.settings import Settings
from fastapi.testclient import TestClient


def configured(**overrides):
    values = {
        "resend_api_key": "private-test-resend-key",
        "email_from": "login@example.com",
    }
    return Settings(**(values | overrides))


def test_resend_sends_documented_rest_request_and_requires_response_id():
    def handler(request):
        assert (
            request.method == "POST"
            and str(request.url) == "https://api.resend.com/emails"
        )
        assert request.headers["Authorization"] == "Bearer private-test-resend-key"
        assert request.headers["User-Agent"].startswith("dark-cli/")
        body = json.loads(request.content)
        assert body["from"] == "login@example.com"
        assert body["to"] == ["dev@example.com"]
        assert body["subject"] == "12345678 is your Dark sign-in code"
        assert "12345678" in body["text"] and "10 minutes" in body["text"]
        assert set(body) == {"from", "to", "subject", "text"}
        return httpx.Response(200, json={"id": "49a3999c-0ce1-4ea6-ab68-afcd6dc2e794"})

    mailer = ResendMailer(configured(), httpx.MockTransport(handler))
    assert mailer.send_code("dev@example.com", "12345678") is None


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(401, json={"message": "private-provider-message"}),
        httpx.Response(403, json={"message": "private-provider-message"}),
        httpx.Response(429, json={"message": "private-provider-message"}),
        httpx.Response(503, json={"message": "private-provider-message"}),
        httpx.Response(200, content="not-json"),
        httpx.Response(200, json=[]),
        httpx.Response(200, json={}),
        httpx.Response(200, json={"id": None}),
        httpx.Response(200, json={"id": ""}),
        httpx.Response(200, json={"id": " "}),
        httpx.Response(200, json={"id": 123}),
        httpx.Response(200, json={"id": "line\nbreak"}),
        httpx.Response(200, json={"id": "nul\x00character"}),
        httpx.Response(200, json={"id": "x" * 257}),
        httpx.Response(
            200, json={"id": "email-id", "error": "private-provider-message"}
        ),
    ],
)
def test_resend_errors_and_incomplete_responses_never_count_as_sent(response):
    mailer = ResendMailer(configured(), httpx.MockTransport(lambda request: response))
    with pytest.raises(EmailDeliveryError) as failure:
        mailer.send_code("dev@example.com", "12345678")
    assert "private-" not in str(failure.value) and "12345678" not in str(failure.value)


def test_resend_timeout_is_safe_and_does_not_retry_a_send():
    requests = []

    def timeout(request):
        requests.append(request)
        raise httpx.ReadTimeout("private-upstream-context", request=request)

    mailer = ResendMailer(configured(), httpx.MockTransport(timeout))
    with pytest.raises(EmailDeliveryError) as failure:
        mailer.send_code("dev@example.com", "12345678")
    assert len(requests) == 1
    assert "private-" not in str(failure.value)


@pytest.mark.parametrize(
    "settings",
    [
        Settings(email_provider="resend"),
        Settings(email_provider="resend", resend_api_key="private-test-key"),
        Settings(email_provider="resend", email_from="login@example.com"),
    ],
)
def test_incomplete_resend_config_fails_before_network_request(settings):
    def forbidden(request):
        pytest.fail("Missing email credentials must not send an HTTP request")

    assert settings.email_configured is False
    with pytest.raises(EmailDeliveryError, match="not configured"):
        ResendMailer(settings, httpx.MockTransport(forbidden)).send_code(
            "dev@example.com", "12345678"
        )


def test_provider_selection_preserves_explicit_choice_and_cloudflare_compatibility():
    assert configured().selected_email_provider == "resend"
    assert isinstance(make_mailer(configured()), ResendMailer)
    assert configured().email_configured is True

    cloudflare = Settings(
        cloudflare_account_id="account",
        cloudflare_api_token="test-key",
        email_from="login@example.com",
    )
    assert isinstance(make_mailer(cloudflare), CloudflareMailer)
    assert (
        cloudflare.selected_email_provider == "cloudflare"
        and cloudflare.email_configured is True
    )

    explicit_cloudflare = configured(email_provider="cloudflare")
    assert isinstance(make_mailer(explicit_cloudflare), CloudflareMailer)
    assert explicit_cloudflare.email_configured is False

    explicit_resend = Settings(
        email_provider="resend",
        cloudflare_account_id="account",
        cloudflare_api_token="test-key",
        email_from="login@example.com",
    )
    assert isinstance(make_mailer(explicit_resend), ResendMailer)
    assert explicit_resend.email_configured is False


def test_app_factory_and_readiness_use_selected_resend_provider_without_sending():
    config = configured(auth_secret="resend-tests-only-secret-" * 2)
    database = mongomock.MongoClient(tz_aware=True).dark
    with TestClient(create_app(config, database=database)) as client:
        assert isinstance(client.app.state.auth.mailer, ResendMailer)
        response = client.get("/api/auth/readiness")
        assert (
            response.status_code == 200
            and response.json()["checks"]["email_configured"] is True
        )
        assert response.json()["email_delivery_verified"] is False
        assert "private-test-resend-key" not in response.text
    config = configured(auth_secret="resend-tests-only-secret-" * 2, email_from="")
    with TestClient(create_app(config, database=database)) as client:
        assert client.get("/api/auth/readiness").status_code == 503


def test_resend_environment_selection_and_invalid_provider(monkeypatch, tmp_path):
    monkeypatch.setenv("RESEND_API_KEY", " private-test-key ")
    monkeypatch.setenv("DARK_EMAIL_FROM", " login@example.com ")
    monkeypatch.setenv("DARK_EMAIL_PROVIDER", " RESEND ")
    monkeypatch.setenv("MONGODB_URI", "")
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")
    config = Settings.from_env(env_file)
    config.validate()
    assert config.resend_api_key == "private-test-key"
    assert (
        config.selected_email_provider == "resend" and config.email_configured is True
    )
    with pytest.raises(ValueError, match="DARK_EMAIL_PROVIDER"):
        Settings(email_provider="not-supported").validate()
