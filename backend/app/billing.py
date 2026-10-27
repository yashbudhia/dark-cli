"""Razorpay checkout for prepaid credits: server-priced top-ups, bonuses and a free trial."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from .auth import AuthError, AuthService, now
from .auth_routes import BrowserUser, Service
from .settings import Settings

router = APIRouter(prefix="/api/billing", tags=["billing"])
RAZORPAY_API = "https://api.razorpay.com/v1"
CURRENCY = "USD"
TRIAL_CENTS = 100  # $1 free, once per account

# Amounts are cents. Recharge $10 and get $5 free.
PACKS = {
    "topup_5": {"id": "topup_5", "price": 500, "bonus": 0},
    "topup_10": {"id": "topup_10", "price": 1000, "bonus": 500},
}


def pack_view(pack: dict) -> dict:
    return {**pack, "credit": pack["price"] + pack["bonus"], "currency": CURRENCY}


def razorpay_request(settings: Settings, method: str, path: str, body=None) -> dict:
    try:
        response = httpx.request(
            method,
            f"{RAZORPAY_API}{path}",
            json=body,
            auth=(settings.razorpay_key_id, settings.razorpay_key_secret),
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise TypeError("Unexpected payment response")
        return payload
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise AuthError(
            502,
            "Payments are unavailable right now. Try again.",
            "payments_unavailable",
        ) from exc


def razorpay_post(settings: Settings, path: str, body: dict) -> dict:
    return razorpay_request(settings, "POST", path, body)


def razorpay_get(settings: Settings, path: str) -> dict:
    return razorpay_request(settings, "GET", path)


def sign(secret: str, message: bytes) -> str:
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def billing_enabled(auth: Service) -> Settings:
    if not auth.settings.billing_configured:
        raise AuthError(503, "Payments are not configured yet.", "not_configured")
    return auth.settings


Enabled = Annotated[Settings, Depends(billing_enabled)]


def credit(auth: AuthService, user_id: str, cents: int, reason: str, ref: str) -> None:
    # The ledger is the balance source of truth. One atomic write per grant means
    # retries after a crash cannot lose money or add it twice.
    try:
        auth.db.credit_ledger.update_one(
            {"_id": f"{reason}:{ref}"},
            {
                "$setOnInsert": {
                    "user_id": user_id,
                    "delta": cents,
                    "reason": reason,
                    "ref": ref,
                    "at": now(),
                }
            },
            upsert=True,
        )
    except DuplicateKeyError:
        pass  # Another request inserted the same grant.


def grant_trial(auth: AuthService, user_id: str) -> None:
    """Give the $1 trial once, including across concurrent requests and retries."""
    credit(auth, user_id, TRIAL_CENTS, "trial", user_id)


def grant(auth: AuthService, order_id: str, entity: dict) -> bool:
    """Credit only a captured payment matching our server-priced order."""
    payment = auth.db.payments.find_one({"_id": order_id})
    if payment is None:
        return False
    if (
        not isinstance(entity, dict)
        or not re.fullmatch(r"pay_[a-zA-Z0-9]+", str(entity.get("id", "")))
        or entity.get("order_id") != order_id
        or entity.get("amount") != payment["amount"]
        or entity.get("currency") != payment["currency"]
    ):
        raise AuthError(
            400, "Payment details do not match the order.", "invalid_payment"
        )
    if entity.get("status") != "captured":
        raise AuthError(
            409,
            "Payment has not been captured yet. Check again shortly.",
            "payment_pending",
        )
    credit(auth, payment["user_id"], payment["credit"], "topup", order_id)
    auth.db.payments.update_one(
        {"_id": order_id, "status": "created"},
        {"$set": {"status": "paid", "payment_id": entity["id"], "paid_at": now()}},
    )
    return True


def balance(auth: AuthService, user_id: str) -> dict:
    totals = list(
        auth.db.credit_ledger.aggregate(
            [
                {"$match": {"user_id": user_id}},
                {"$group": {"_id": None, "balance": {"$sum": "$delta"}}},
            ]
        )
    )
    return {
        "balance_cents": totals[0]["balance"] if totals else 0,
        "currency": CURRENCY,
        "trial_cents": TRIAL_CENTS,
    }


class OrderRequest(BaseModel):
    pack: str = Field(pattern=r"^[a-z_0-9]{1,20}$")


class VerifyRequest(BaseModel):
    razorpay_order_id: str = Field(pattern=r"^order_[a-zA-Z0-9]{1,58}$")
    razorpay_payment_id: str = Field(pattern=r"^pay_[a-zA-Z0-9]{1,60}$")
    razorpay_signature: str = Field(pattern=r"^[a-f0-9]{64}$")


@router.get("/plans")
def list_packs(request: Request) -> dict:
    return {
        "enabled": request.app.state.settings.billing_configured,
        "currency": CURRENCY,
        "trial_cents": TRIAL_CENTS,
        "packs": [pack_view(pack) for pack in PACKS.values()],
    }


@router.get("/status")
def status(identity: BrowserUser, auth: Service) -> dict:
    grant_trial(auth, identity[0]["_id"])
    return balance(auth, identity[0]["_id"])


@router.post("/order")
def create_order(
    body: OrderRequest, identity: BrowserUser, auth: Service, settings: Enabled
) -> dict:
    pack = PACKS.get(body.pack)
    if pack is None:
        raise AuthError(404, "Unknown credit pack.", "unknown_pack")
    user = identity[0]
    auth.limit(f"order:{user['_id']}", 10, 600)
    order = razorpay_post(
        settings,
        "/orders",
        {
            "amount": pack["price"],
            "currency": CURRENCY,
            "receipt": secrets.token_hex(12),
            "notes": {"user_id": user["_id"], "pack": pack["id"]},
        },
    )
    order_id = order.get("id")
    if (
        not isinstance(order_id, str)
        or not re.fullmatch(r"order_[a-zA-Z0-9]{1,58}", order_id)
        or order.get("amount") != pack["price"]
        or order.get("currency") != CURRENCY
    ):
        raise AuthError(
            502, "Payments returned an unexpected order.", "payments_unavailable"
        )
    auth.db.payments.insert_one(
        {
            "_id": order_id,
            "user_id": user["_id"],
            "pack": pack["id"],
            "amount": pack["price"],
            "credit": pack["price"] + pack["bonus"],
            "currency": CURRENCY,
            "status": "created",
            "created_at": now(),
        }
    )
    return {
        "key_id": settings.razorpay_key_id,
        "order_id": order_id,
        "amount": pack["price"],
        "currency": CURRENCY,
        "name": f"Dark credits ${pack['price'] // 100}",
        "email": user["email"],
    }


@router.post("/verify")
def verify_payment(
    body: VerifyRequest, identity: BrowserUser, auth: Service, settings: Enabled
) -> dict:
    expected = sign(
        settings.razorpay_key_secret,
        f"{body.razorpay_order_id}|{body.razorpay_payment_id}".encode(),
    )
    if not hmac.compare_digest(expected, body.razorpay_signature):
        raise AuthError(400, "Payment could not be verified.", "invalid_signature")
    owned = auth.db.payments.find_one(
        {"_id": body.razorpay_order_id, "user_id": identity[0]["_id"]}
    )
    if owned is None:
        raise AuthError(404, "Order was not found.", "unknown_order")
    entity = razorpay_get(settings, f"/payments/{body.razorpay_payment_id}")
    if entity.get("id") != body.razorpay_payment_id:
        raise AuthError(
            502, "Payments returned an unexpected payment.", "payments_unavailable"
        )
    grant(auth, body.razorpay_order_id, entity)
    return balance(auth, identity[0]["_id"])


@router.post("/webhook")
async def webhook(request: Request, auth: Service, settings: Enabled) -> dict:
    """Razorpay calls this when a payment is captured, even if the browser closed."""
    if not settings.razorpay_webhook_secret:
        raise AuthError(503, "Webhook is not configured.", "not_configured")
    raw = await request.body()
    given = request.headers.get("x-razorpay-signature", "")
    if not re.fullmatch(r"[a-f0-9]{64}", given) or not hmac.compare_digest(
        sign(settings.razorpay_webhook_secret, raw), given
    ):
        raise AuthError(400, "Invalid signature.", "invalid_signature")
    try:
        event = json.loads(raw)
        if not isinstance(event, dict):
            raise TypeError("Expected an event object")
        if event.get("event") in ("payment.captured", "order.paid"):
            entity = event["payload"]["payment"]["entity"]
            grant(auth, entity["order_id"], entity)
    except (ValueError, KeyError, TypeError):
        raise AuthError(400, "Invalid payment event.", "invalid_event") from None
    return {"ok": True}
