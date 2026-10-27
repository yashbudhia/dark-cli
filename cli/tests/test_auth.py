import json

import httpx
import pytest
from keyring.errors import NoKeyringError
from typer.testing import CliRunner

from dark_cli import auth
from dark_cli.cli import app


class Clock:
    def __init__(self):
        self.value = 0
        self.sleeps = []

    def now(self):
        return self.value

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.value += seconds


def test_device_login_pending_slow_down_and_success_never_prints_token():
    clock = Clock()
    opened, messages, polls = [], [], []
    token = "test-session-" * 5
    device_secret = "test-device-" * 5

    def handler(request):
        if request.url.path.endswith("/code"):
            return httpx.Response(
                200,
                json={
                    "device_code": device_secret,
                    "user_code": "ABCD-EFGH",
                    "interval": 5,
                    "expires_in": 600,
                    "verification_uri_complete": "https://dark.example/connect?code=ABCD-EFGH",
                },
            )
        assert json.loads(request.content)["device_code"] == device_secret
        polls.append(clock.now())
        if len(polls) < 3:
            return httpx.Response(
                400, json={"error": "authorization_pending" if len(polls) == 1 else "slow_down"}
            )
        return httpx.Response(200, json={"access_token": token})

    client = auth.AccountClient("https://dark.example", httpx.MockTransport(handler))
    try:
        assert (
            client.login(
                open_browser=opened.append,
                notify=messages.append,
                sleep=clock.sleep,
                clock=clock.now,
            )
            == token
        )
        assert polls == [5, 10, 20]
        assert len(opened) == 1
        assert "ABCD-EFGH" in messages[0]
        assert token not in str(messages) and device_secret not in str(messages)
    finally:
        client.close()


@pytest.mark.parametrize("error", ["access_denied", "expired_token"])
def test_cli_handles_denial_and_expiration(error):
    clock = Clock()

    def handler(request):
        if request.url.path.endswith("/code"):
            return httpx.Response(
                200,
                json={
                    "device_code": "device" * 8,
                    "user_code": "ABCD-EFGH",
                    "interval": 5,
                    "expires_in": 600,
                    "verification_uri_complete": "https://dark.example/connect?code=ABCD-EFGH",
                },
            )
        return httpx.Response(400, json={"error": error})

    client = auth.AccountClient("https://dark.example", httpx.MockTransport(handler))
    with pytest.raises(auth.LoginError, match="declined|expired"):
        client.login(no_browser=True, notify=lambda _: None, sleep=clock.sleep, clock=clock.now)
    client.close()


def test_cli_refuses_verification_url_on_another_origin():
    opened = []
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "device_code": "device" * 8,
                "user_code": "ABCD-EFGH",
                "interval": 5,
                "expires_in": 600,
                "verification_uri_complete": "https://evil.example/connect",
            },
        )
    )
    client = auth.AccountClient("https://dark.example", transport)
    with pytest.raises(auth.LoginError, match="invalid pairing"):
        client.login(open_browser=opened.append)
    assert not opened
    client.close()


@pytest.mark.parametrize(
    "server",
    [
        "http://remote.example",
        "https://user:secret@dark.example",
        "https://dark.example/path",
        "javascript:alert(1)",
    ],
)
def test_server_requires_https_origin_except_loopback(server):
    with pytest.raises(auth.LoginError):
        auth.server_url(server)


@pytest.fixture
def credential_store(monkeypatch):
    values = {}
    native = type(
        "TestNativeVault",
        (),
        {
            "__module__": "keyring.backends.Windows",
            "priority": 1,
            "get_password": lambda self, service, user: values.get((service, user)),
            "set_password": lambda self, service, user, token: values.__setitem__(
                (service, user), token
            ),
            "delete_password": lambda self, service, user: values.pop((service, user)),
        },
    )()
    monkeypatch.setattr(auth.keyring, "get_keyring", lambda: native)
    return values


def test_root_login_whoami_logout_and_credential_scope(monkeypatch, credential_store):
    token = "session" * 8
    revoked = []

    def handler(request):
        assert request.headers["Authorization"] == f"Bearer {token}"
        if request.url.path.endswith("/logout"):
            revoked.append(True)
            return httpx.Response(204)
        return httpx.Response(200, json={"user": {"email": "dev@example.com"}})

    client_class = auth.AccountClient
    monkeypatch.setattr(
        auth, "AccountClient", lambda server: client_class(server, httpx.MockTransport(handler))
    )
    monkeypatch.setattr(client_class, "login", lambda self, **kwargs: token)
    runner = CliRunner()
    result = runner.invoke(app, ["login", "--server", "https://dark.example", "--no-browser"])
    assert result.exit_code == 0, result.output
    assert token not in result.output
    assert credential_store[("dark-cli:https://dark.example", "session")] == token
    assert runner.invoke(app, ["whoami", "--server", "https://dark.example"]).output.startswith(
        "dev@example.com"
    )
    assert runner.invoke(app, ["whoami", "--server", "https://other.example"]).exit_code == 1
    assert runner.invoke(app, ["logout", "--server", "https://dark.example"]).exit_code == 0
    assert revoked == [True] and not credential_store


def test_logout_network_failure_keeps_credential_for_retry(monkeypatch, credential_store):
    token = "session" * 8
    credential_store[("dark-cli:https://dark.example", "session")] = token

    def handler(request):
        raise httpx.ConnectError("offline")

    client_class = auth.AccountClient
    monkeypatch.setattr(
        auth, "AccountClient", lambda server: client_class(server, httpx.MockTransport(handler))
    )
    runner = CliRunner()
    assert runner.invoke(app, ["logout", "--server", "https://dark.example"]).exit_code == 1
    assert credential_store
    assert (
        runner.invoke(app, ["logout", "--server", "https://dark.example", "--local-only"]).exit_code
        == 0
    )
    assert not credential_store


def test_keyring_unavailable_fails_without_plaintext_fallback(monkeypatch):
    def unavailable(*args):
        raise NoKeyringError("No keyring")

    native = type(
        "LockedNativeVault",
        (),
        {
            "__module__": "keyring.backends.Windows",
            "priority": 1,
            "get_password": unavailable,
        },
    )()
    monkeypatch.setattr(auth.keyring, "get_keyring", lambda: native)
    with pytest.raises(auth.LoginError, match="credential store"):
        auth.Credentials("https://dark.example").get()
    plaintext = type("PlaintextKeyring", (), {"priority": 1, "__module__": "keyrings.alt.file"})()
    monkeypatch.setattr(auth.keyring, "get_keyring", lambda: plaintext)
    with pytest.raises(auth.LoginError, match="keyring"):
        auth.Credentials("https://dark.example").get()


@pytest.mark.parametrize("value", [[], None, "not-an-object", 123])
def test_non_object_json_is_rejected_without_attribute_errors(value):
    with pytest.raises(auth.LoginError, match="invalid response"):
        auth.AccountClient.require_success(httpx.Response(200, json=value))


@pytest.mark.parametrize(
    "server",
    [
        "https://dark.example:invalid",
        "https://dark.example:0",
        "https://dark.example\n",
        "https://[bad",
    ],
)
def test_malformed_origins_are_login_errors(server):
    with pytest.raises(auth.LoginError):
        auth.server_url(server)
    assert auth.server_url("https://DARK.EXAMPLE:443/") == "https://dark.example"


def test_native_backend_is_selected_inside_a_chainer(monkeypatch):
    native = type("NativeVault", (), {"__module__": "keyring.backends.Windows", "priority": 1})()
    plaintext = type("Plaintext", (), {"__module__": "keyrings.alt.file", "priority": 10})()
    chainer = type(
        "ChainerBackend",
        (),
        {"__module__": "keyring.backends.chainer", "backends": [plaintext, native]},
    )()
    monkeypatch.setattr(auth.keyring, "get_keyring", lambda: chainer)
    assert auth.Credentials.backend() is native
    chainer.backends = [plaintext]
    with pytest.raises(auth.LoginError, match="native keyring"):
        auth.Credentials.backend()


def test_whoami_handles_missing_account_without_traceback(monkeypatch, credential_store):
    credential_store[("dark-cli:https://dark.example", "session")] = "session" * 8
    client_class = auth.AccountClient
    monkeypatch.setattr(
        auth,
        "AccountClient",
        lambda server: client_class(
            server, httpx.MockTransport(lambda request: httpx.Response(200, json={"user": None}))
        ),
    )
    result = CliRunner().invoke(app, ["whoami", "--server", "https://dark.example"])
    assert result.exit_code == 1 and "invalid account" in result.output


def test_custom_server_is_remembered_after_successful_login(monkeypatch, credential_store):
    client_class = auth.AccountClient
    monkeypatch.setattr(client_class, "login", lambda self, **kwargs: "session" * 8)
    runner = CliRunner()
    assert (
        runner.invoke(
            app, ["login", "--server", "https://custom.example", "--no-browser"]
        ).exit_code
        == 0
    )
    client = auth.AccountClient(None)
    try:
        assert client.server == "https://custom.example"
    finally:
        client.close()


def test_cancelled_login_does_not_save_credentials(monkeypatch, credential_store):
    def cancelled(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(auth.AccountClient, "login", cancelled)
    result = CliRunner().invoke(app, ["login", "--server", "https://dark.example", "--no-browser"])
    assert result.exit_code == 130 and "cancelled" in result.output
    assert not credential_store


def test_storage_failure_revokes_new_token(monkeypatch, credential_store):
    client_class = auth.AccountClient
    revoked = []

    def handler(request):
        revoked.append(request.url.path)
        return httpx.Response(204)

    monkeypatch.setattr(
        auth, "AccountClient", lambda server: client_class(server, httpx.MockTransport(handler))
    )
    monkeypatch.setattr(client_class, "login", lambda self, **kwargs: "session" * 8)

    def cannot_save(*args):
        raise auth.LoginError("Credential storage failed")

    monkeypatch.setattr(auth.Credentials, "set", cannot_save)
    result = CliRunner().invoke(app, ["login", "--server", "https://dark.example"])
    assert result.exit_code == 1 and "Credential storage failed" in result.output
    assert revoked == ["/api/auth/logout"] and not credential_store


@pytest.mark.parametrize("ready", [True, False])
def test_doctor_uses_only_safe_readiness_fields(monkeypatch, ready):
    client_class = auth.AccountClient

    def handler(request):
        assert request.url.path == "/api/auth/readiness"
        assert "Authorization" not in request.headers
        return httpx.Response(
            200 if ready else 503,
            json={
                "ready": ready,
                "checks": {
                    name: ready
                    for name in (
                        "database_configured",
                        "auth_secret_configured",
                        "email_configured",
                        "mongodb_reachable",
                    )
                },
                "unsafe-debug": "provider-secret-must-not-print",
                "email_delivery_verified": True,
            },
        )

    monkeypatch.setattr(
        auth, "AccountClient", lambda server: client_class(server, httpx.MockTransport(handler))
    )
    result = CliRunner().invoke(app, ["doctor", "--server", "https://dark.example", "--json"])
    assert result.exit_code == (0 if ready else 2), result.output
    data = json.loads(result.output)
    assert data["ready"] is ready and data["email_delivery_verified"] is False
    assert "provider-secret" not in result.output
