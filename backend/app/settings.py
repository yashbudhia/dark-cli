"""Server-only configuration; missing credentials never enable a demo login."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from email_validator import EmailNotValidError, validate_email


@dataclass(frozen=True)
class Settings:
    mongo_uri: str = ""
    mongo_database: str = "dark"
    auth_secret: str = ""
    web_url: str = "http://127.0.0.1:3000"
    cloudflare_account_id: str = ""
    cloudflare_api_token: str = ""
    email_from: str = ""

    @classmethod
    def from_env(cls) -> Settings:
        def value(name: str, default: str = "") -> str:
            return os.getenv(name, default).strip()

        return cls(
            mongo_uri=value("MONGODB_URI"),
            mongo_database=value("MONGODB_DATABASE", "dark"),
            auth_secret=value("DARK_AUTH_SECRET"),
            web_url=value("DARK_WEB_URL", "http://127.0.0.1:3000").rstrip("/"),
            cloudflare_account_id=value("CLOUDFLARE_ACCOUNT_ID"),
            cloudflare_api_token=value("CLOUDFLARE_API_TOKEN"),
            email_from=value("DARK_EMAIL_FROM"),
        )

    @property
    def configured(self) -> bool:
        return bool(self.mongo_uri and len(self.auth_secret) >= 32)

    @property
    def secure_cookie(self) -> bool:
        return urlsplit(self.web_url).scheme == "https"

    @property
    def email_configured(self) -> bool:
        return all(
            (self.cloudflare_account_id, self.cloudflare_api_token, self.email_from)
        )

    def validate(self) -> None:
        try:
            url = urlsplit(self.web_url)
            port = url.port
        except ValueError:
            raise ValueError("DARK_WEB_URL must be a valid website origin") from None
        if (
            url.scheme not in ("http", "https")
            or not url.hostname
            or url.username
            or url.password
            or url.path
            or url.query
            or url.fragment
            or any(character.isspace() for character in self.web_url)
            or (port is not None and port < 1)
            or (
                url.scheme == "http"
                and url.hostname not in ("127.0.0.1", "localhost", "::1")
            )
        ):
            raise ValueError(
                "DARK_WEB_URL must be an HTTPS origin (HTTP allowed on loopback)"
            )
        if self.auth_secret and len(self.auth_secret) < 32:
            raise ValueError("DARK_AUTH_SECRET must contain at least 32 characters")
        if self.mongo_uri and not self.mongo_uri.startswith(
            ("mongodb://", "mongodb+srv://")
        ):
            raise ValueError("MONGODB_URI must use mongodb:// or mongodb+srv://")
        if not self.mongo_database or any(
            character in self.mongo_database for character in '/\\. "$*<>:|?\x00'
        ):
            raise ValueError("MONGODB_DATABASE must be a valid MongoDB database name")
        if self.cloudflare_account_id and not re.fullmatch(
            r"[a-zA-Z0-9_-]{1,128}", self.cloudflare_account_id
        ):
            raise ValueError("CLOUDFLARE_ACCOUNT_ID must be a valid account identifier")
        if self.email_from:
            try:
                validate_email(self.email_from, check_deliverability=False)
            except EmailNotValidError:
                raise ValueError(
                    "DARK_EMAIL_FROM must be a valid sender email address"
                ) from None
