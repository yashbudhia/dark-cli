"""Browser-approved account login; credentials remain in the OS keyring."""

from __future__ import annotations

import json
import re
import socket
import time
import webbrowser
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlsplit

import keyring
from keyring.errors import KeyringError

from . import ui
from .config import ConfigError, configured_server, remember_server

if TYPE_CHECKING:
    import httpx
    import typer


class LoginError(Exception):
    pass


class ConnectionInterrupted(LoginError):
    """A transport failure, which may be retried only for a recoverable operation."""


def server_url(value: str) -> str:
    import httpx

    try:
        if any(ord(character) < 33 or ord(character) == 127 for character in value):
            raise ValueError("Control character in origin")
        value = value.rstrip("/")
        parsed = urlsplit(value)
        port = parsed.port
        if (
            parsed.scheme not in ("https", "http")
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path
            or parsed.query
            or parsed.fragment
            or (port is not None and not 1 <= port <= 65535)
            or (
                parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "::1")
            )
        ):
            raise ValueError("Invalid origin")
        return str(httpx.URL(value)).rstrip("/")
    except (ValueError, httpx.InvalidURL) as exc:
        raise LoginError("Use an HTTPS website origin; HTTP is allowed only on loopback.") from exc


def account_email(data: dict) -> str:
    user = data.get("user")
    email = user.get("email") if isinstance(user, dict) else None
    if (
        not isinstance(email, str)
        or not 3 <= len(email) <= 254
        or "@" not in email
        or any(ord(c) < 32 or ord(c) == 127 for c in email)
    ):
        raise LoginError("Dark server returned an invalid account response.")
    return email


class Credentials:
    def __init__(self, server: str):
        self.service = f"dark-cli:{server}"

    @staticmethod
    def backend():
        backend = keyring.get_keyring()
        candidates = (
            backend.backends
            if type(backend).__module__ == "keyring.backends.chainer"
            else [backend]
        )
        supported = (
            "keyring.backends.Windows",
            "keyring.backends.macOS",
            "keyring.backends.SecretService",
            "keyring.backends.kwallet",
            "keyring.backends.libsecret",
        )
        for candidate in candidates:
            if type(candidate).__module__.startswith(supported) and candidate.priority > 0:
                return candidate
        raise LoginError(
            "No supported OS credential store is available. Configure a native keyring first."
        )

    def get(self) -> str | None:
        try:
            return self.backend().get_password(self.service, "session")
        except (KeyringError, RuntimeError, OSError) as exc:
            raise LoginError("The OS credential store is unavailable or locked.") from exc

    def set(self, token: str) -> None:
        try:
            self.backend().set_password(self.service, "session", token)
        except (KeyringError, RuntimeError, OSError) as exc:
            raise LoginError("Could not save the session in the OS credential store.") from exc

    def delete(self) -> None:
        try:
            if self.get() is not None:
                self.backend().delete_password(self.service, "session")
        except (KeyringError, RuntimeError, OSError) as exc:
            raise LoginError("Could not remove the local session.") from exc


class AccountClient:
    def __init__(self, server: str | None, transport: httpx.BaseTransport | None = None):
        try:
            self.server = server_url(configured_server(server))
        except ConfigError as exc:
            raise LoginError(str(exc)) from exc
        import httpx

        self.http = httpx.Client(
            base_url=self.server,
            timeout=httpx.Timeout(30, connect=10),
            transport=transport,
            limits=httpx.Limits(keepalive_expiry=60),
        )

    def close(self) -> None:
        self.http.close()

    def request(
        self, method: str, path: str, *, token: str | None = None, **kwargs
    ) -> httpx.Response:
        import httpx

        try:
            return self.http.request(
                method,
                path,
                headers={"Authorization": f"Bearer {token}"} if token else {},
                **kwargs,
            )
        except httpx.HTTPError as exc:
            raise ConnectionInterrupted(
                "Cannot reach the Dark server. Check --server and your connection."
            ) from exc

    @staticmethod
    def require_success(response: httpx.Response, *, expect_list: bool = False) -> dict | list:
        if response.status_code == 401:
            raise LoginError("Session expired or revoked. Run dark login again.")
        if not response.is_success:
            if response.status_code == 503:
                raise LoginError(
                    "Dark service is not ready. Run dark doctor to check configuration and storage."
                )
            if response.status_code == 429:
                raise LoginError("Too many requests. Wait a minute before trying again.")
            raise LoginError(f"Dark server returned HTTP {response.status_code}. Try again later.")
        try:
            result = response.json()
            if not isinstance(result, list if expect_list else dict):
                raise ValueError("Unexpected JSON shape")
            return result
        except ValueError as exc:
            raise LoginError("Dark server returned an invalid response.") from exc

    def login(
        self,
        *,
        open_browser=webbrowser.open,
        notify=None,
        sleep=time.sleep,
        clock=time.monotonic,
        no_browser=False,
    ) -> str:
        if notify is None:
            import typer

            notify = typer.echo
        pairing = self.require_success(
            self.request(
                "POST",
                "/api/auth/device/code",
                json={"name": f"{socket.gethostname()} / Dark CLI"[:80], "poll_interval": 2},
            )
        )
        try:
            uri = pairing["verification_uri_complete"]
            if not isinstance(uri, str) or any(ord(c) < 33 or ord(c) == 127 for c in uri):
                raise ValueError("Invalid verification URL")
            parsed = urlsplit(uri)
            if (
                server_url(f"{parsed.scheme}://{parsed.netloc}") != self.server
                or parsed.path != "/connect"
                or parsed.fragment
            ):
                raise ValueError("Unexpected verification origin")
            device_code, display_code = pairing["device_code"], pairing["user_code"]
            if not isinstance(device_code, str) or not re.fullmatch(
                r"[A-Za-z0-9_-]{32,128}", device_code
            ):
                raise ValueError("Invalid device code")
            if not isinstance(display_code, str) or not re.fullmatch(
                r"[A-Z2-9]{4}-[A-Z2-9]{4}", display_code
            ):
                raise ValueError("Invalid display code")
            if parse_qs(parsed.query).get("code") != [display_code]:
                raise ValueError("Verification code mismatch")
            interval, lifetime = pairing["interval"], pairing["expires_in"]
            if type(interval) is not int or type(lifetime) is not int:
                raise ValueError("Invalid timing types")
            if not (2 <= interval <= 30 and 1 <= lifetime <= 600):
                raise ValueError("Invalid timing")
        except (KeyError, TypeError, ValueError) as exc:
            raise LoginError("Dark server returned an invalid pairing request.") from exc
        deadline = clock() + lifetime
        notify(f"Open {uri}\nConfirm this code in your browser: {display_code}")
        if not no_browser:
            try:
                if open_browser(uri) is False:
                    notify("Could not open the browser. Open the URL above manually.")
            except (webbrowser.Error, OSError):
                notify("Could not open the browser. Open the URL above manually.")
        delay = 0
        interrupted = False
        with ui.progress(f"Waiting for approval of {display_code} in your browser"):
            while clock() < deadline:
                sleep(min(delay, max(0, deadline - clock())))
                if clock() >= deadline:
                    break
                try:
                    response = self.request(
                        "POST", "/api/auth/device/token", json={"device_code": device_code}
                    )
                except ConnectionInterrupted:
                    if not interrupted:
                        notify(
                            "Connection interrupted; retrying this pairing. Your browser approval is preserved."
                        )
                    interrupted = True
                    delay = interval
                    continue
                delay = interval
                if response.status_code in (429, 500, 502, 503, 504):
                    if not interrupted:
                        notify("Service temporarily unavailable; retrying this pairing.")
                    interrupted = True
                    delay = min(30, max(interval, retry_after(response, interval)))
                    continue
                interrupted = False
                if response.is_success:
                    payload = self.require_success(response)
                    token = payload.get("access_token")
                    if not isinstance(token, str) or not re.fullmatch(
                        r"[A-Za-z0-9_-]{32,256}", token
                    ):
                        raise LoginError("Dark server did not return a valid session.")
                    return token
                try:
                    error = response.json().get("error")
                except (ValueError, AttributeError):
                    error = None
                if response.status_code == 400 and error == "authorization_pending":
                    continue
                if response.status_code == 400 and error == "slow_down":
                    delay = retry_after(response, interval + 5)
                    interval = max(interval, delay)
                    continue
                if error == "access_denied":
                    raise LoginError("Connection declined in the browser.")
                if error == "expired_token":
                    break
                self.require_success(response)
        raise LoginError("Pairing expired. Run dark login again.")


def retry_after(response: httpx.Response, default: int) -> int:
    try:
        return min(30, max(1, int(response.headers["Retry-After"])))
    except (KeyError, ValueError):
        return default


def register(app: typer.Typer) -> None:
    import typer

    @app.command()
    def doctor(
        server: str | None = typer.Option(None, envvar="DARK_SERVER_URL"),
        json_output: bool = typer.Option(
            False, "--json", help="Print a machine-readable readiness summary."
        ),
    ) -> None:
        """Check service configuration and MongoDB connectivity without sending email."""
        client = None
        try:
            client = AccountClient(server)
            response = client.request("GET", "/api/auth/readiness")
            if response.status_code not in (200, 503):
                client.require_success(response)
            try:
                data = response.json()
                names = (
                    "database_configured",
                    "auth_secret_configured",
                    "email_configured",
                    "mongodb_reachable",
                )
                checks = {name: data["checks"][name] for name in names}
                if (
                    any(type(value) is not bool for value in checks.values())
                    or type(data["ready"]) is not bool
                ):
                    raise ValueError("Invalid readiness status")
                ready = data["ready"] and all(checks.values()) and response.status_code == 200
            except (ValueError, TypeError, KeyError) as exc:
                raise LoginError("Dark server returned an invalid readiness response.") from exc
            if json_output:
                typer.echo(
                    json.dumps(
                        {
                            "server": client.server,
                            "ready": ready,
                            "checks": checks,
                            "email_delivery_verified": False,
                        },
                        indent=2,
                    )
                )
            else:
                typer.echo(f"Server: {client.server}")
                labels = {
                    "database_configured": "MongoDB configured",
                    "auth_secret_configured": "Auth secret configured",
                    "email_configured": "Email sending configured",
                    "mongodb_reachable": "MongoDB reachable",
                }
                for name, passed in checks.items():
                    typer.echo(f"{'OK' if passed else 'MISSING'}  {labels[name]}")
                typer.echo("Email delivery: not verified by this check.")
                typer.echo(
                    "Service configuration and storage are ready."
                    if ready
                    else "Configure the missing settings and restart the service."
                )
            if not ready:
                raise typer.Exit(2)
        except LoginError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(1) from exc
        finally:
            if client:
                client.close()

    @app.command()
    def login(
        server: str | None = typer.Option(None, envvar="DARK_SERVER_URL"),
        no_browser: bool = typer.Option(
            False, "--no-browser", help="Print the URL without opening it."
        ),
    ) -> None:
        """Sign in through the website and connect this computer."""
        client = None
        try:
            client = AccountClient(server)
            credentials = Credentials(client.server)
            existing = credentials.get()
            if existing:
                response = client.request("GET", "/api/auth/me", token=existing)
                if response.is_success:
                    email = account_email(client.require_success(response))
                    try:
                        remember_server(client.server)
                    except ConfigError as exc:
                        typer.echo(str(exc), err=True)
                    typer.echo(f"Already connected as {email}. Run dark whoami or dark logout.")
                    return
                if response.status_code != 401:
                    client.require_success(response)
                credentials.delete()
            token = client.login(no_browser=no_browser)
            try:
                credentials.set(token)
            except LoginError as exc:
                try:
                    response = client.request("POST", "/api/auth/logout", token=token)
                    if not response.is_success and response.status_code != 401:
                        raise LoginError("Revocation failed")
                except LoginError:
                    raise LoginError(
                        "Could not save the session or confirm remote revocation. Revoke this computer from your website workspace."
                    ) from exc
                raise
            try:
                remember_server(client.server)
            except ConfigError as exc:
                typer.echo(str(exc), err=True)
            typer.echo("Connected. Your session is saved in the OS credential store.")
        except KeyboardInterrupt as exc:
            typer.echo(
                "Login cancelled. Any pending pairing code will expire automatically.", err=True
            )
            raise typer.Exit(130) from exc
        except LoginError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(1) from exc
        finally:
            if client:
                client.close()

    @app.command()
    def whoami(
        server: str | None = typer.Option(None, envvar="DARK_SERVER_URL"),
    ) -> None:
        """Show the account connected to this CLI."""
        client = None
        try:
            client = AccountClient(server)
            token = Credentials(client.server).get()
            if not token:
                raise LoginError("Not connected. Run dark login.")
            data = client.require_success(client.request("GET", "/api/auth/me", token=token))
            typer.echo(f"{account_email(data)}\nServer: {client.server}")
        except LoginError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(1) from exc
        finally:
            if client:
                client.close()

    @app.command()
    def logout(
        server: str | None = typer.Option(None, envvar="DARK_SERVER_URL"),
        local_only: bool = typer.Option(
            False, "--local-only", help="Forget this credential without revoking it remotely."
        ),
    ) -> None:
        """Revoke this CLI session and remove its local credential."""
        client = None
        try:
            client = AccountClient(server)
            credentials = Credentials(client.server)
            token = credentials.get()
            if token and not local_only:
                response = client.request("POST", "/api/auth/logout", token=token)
                if not response.is_success and response.status_code != 401:
                    client.require_success(response)
            credentials.delete()
            typer.echo("Local credential removed." if local_only else "Signed out.")
        except LoginError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(1) from exc
        finally:
            if client:
                client.close()
