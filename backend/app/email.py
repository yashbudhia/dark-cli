"""Cloudflare Email Sending REST adapter. No codes or provider responses are logged."""

from __future__ import annotations

import httpx

from .settings import Settings


class EmailDeliveryError(Exception):
    pass


class CloudflareMailer:
    def __init__(
        self, settings: Settings, transport: httpx.BaseTransport | None = None
    ):
        self.settings = settings
        self.transport = transport

    def send_code(self, email: str, code: str) -> None:
        config = self.settings
        if not all(
            (
                config.cloudflare_account_id,
                config.cloudflare_api_token,
                config.email_from,
            )
        ):
            raise EmailDeliveryError("Email delivery is not configured yet.")
        try:
            with httpx.Client(timeout=15, transport=self.transport) as client:
                response = client.post(
                    "https://api.cloudflare.com/client/v4/accounts/"
                    f"{config.cloudflare_account_id}/email/sending/send",
                    headers={"Authorization": f"Bearer {config.cloudflare_api_token}"},
                    json={
                        "from": config.email_from,
                        "to": [email],
                        "subject": f"{code} is your Dark sign-in code",
                        "text": (
                            f"Your Dark sign-in code is {code}.\n\n"
                            "It expires in 10 minutes and can be used once.\n"
                            "If you did not request it, ignore this email.\n"
                            "Never share this code with anyone."
                        ),
                    },
                )
                response.raise_for_status()
                payload = response.json()
                result = payload.get("result", {})
                accepted = result.get("delivered", []) + result.get("queued", [])
                if not payload.get("success") or email not in accepted:
                    raise EmailDeliveryError(
                        "Email was not accepted for delivery. Try again later."
                    )
        except (httpx.HTTPError, ValueError, TypeError, AttributeError) as exc:
            raise EmailDeliveryError(
                "Email delivery is unavailable. Try again later."
            ) from exc
