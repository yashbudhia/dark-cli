"""HTTP boundary for browser sign-in and CLI device authorization."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field, StrictBool, field_validator
from pymongo.errors import PyMongoError

from .auth import COOKIE_NAME, AuthError, AuthService, now, public_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


def service(request: Request) -> AuthService:
    auth = request.app.state.auth
    if auth is None:
        raise AuthError(503, "Sign-in is not configured yet.", "not_configured")
    return auth


Service = Annotated[AuthService, Depends(service)]


def browser_origin(request: Request) -> None:
    if request.headers.get("origin") != request.app.state.settings.web_url:
        raise AuthError(
            403, "Open this page on the Dark website to continue.", "invalid_origin"
        )


def principal(request: Request, auth: Service) -> tuple[dict, dict]:
    authorization = request.headers.get("authorization", "")
    if authorization:
        if not authorization.startswith("Bearer "):
            raise AuthError(401, "Invalid authorization header.")
        return auth.authenticate(authorization[7:], "cli")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        browser_origin(request)
    return auth.authenticate(request.cookies.get(COOKIE_NAME, ""), "web")


Principal = Annotated[tuple[dict, dict], Depends(principal)]


def browser_user(request: Request, auth: Service) -> tuple[dict, dict]:
    if request.method != "GET":
        browser_origin(request)
    return auth.authenticate(request.cookies.get(COOKIE_NAME, ""), "web")


BrowserUser = Annotated[tuple[dict, dict], Depends(browser_user)]


def client_ip(request: Request) -> str:
    # Trust only the ASGI server's peer address, never caller-supplied forwarded headers.
    return request.client.host if request.client else "unknown"


class EmailRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class VerifyRequest(BaseModel):
    challenge_id: str = Field(min_length=20, max_length=128)
    code: str = Field(pattern=r"^[0-9]{8}$")


class DeviceRequest(BaseModel):
    poll_interval: int = Field(default=5, ge=2, le=5, strict=True)
    name: str = Field(
        default="Dark CLI", min_length=1, max_length=80, pattern=r"^[^\x00-\x1f\x7f]+$"
    )

    @field_validator("name")
    @classmethod
    def meaningful_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Computer name must not be empty")
        return value


class PollRequest(BaseModel):
    device_code: str = Field(min_length=20, max_length=128)


class DecisionRequest(BaseModel):
    user_code: str = Field(min_length=8, max_length=12)
    approve: StrictBool


@router.get("/readiness")
def readiness(request: Request, response: Response) -> dict:
    config = request.app.state.settings
    auth = request.app.state.auth
    reachable = False
    if auth is not None:
        try:
            reachable = auth.db.command("ping").get("ok") == 1
        except PyMongoError:
            pass
    checks = {
        "database_configured": bool(config.mongo_uri or auth is not None),
        "auth_secret_configured": len(config.auth_secret) >= 32,
        "email_configured": config.email_configured,
        "mongodb_reachable": reachable,
    }
    ready = all(checks.values()) and auth is not None
    response.status_code = 200 if ready else 503
    return {"ready": ready, "checks": checks, "email_delivery_verified": False}


@router.post("/email/request", dependencies=[Depends(browser_origin)])
def request_email(body: EmailRequest, request: Request, auth: Service) -> dict:
    return auth.request_email(body.email, client_ip(request))


@router.post("/email/verify", dependencies=[Depends(browser_origin)])
def verify_email(
    body: VerifyRequest, request: Request, response: Response, auth: Service
) -> dict:
    user, token = auth.verify_email(body.challenge_id, body.code, client_ip(request))
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=7 * 86400,
        httponly=True,
        secure=auth.settings.secure_cookie,
        samesite="lax",
        path="/api",
    )
    return {"user": user}


@router.get("/me")
def me(identity: Principal) -> dict:
    user, session = identity
    return {
        "user": public_user(user),
        "session": {"kind": session["kind"], "expires_at": session["expires_at"]},
    }


@router.post("/logout", status_code=204)
def logout(response: Response, identity: Principal, auth: Service) -> None:
    auth.db.sessions.delete_one({"_id": identity[1]["_id"]})
    response.delete_cookie(
        COOKIE_NAME,
        path="/api",
        secure=auth.settings.secure_cookie,
        httponly=True,
        samesite="lax",
    )


@router.post("/device/code")
def device_code(body: DeviceRequest, request: Request, auth: Service) -> dict:
    return auth.start_device(
        body.name, client_ip(request), poll_interval=body.poll_interval
    )


@router.post("/device/token")
def device_token(body: PollRequest, auth: Service) -> dict:
    return auth.poll_device(body.device_code)


@router.get("/device")
def device_details(auth: Service, identity: BrowserUser, user_code: str = "") -> dict:
    auth.limit(f"device-lookup:{identity[0]['_id']}", 30, 600)
    return auth.device_info(user_code)


@router.post("/device/decision", status_code=204)
def device_decision(
    body: DecisionRequest, identity: BrowserUser, auth: Service
) -> None:
    auth.limit(f"device-decision:{identity[0]['_id']}", 30, 600)
    auth.decide_device(body.user_code, identity[0]["_id"], body.approve)


@router.get("/devices")
def devices(identity: BrowserUser, auth: Service) -> list[dict]:
    return [
        {key: row[key] for key in ("id", "name", "created_at", "expires_at")}
        for row in auth.db.sessions.find(
            {
                "user_id": identity[0]["_id"],
                "kind": "cli",
                "expires_at": {"$gt": now()},
            }
        ).sort("created_at", -1)
    ]


@router.delete("/devices/{device_id}", status_code=204)
def revoke_device(device_id: str, identity: BrowserUser, auth: Service) -> None:
    result = auth.db.sessions.delete_one(
        {"id": device_id, "user_id": identity[0]["_id"], "kind": "cli"}
    )
    if not result.deleted_count:
        raise AuthError(404, "Connected device was not found.")
