"""Browser-approved account login; credentials remain in the OS keyring."""

from __future__ import annotations

import socket
import time
import webbrowser
from urllib.parse import urlsplit

import httpx
import keyring
import typer
from keyring.errors import KeyringError


class LoginError(Exception):
    pass


def server_url(value: str) -> str:
    value = value.rstrip("/")
    parsed = urlsplit(value)
    if (
        parsed.scheme not in ("https", "http")
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
        or (parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"))
    ):
        raise LoginError("Use an HTTPS website origin; HTTP is allowed only on loopback.")
    return value


class Credentials:
    def __init__(self, server: str):
        self.service = f"dark-cli:{server}"

    def get(self) -> str | None:
        try:
            backend = keyring.get_keyring()
            if backend.priority <= 0 or type(backend).__module__.startswith("keyrings.alt"):
                raise LoginError("No OS credential store is available. Configure a keyring first.")
            return keyring.get_password(self.service, "session")
        except (KeyringError, RuntimeError) as exc:
            raise LoginError("The OS credential store is unavailable or locked.") from exc

    def set(self, token: str) -> None:
        try:
            keyring.set_password(self.service, "session", token)
        except (KeyringError, RuntimeError) as exc:
            raise LoginError("Could not save the session in the OS credential store.") from exc

    def delete(self) -> None:
        try:
            if self.get() is not None:
                keyring.delete_password(self.service, "session")
        except (KeyringError, RuntimeError) as exc:
            raise LoginError("Could not remove the local session.") from exc


class AccountClient:
    def __init__(self, server: str, transport: httpx.BaseTransport | None = None):
        self.server = server_url(server)
        self.http = httpx.Client(base_url=self.server, timeout=15, transport=transport)

    def close(self) -> None:
        self.http.close()

    def request(
        self, method: str, path: str, *, token: str | None = None, **kwargs
    ) -> httpx.Response:
        try:
            return self.http.request(
                method,
                path,
                headers={"Authorization": f"Bearer {token}"} if token else {},
                **kwargs,
            )
        except httpx.HTTPError as exc:
            raise LoginError(
                "Cannot reach the Dark server. Check --server and your connection."
            ) from exc

    @staticmethod
    def require_success(response: httpx.Response) -> dict:
        if response.status_code == 401:
            raise LoginError("Session expired or revoked. Run dark login again.")
        if not response.is_success:
            raise LoginError(f"Dark server returned HTTP {response.status_code}. Try again later.")
        try:
            return response.json()
        except ValueError as exc:
            raise LoginError("Dark server returned an invalid response.") from exc

    def login(
        self,
        *,
        open_browser=webbrowser.open,
        notify=typer.echo,
        sleep=time.sleep,
        clock=time.monotonic,
        no_browser=False,
    ) -> str:
        pairing = self.require_success(
            self.request(
                "POST",
                "/api/auth/device/code",
                json={"name": f"{socket.gethostname()} / Dark CLI"[:80]},
            )
        )
        try:
            uri = pairing["verification_uri_complete"]
            parsed = urlsplit(uri)
            if (
                server_url(f"{parsed.scheme}://{parsed.netloc}") != self.server
                or parsed.path != "/connect"
            ):
                raise ValueError("Unexpected verification origin")
            device_code, display_code = pairing["device_code"], pairing["user_code"]
            interval, lifetime = int(pairing["interval"]), int(pairing["expires_in"])
            if not (5 <= interval <= 30 and 1 <= lifetime <= 600):
                raise ValueError("Invalid timing")
        except (KeyError, TypeError, ValueError) as exc:
            raise LoginError("Dark server returned an invalid pairing request.") from exc
        notify(f"Open {uri}\nConfirm this code in your browser: {display_code}")
        if not no_browser:
            try:
                open_browser(uri)
            except webbrowser.Error:
                notify("Could not open the browser. Open the URL above manually.")
        deadline = clock() + lifetime
        while clock() < deadline:
            sleep(min(interval, max(0, deadline - clock())))
            if clock() >= deadline:
                break
            response = self.request(
                "POST", "/api/auth/device/token", json={"device_code": device_code}
            )
            if response.is_success:
                payload = self.require_success(response)
                token = payload.get("access_token")
                if not isinstance(token, str) or len(token) < 32:
                    raise LoginError("Dark server did not return a valid session.")
                return token
            try:
                error = response.json().get("error")
            except (ValueError, AttributeError):
                error = None
            if response.status_code == 400 and error == "authorization_pending":
                continue
            if response.status_code == 400 and error == "slow_down":
                interval += 5
                continue
            if error == "access_denied":
                raise LoginError("Connection declined in the browser.")
            if error == "expired_token":
                break
            self.require_success(response)
        raise LoginError("Pairing expired. Run dark login again.")


def register(app: typer.Typer) -> None:
    @app.command()
    def login(
        server: str = typer.Option("http://127.0.0.1:3000", envvar="DARK_SERVER_URL"),
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
                    typer.echo("Already connected. Run dark whoami or dark logout.")
                    return
                if response.status_code != 401:
                    client.require_success(response)
                credentials.delete()
            token = client.login(no_browser=no_browser)
            try:
                credentials.set(token)
            except LoginError:
                client.request("POST", "/api/auth/logout", token=token)
                raise
            typer.echo("Connected. Your session is saved in the OS credential store.")
        except LoginError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(1) from exc
        finally:
            if client:
                client.close()

    @app.command()
    def whoami(
        server: str = typer.Option("http://127.0.0.1:3000", envvar="DARK_SERVER_URL"),
    ) -> None:
        """Show the account connected to this CLI."""
        client = None
        try:
            client = AccountClient(server)
            token = Credentials(client.server).get()
            if not token:
                raise LoginError("Not connected. Run dark login.")
            data = client.require_success(client.request("GET", "/api/auth/me", token=token))
            typer.echo(f"{data['user']['email']}\nServer: {client.server}")
        except LoginError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(1) from exc
        finally:
            if client:
                client.close()

    @app.command()
    def logout(
        server: str = typer.Option("http://127.0.0.1:3000", envvar="DARK_SERVER_URL"),
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
