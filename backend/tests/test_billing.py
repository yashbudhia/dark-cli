import json

import mongomock
import pytest
from app import billing
from app.auth import COOKIE_NAME, now
from app.main import create_app
from app.settings import Settings
from fastapi.testclient import TestClient
from pymongo.errors import AutoReconnect

SECRET = "rzp-test-secret"
WEBHOOK = "rzp-webhook-secret"


@pytest.fixture
def api(monkeypatch):
    db = mongomock.MongoClient(tz_aware=True).dark
    settings = Settings(
        auth_secret="billing-test-only-secret-" * 3,
        razorpay_key_id="rzp_test_key",
        razorpay_key_secret=SECRET,
        razorpay_webhook_secret=WEBHOOK,
    )
    calls = []

    def fake_post(config, path, body):
        calls.append((path, body))
        return {"id": "order_TEST123456", "amount": body["amount"], "currency": "USD"}

    def fake_get(config, path):
        payment = db.payments.find_one({"_id": "order_TEST123456"})
        return {
            "id": "pay_TEST123456",
            "order_id": payment["_id"],
            "amount": payment["amount"],
            "currency": "USD",
            "status": "captured",
        }

    monkeypatch.setattr(billing, "razorpay_post", fake_post)
    monkeypatch.setattr(billing, "razorpay_get", fake_get)
    with TestClient(create_app(settings, database=db)) as client:
        db.users.insert_one(
            {"_id": "buyer", "email": "buyer@example.com", "created_at": now()}
        )
        token, _ = client.app.state.auth.issue_session("buyer", "web", "Browser")
        headers = {"Cookie": f"{COOKIE_NAME}={token}", "Origin": settings.web_url}
        yield client, db, headers, calls


def signature(order="order_TEST123456", payment="pay_TEST123456", secret=SECRET):
    return billing.sign(secret, f"{order}|{payment}".encode())


def pay(client, headers, **overrides):
    body = {
        "razorpay_order_id": "order_TEST123456",
        "razorpay_payment_id": "pay_TEST123456",
        "razorpay_signature": signature(),
        **overrides,
    }
    return client.post("/api/billing/verify", headers=headers, json=body)


def balance(client, headers):
    return client.get("/api/billing/status", headers=headers).json()["balance_cents"]


def order(client, headers, pack="topup_10"):
    return client.post("/api/billing/order", headers=headers, json={"pack": pack})


def test_new_account_gets_one_dollar_trial_once(api):
    client, db, headers, _ = api
    assert balance(client, headers) == 100
    assert balance(client, headers) == 100
    assert db.credit_ledger.count_documents({"reason": "trial"}) == 1


def test_order_is_priced_by_the_server(api):
    client, db, headers, calls = api
    response = order(client, headers)
    assert response.status_code == 200, response.text
    assert (
        response.json()["amount"] == 1000
        and response.json()["key_id"] == "rzp_test_key"
    )
    assert calls[0][1]["amount"] == 1000 and calls[0][1]["currency"] == "USD"
    assert db.payments.find_one({"_id": "order_TEST123456"})["credit"] == 1500
    assert order(client, headers, "bogus").status_code == 404


def test_ten_dollar_recharge_adds_five_free_and_replay_adds_nothing(api):
    client, _db, headers, _ = api
    order(client, headers)
    first = pay(client, headers)
    assert first.status_code == 200
    assert first.json()["balance_cents"] == 1500
    assert pay(client, headers).json()["balance_cents"] == first.json()["balance_cents"]


def test_five_dollar_pack_has_no_bonus(api):
    client, _db, headers, _ = api
    order(client, headers, "topup_5")
    assert pay(client, headers).json()["balance_cents"] == 500


def test_forged_signature_is_rejected(api):
    client, db, headers, _ = api
    order(client, headers)
    bad = pay(client, headers, razorpay_signature=signature(secret="wrong"))
    assert bad.status_code == 400
    assert db.credit_ledger.count_documents({"reason": "topup"}) == 0


def test_another_account_cannot_claim_the_order(api):
    client, db, headers, _ = api
    order(client, headers)
    db.users.insert_one({"_id": "thief", "email": "t@example.com", "created_at": now()})
    token, _ = client.app.state.auth.issue_session("thief", "web", "Browser")
    other = {**headers, "Cookie": f"{COOKIE_NAME}={token}"}
    assert pay(client, other).status_code == 404


def test_webhook_credits_with_valid_signature_only(api):
    client, _db, headers, _ = api
    order(client, headers)
    event = json.dumps(
        {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_TEST123456",
                        "order_id": "order_TEST123456",
                        "amount": 1000,
                        "currency": "USD",
                        "status": "captured",
                    }
                }
            },
        }
    ).encode()
    forged = client.post(
        "/api/billing/webhook",
        content=event,
        headers={"x-razorpay-signature": "0" * 64},
    )
    assert forged.status_code == 400
    ok = client.post(
        "/api/billing/webhook",
        content=event,
        headers={"x-razorpay-signature": billing.sign(WEBHOOK, event)},
    )
    assert ok.status_code == 200
    assert billing.balance(client.app.state.auth, "buyer")["balance_cents"] == 1500


def test_checkout_reports_unconfigured_payments():
    db = mongomock.MongoClient(tz_aware=True).dark
    settings = Settings(auth_secret="billing-test-only-secret-" * 3)
    with TestClient(create_app(settings, database=db)) as client:
        body = client.get("/api/billing/plans").json()
        assert body["enabled"] is False and body["trial_cents"] == 100
        assert [pack["credit"] for pack in body["packs"]] == [500, 1500]


@pytest.mark.parametrize(
    "change, expected",
    [
        ({"status": "authorized"}, 409),
        ({"status": "failed"}, 409),
        ({"amount": 1}, 400),
        ({"currency": "INR"}, 400),
        ({"order_id": "order_other"}, 400),
    ],
)
def test_signed_checkout_requires_matching_captured_payment(
    api, monkeypatch, change, expected
):
    client, db, headers, _ = api
    order(client, headers)
    monkeypatch.setattr(
        billing,
        "razorpay_get",
        lambda *_: {
            "id": "pay_TEST123456",
            "order_id": "order_TEST123456",
            "amount": 1000,
            "currency": "USD",
            "status": "captured",
            **change,
        },
    )
    assert pay(client, headers).status_code == expected
    assert db.credit_ledger.count_documents({"reason": "topup"}) == 0


@pytest.mark.parametrize("collection", ["payments", "credit_ledger"])
def test_interrupted_credit_grant_can_be_retried_without_loss_or_double_credit(
    api, monkeypatch, collection
):
    client, db, headers, _ = api
    order(client, headers)
    original = db[collection].update_one
    failed = False

    def interrupted(*args, **kwargs):
        nonlocal failed
        if not failed:
            failed = True
            raise AutoReconnect("synthetic interrupted write")
        return original(*args, **kwargs)

    monkeypatch.setattr(db[collection], "update_one", interrupted)
    assert pay(client, headers).status_code == 503
    assert pay(client, headers).json()["balance_cents"] == 1500
    assert pay(client, headers).json()["balance_cents"] == 1500
    assert db.credit_ledger.count_documents({"reason": "topup"}) == 1
    assert db.payments.find_one({"_id": "order_TEST123456"})["status"] == "paid"


def test_concurrent_trial_grants_add_one_credit_entry(api):
    from concurrent.futures import ThreadPoolExecutor

    client, db, _, _ = api
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(
            pool.map(
                lambda _: billing.grant_trial(client.app.state.auth, "buyer"), range(8)
            )
        )
    assert billing.balance(client.app.state.auth, "buyer")["balance_cents"] == 100
    assert db.credit_ledger.count_documents({"reason": "trial"}) == 1


@pytest.mark.parametrize("event", [[], {"event": "payment.captured", "payload": {}}])
def test_malformed_signed_webhook_returns_controlled_error(api, event):
    client, _, _, _ = api
    raw = json.dumps(event).encode()
    response = client.post(
        "/api/billing/webhook",
        content=raw,
        headers={
            "x-razorpay-signature": billing.sign(WEBHOOK, raw),
        },
    )
    assert response.status_code == 400
