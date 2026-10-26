"""Server-only configuration; missing credentials never enable a demo login."""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlsplit


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
        return cls(
            mongo_uri=os.getenv("MONGODB_URI", ""),
            mongo_database=os.getenv("MONGODB_DATABASE", "dark"),
            auth_secret=os.getenv("DARK_AUTH_SECRET", ""),
            web_url=os.getenv("DARK_WEB_URL", "http://127.0.0.1:3000").rstrip("/"),
            cloudflare_account_id=os.getenv("CLOUDFLARE_ACCOUNT_ID", ""),
            cloudflare_api_token=os.getenv("CLOUDFLARE_API_TOKEN", ""),
            email_from=os.getenv("DARK_EMAIL_FROM", ""),
        )

    @property
    def configured(self) -> bool:
        return bool(self.mongo_uri and len(self.auth_secret) >= 32)

    @property
    def secure_cookie(self) -> bool:
        return self.web_url.startswith("https://")

    def validate(self) -> None:
        url = urlsplit(self.web_url)
        if (
            url.scheme not in ("http", "https")
            or not url.hostname
            or url.username
            or url.password
            or url.path not in ("", "/")
            or url.query
            or url.fragment
            or (
                url.scheme == "http"
                and url.hostname not in ("127.0.0.1", "localhost", "::1")
            )
        ):
            raise ValueError(
                "DARK_WEB_URL must be an HTTPS origin (HTTP allowed on loopback)"
            )
