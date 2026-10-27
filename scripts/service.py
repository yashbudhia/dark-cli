"""Initialize service configuration and run the local API/Next.js stack."""

from __future__ import annotations

import argparse
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import urlopen

from dotenv import dotenv_values, set_key

ROOT = Path(__file__).resolve().parent.parent
REQUIRED = (
    "MONGODB_URI",
    "DARK_AUTH_SECRET",
    "DARK_EMAIL_FROM",
)
SERVER_ONLY = frozenset(REQUIRED) | {
    "RESEND_API_KEY",
    "RAZORPAY_KEY_ID",
    "RAZORPAY_KEY_SECRET",
    "RAZORPAY_WEBHOOK_SECRET",
    "CLOUDFLARE_ACCOUNT_ID",
    "CLOUDFLARE_API_TOKEN",
    "DARK_EMAIL_PROVIDER",
    "MONGODB_DATABASE",
    "DARK_API_KEY",
    "TYPESAFE_API_KEY",
    "DARK_BASE_URL",
    "DARK_MODEL",
    "DARK_VISION_MODEL",
    "DARK_WINDOWS_MCP_PATH",
}


def initialize_env(template: Path, destination: Path) -> bool:
    """Fill missing keys and create a stable auth secret, preserving existing values."""
    created = not destination.exists()
    if created:
        destination.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
    current = dotenv_values(destination)
    for key, value in dotenv_values(template).items():
        if key not in current:
            set_key(destination, key, value or "")
    current = dotenv_values(destination)
    if not (current.get("DARK_AUTH_SECRET") or "").strip():
        set_key(destination, "DARK_AUTH_SECRET", secrets.token_urlsafe(48))
    return created


def environment(path: Path) -> dict[str, str]:
    return {
        **{
            key: value.strip()
            for key, value in dotenv_values(path).items()
            if value is not None
        },
        **os.environ,
    }


def missing_config(values: dict[str, str]) -> list[str]:
    provider = values.get("DARK_EMAIL_PROVIDER", "").strip().lower()
    if provider not in ("", "resend", "cloudflare"):
        raise ValueError("DARK_EMAIL_PROVIDER must be resend or cloudflare")
    provider = provider or (
        "resend" if values.get("RESEND_API_KEY", "").strip() else "cloudflare"
    )
    provider_keys = (
        ("RESEND_API_KEY",)
        if provider == "resend"
        else ("CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN")
    )
    return [
        key for key in (*REQUIRED, *provider_keys) if not values.get(key, "").strip()
    ]


def local_origin(value: str, port: int) -> str:
    """Local port overrides keep browser Origin checks consistent with the local URL."""
    parsed = urlsplit(value)
    if parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "localhost"):
        return f"http://{parsed.hostname}:{port}"
    return value.rstrip("/")


def check_port(port: int) -> None:
    if not 1 <= port <= 65535:
        raise ValueError("Service ports must be between 1 and 65535.")
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError as exc:
            raise ValueError(
                f"Port {port} is in use. Stop the existing server or choose another port."
            ) from exc


def stop_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
                check=False,
            )
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def spawn(command: list[str], cwd: Path, values: dict[str, str]) -> subprocess.Popen:
    return subprocess.Popen(
        command,
        cwd=cwd,
        env=values,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        start_new_session=os.name != "nt",
    )


def wait_for_api(process: subprocess.Popen, port: int) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                "Backend exited during startup. Review its configuration errors above."
            )
        try:
            with urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as response:
                if response.status == 200:
                    return
        except (URLError, TimeoutError):
            time.sleep(0.2)
    raise RuntimeError("Backend did not become available within 20 seconds.")


def start(args: argparse.Namespace) -> None:
    values = environment(ROOT / ".env")
    missing = missing_config(values)
    if missing and not args.allow_unconfigured:
        raise ValueError("Set these variables in .env first: " + ", ".join(missing))
    backend_port = args.backend_port or int(values.get("DARK_BACKEND_PORT", "8000"))
    frontend_port = args.frontend_port
    if frontend_port is None:
        try:
            website = urlsplit(values.get("DARK_WEB_URL", "http://127.0.0.1:3000"))
            frontend_port = (
                website.port if website.hostname in ("127.0.0.1", "localhost") else None
            )
        except ValueError:
            raise ValueError(
                "DARK_WEB_URL must contain a valid website origin and port."
            ) from None
        frontend_port = frontend_port or 3000
    if frontend_port == backend_port:
        raise ValueError("Frontend and backend need different ports.")
    for port in (frontend_port, backend_port):
        check_port(port)
    node = shutil.which("node")
    next_cli = ROOT / "frontend" / "node_modules" / "next" / "dist" / "bin" / "next"
    if not node or not next_cli.exists():
        raise ValueError(
            "Frontend dependencies are missing. Run scripts/setup-service.ps1 first."
        )
    values["DARK_WEB_URL"] = local_origin(
        values.get("DARK_WEB_URL", "http://127.0.0.1:3000"),
        frontend_port,
    )
    # Root .env is read only by the API. The web process needs the proxy URL.
    frontend_env = {
        key: value for key, value in os.environ.items() if key not in SERVER_ONLY
    }
    frontend_env["DARK_BACKEND_URL"] = f"http://127.0.0.1:{backend_port}"
    frontend_env["NEXT_TELEMETRY_DISABLED"] = "1"
    children = []
    try:
        backend = spawn(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(backend_port),
                "--no-access-log",
            ],
            ROOT,
            values,
        )
        children.append(backend)
        wait_for_api(backend, backend_port)
        if args.production:
            subprocess.run(
                [node, str(next_cli), "build"],
                cwd=ROOT / "frontend",
                env=frontend_env,
                check=True,
            )
        frontend = spawn(
            [
                node,
                str(next_cli),
                "start" if args.production else "dev",
                "--hostname",
                "127.0.0.1",
                "--port",
                str(frontend_port),
            ],
            ROOT / "frontend",
            frontend_env,
        )
        children.append(frontend)
        print(f"\nDark website: {values['DARK_WEB_URL']}", flush=True)
        print(
            f"CLI commands: use --server {values['DARK_WEB_URL']} when overriding the default.",
            flush=True,
        )
        print("Press Ctrl+C to stop both service processes.\n", flush=True)
        if missing:
            print(
                "Preview only: account services need " + ", ".join(missing), flush=True
            )
        while all(child.poll() is None for child in children):
            time.sleep(0.25)
        raise RuntimeError(
            "A service process exited. Both processes have been stopped."
        )
    finally:
        for child in reversed(children):
            stop_process(child)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="Create .env without overwriting credentials.")
    run = commands.add_parser("start", help="Start the API and Next.js together.")
    run.add_argument(
        "--production",
        action="store_true",
        help="Build and serve Next.js production assets.",
    )
    run.add_argument(
        "--allow-unconfigured",
        action="store_true",
        help="Preview pages with unavailable account APIs.",
    )
    run.add_argument("--frontend-port", type=int)
    run.add_argument("--backend-port", type=int)
    args = parser.parse_args()
    try:
        if args.command == "init":
            created = initialize_env(ROOT / ".env.example", ROOT / ".env")
            print(
                "Created .env."
                if created
                else "Preserved .env and filled missing configuration keys."
            )
            print("DARK_AUTH_SECRET is configured; its value is not printed.")
            remaining = missing_config(environment(ROOT / ".env"))
            if remaining:
                print("Fill in: " + ", ".join(remaining))
        else:
            start(args)
    except KeyboardInterrupt:
        print("\nDark service stopped.")
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
