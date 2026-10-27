"""Transactional email adapters. No codes, keys or provider responses are logged."""

from __future__ import annotations

import httpx

from .settings import Settings


class EmailDeliveryError(Exception):
    pass


def code_message(sender: str, email: str, code: str) -> dict:
    return {
        "from": sender,
        "to": [email],
        "subject": f"{code} is your Dark sign-in code",
        "text": (
            f"Your Dark sign-in code is {code}.\n\n"
            "It expires in 10 minutes and can be used once.\n"
            "If you did not request it, ignore this email.\n"
            "Never share this code with anyone."
        ),
    }


class ResendMailer:
    def __init__(
        self, settings: Settings, transport: httpx.BaseTransport | None = None
    ):
        self.settings = settings
        self.transport = transport

    def send_code(self, email: str, code: str) -> None:
        config = self.settings
        if not config.resend_api_key or not config.email_from:
            raise EmailDeliveryError("Email delivery is not configured yet.")
        try:
            with httpx.Client(timeout=15, transport=self.transport) as client:
                response = client.post(
                    "https://api.resend.com/emails",
                    headers={
                        "Authorization": f"Bearer {config.resend_api_key}",
                        "User-Agent": "dark-cli/0.2",
                    },
                    json=code_message(config.email_from, email, code),
                )
                response.raise_for_status()
                payload = response.json()
                identifier = payload.get("id") if isinstance(payload, dict) else None
                if (
                    not isinstance(identifier, str)
                    or not identifier.strip()
                    or len(identifier) > 256
                    or any(
                        ord(character) < 33 or ord(character) > 126
                        for character in identifier
                    )
                    or "error" in payload
                ):
                    raise EmailDeliveryError(
                        "Email was not accepted for delivery. Try again later."
                    )
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise EmailDeliveryError(
                "Email delivery is unavailable. Try again later."
            ) from exc


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
                    json=code_message(config.email_from, email, code),
                )
                response.raise_for_status()
                payload = response.json()
                result = payload.get("result") if isinstance(payload, dict) else None
                if not isinstance(result, dict):
                    raise EmailDeliveryError(
                        "Email delivery returned an invalid response. Try again later."
                    )
                delivered, queued, bounced = (
                    result.get("delivered", []),
                    result.get("queued", []),
                    result.get("permanent_bounces", []),
                )
                if not all(
                    isinstance(values, list)
                    and all(isinstance(item, str) for item in values)
                    for values in (delivered, queued, bounced)
                ):
                    raise EmailDeliveryError(
                        "Email delivery returned an invalid response. Try again later."
                    )
                if (
                    payload.get("success") is not True
                    or email not in delivered + queued
                    or email in bounced
                ):
                    raise EmailDeliveryError(
                        "Email was not accepted for delivery. Try again later."
                    )
        except (httpx.HTTPError, ValueError, TypeError, AttributeError) as exc:
            raise EmailDeliveryError(
                "Email delivery is unavailable. Try again later."
            ) from exc


def make_mailer(
    settings: Settings, transport: httpx.BaseTransport | None = None
) -> ResendMailer | CloudflareMailer:
    if settings.selected_email_provider == "resend":
        return ResendMailer(settings, transport)
    if settings.selected_email_provider == "cloudflare":
        return CloudflareMailer(settings, transport)
    raise ValueError("DARK_EMAIL_PROVIDER must be resend or cloudflare")
