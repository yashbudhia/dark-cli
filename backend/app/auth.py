"""Mongo-backed one-time email codes, opaque sessions and first-party CLI pairing."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from email_validator import EmailNotValidError, validate_email
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from .email import EmailDeliveryError
from .settings import Settings

COOKIE_NAME = "dark_session"
POLL_INTERVAL = 5
PAIRING_TTL = 600
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class AuthError(Exception):
    def __init__(
        self,
        status: int,
        message: str,
        code: str = "invalid_request",
        *,
        retry_after: int | None = None,
    ):
        self.status, self.message, self.code = status, message, code
        self.retry_after = retry_after
        super().__init__(message)


def now() -> datetime:
    return datetime.now(UTC)


def normalize_email(value: str) -> str:
    try:
        return validate_email(value, check_deliverability=False).normalized.lower()
    except EmailNotValidError as exc:
        raise AuthError(422, "Enter a valid email address.") from exc


def normalize_code(value: str) -> str:
    return value.upper().replace("-", "").replace(" ", "")


def public_user(user: dict) -> dict:
    return {"id": user["_id"], "email": user["email"], "created_at": user["created_at"]}


class AuthService:
    def __init__(self, db, settings: Settings, mailer):
        self.db, self.settings, self.mailer = db, settings, mailer

    def indexes(self) -> None:
        self.db.users.create_index("email", unique=True)
        for name in ("email_codes", "sessions", "device_codes", "auth_limits"):
            self.db[name].create_index("expires_at", expireAfterSeconds=0)
        self.db.sessions.create_index("user_id")
        self.db.device_codes.create_index("user_code_hash", unique=True)
        self.db.runs.create_index([("owner_id", 1), ("id", 1)], unique=True)
        self.db.payments.create_index("user_id")
        self.db.credit_ledger.create_index("user_id")
        for name in ("findings", "refusals"):
            self.db[name].create_index(
                [("owner_id", 1), ("run_id", 1), ("id", 1)], unique=True
            )

    def digest(self, purpose: str, value: str) -> str:
        return hmac.new(
            self.settings.auth_secret.encode(),
            f"{purpose}:{value}".encode(),
            hashlib.sha256,
        ).hexdigest()

    def limit(self, key: str, maximum: int, seconds: int) -> None:
        timestamp = int(time.time())
        bucket = timestamp // seconds
        query = {"_id": self.digest("limit", f"{key}:{bucket}")}
        update = {
            "$inc": {"count": 1},
            "$setOnInsert": {"expires_at": now() + timedelta(seconds=seconds * 2)},
        }
        try:
            entry = self.db.auth_limits.find_one_and_update(
                query,
                update,
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError:
            # Another worker inserted this bucket after our upsert's query phase.
            entry = self.db.auth_limits.find_one_and_update(
                query,
                {"$inc": {"count": 1}},
                return_document=ReturnDocument.AFTER,
            )
            if entry is None:
                raise
        if entry["count"] > maximum:
            raise AuthError(
                429,
                "Too many attempts. Wait for the cooldown and try again.",
                "rate_limited",
                retry_after=seconds - timestamp % seconds,
            )

    def request_email(self, email: str, ip: str) -> dict:
        email = normalize_email(email)
        self.limit(f"email-ip:{ip}", 20, 600)
        self.limit(f"email:{email}", 1, 60)
        challenge, code = (
            secrets.token_urlsafe(32),
            f"{secrets.randbelow(100_000_000):08d}",
        )
        challenge_hash = self.digest("challenge", challenge)
        self.db.email_codes.insert_one(
            {
                "_id": challenge_hash,
                "email": email,
                "code_hash": self.digest("otp", f"{challenge}:{code}"),
                "attempts": 0,
                "expires_at": now() + timedelta(minutes=10),
            }
        )
        try:
            self.mailer.send_code(email, code)
        except EmailDeliveryError as exc:
            self.db.email_codes.delete_one({"_id": challenge_hash})
            raise AuthError(503, str(exc), "email_unavailable") from exc
        return {"challenge_id": challenge, "expires_in": 600, "resend_after": 60}

    def verify_email(self, challenge: str, code: str, ip: str) -> tuple[dict, str]:
        self.limit(f"verify-ip:{ip}", 60, 600)
        query = {
            "_id": self.digest("challenge", challenge),
            "expires_at": {"$gt": now()},
            "attempts": {"$lt": 5},
        }
        entry = self.db.email_codes.find_one_and_update(
            query, {"$inc": {"attempts": 1}}
        )
        if not entry or not hmac.compare_digest(
            entry["code_hash"], self.digest("otp", f"{challenge}:{code}")
        ):
            raise AuthError(
                400, "Code is incorrect or expired. Request a new code.", "invalid_code"
            )
        # Atomic delete makes a successful code single-use, including concurrent requests.
        if not self.db.email_codes.find_one_and_delete({"_id": entry["_id"]}):
            raise AuthError(400, "Code has already been used.", "invalid_code")
        try:
            user = self.db.users.find_one_and_update(
                {"email": entry["email"]},
                {"$setOnInsert": {"_id": secrets.token_hex(16), "created_at": now()}},
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError:
            # Separate valid challenges for the same email may finish concurrently.
            user = self.db.users.find_one({"email": entry["email"]})
            if user is None:
                raise
        token, _ = self.issue_session(user["_id"], "web", "Browser")
        return public_user(user), token

    def issue_session(self, user_id: str, kind: str, name: str) -> tuple[str, int]:
        token = secrets.token_urlsafe(48)
        lifetime = (7 if kind == "web" else 30) * 86400
        self.db.sessions.insert_one(
            {
                "_id": self.digest("session", token),
                "id": secrets.token_hex(16),
                "user_id": user_id,
                "kind": kind,
                "name": name,
                "created_at": now(),
                "expires_at": now() + timedelta(seconds=lifetime),
            }
        )
        return token, lifetime

    def authenticate(self, token: str, kind: str | None = None) -> tuple[dict, dict]:
        query = {"_id": self.digest("session", token), "expires_at": {"$gt": now()}}
        if kind:
            query["kind"] = kind
        session = self.db.sessions.find_one(query)
        user = self.db.users.find_one({"_id": session["user_id"]}) if session else None
        if not user:
            raise AuthError(401, "Sign in to continue.", "unauthenticated")
        return user, session

    def start_device(self, name: str, ip: str) -> dict:
        self.limit(f"device-ip:{ip}", 30, 600)
        for _ in range(3):
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
            device_code = secrets.token_urlsafe(48)
            try:
                self.db.device_codes.insert_one(
                    {
                        "_id": self.digest("device", device_code),
                        "user_code_hash": self.digest("user-code", code),
                        "name": name,
                        "status": "pending",
                        "created_at": now(),
                        "expires_at": now() + timedelta(seconds=PAIRING_TTL),
                        "last_poll_at": now() - timedelta(seconds=POLL_INTERVAL),
                    }
                )
                break
            except DuplicateKeyError:
                continue
        else:
            raise AuthError(503, "Could not create a pairing code. Try again.")
        display = f"{code[:4]}-{code[4:]}"
        uri = f"{self.settings.web_url}/connect"
        return {
            "device_code": device_code,
            "user_code": display,
            "verification_uri": uri,
            "verification_uri_complete": f"{uri}?{urlencode({'code': display})}",
            "expires_in": PAIRING_TTL,
            "interval": POLL_INTERVAL,
        }

    def device_info(self, code: str) -> dict:
        entry = self.db.device_codes.find_one(
            {
                "user_code_hash": self.digest("user-code", normalize_code(code)),
                "expires_at": {"$gt": now()},
                "status": "pending",
            }
        )
        if not entry:
            raise AuthError(404, "Pairing code is invalid or expired.", "expired_token")
        return {"name": entry["name"], "expires_at": entry["expires_at"]}

    def decide_device(self, code: str, user_id: str, approve: bool) -> None:
        result = self.db.device_codes.update_one(
            {
                "user_code_hash": self.digest("user-code", normalize_code(code)),
                "expires_at": {"$gt": now()},
                "status": "pending",
            },
            {
                "$set": {
                    "status": "approved" if approve else "denied",
                    "user_id": user_id,
                }
            },
        )
        if not result.modified_count:
            raise AuthError(400, "Pairing code is invalid, expired, or already used.")

    def poll_device(self, code: str) -> dict:
        query = {"_id": self.digest("device", code), "expires_at": {"$gt": now()}}
        entry = self.db.device_codes.find_one_and_update(
            {
                **query,
                "last_poll_at": {"$lte": now() - timedelta(seconds=POLL_INTERVAL)},
            },
            {"$set": {"last_poll_at": now()}},
        )
        if not entry:
            if self.db.device_codes.find_one(query):
                raise AuthError(
                    400,
                    "Wait before polling again.",
                    "slow_down",
                    retry_after=POLL_INTERVAL,
                )
            raise AuthError(
                400, "Pairing request expired. Run dark login again.", "expired_token"
            )
        if entry["status"] == "pending":
            raise AuthError(
                400, "Waiting for browser approval.", "authorization_pending"
            )
        if entry["status"] == "denied":
            self.db.device_codes.delete_one(query)
            raise AuthError(400, "Connection was declined.", "access_denied")
        entry = self.db.device_codes.find_one_and_delete(
            {**query, "status": "approved"}
        )
        if not entry:
            raise AuthError(400, "Pairing request already used.", "expired_token")
        token, lifetime = self.issue_session(entry["user_id"], "cli", entry["name"])
        return {"access_token": token, "token_type": "Bearer", "expires_in": lifetime}
