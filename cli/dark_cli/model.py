"""A minimal client for OpenAI-compatible chat completion APIs.

The OpenAI SDK imports thousands of type modules, which takes seconds on Windows. Dark
uses only streamed and single chat completions, so it calls the HTTP API directly.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import httpx

from . import __version__


class ModelError(Exception):
    pass


class APIConnectionError(ModelError):
    pass


class APIStatusError(ModelError):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


class AuthenticationError(APIStatusError):
    pass


class RateLimitError(APIStatusError):
    pass


class Fields(dict):
    """A JSON object read by attribute. Absent fields are None, as in SDK models."""

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return self.get(name)


def fields(value: Any) -> Any:
    if isinstance(value, dict):
        return Fields((key, fields(item)) for key, item in value.items())
    if isinstance(value, list):
        return [fields(item) for item in value]
    return value


def status_error(status: int, body: Any, fallback: str, secret: str = "") -> APIStatusError:
    error = body.get("error") if isinstance(body, dict) else None
    message = error.get("message") if isinstance(error, dict) else error
    kind = {401: AuthenticationError, 403: AuthenticationError, 429: RateLimitError}
    text = str(message or fallback)
    if secret:
        text = text.replace(secret, "[redacted]")
    return kind.get(status, APIStatusError)(status, text[:500])


def response_error(response: httpx.Response, secret: str = "") -> APIStatusError:
    try:
        body = response.json()
    except ValueError:
        body = None
    return status_error(
        response.status_code, body, response.reason_phrase or "Request failed", secret
    )


class Stream:
    """Streamed completion chunks: use with `async with`, then iterate."""

    def __init__(self, response: httpx.Response, secret: str = ""):
        self.response = response
        self.secret = secret

    async def __aenter__(self) -> Stream:
        return self

    async def __aexit__(self, *_) -> None:
        await self.response.aclose()

    async def __aiter__(self) -> AsyncIterator[Any]:
        received = 0
        try:
            async for line in self.response.aiter_lines():
                received += len(line)
                if received > 2_000_000:
                    raise ModelError("The model stream exceeded the response limit.")
                # Blank separators, comments and keep-alives carry no data.
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    return
                try:
                    event = json.loads(data)
                except ValueError as exc:
                    raise ModelError("The model provider sent an unreadable stream.") from exc
                if isinstance(event, dict) and event.get("error"):
                    code = event["error"].get("code") if isinstance(event["error"], dict) else None
                    raise status_error(
                        code if type(code) is int else 502, event, "Stream failed", self.secret
                    )
                yield fields(event)
            # A silently closed connection may contain only part of a tool call.
            raise APIConnectionError(
                "The model stream ended before completion. No tools from this response were run."
            )
        except httpx.HTTPError as exc:
            raise APIConnectionError("The model stream was interrupted.") from exc


class Completions:
    def __init__(self, http: httpx.AsyncClient):
        self.http = http
        self.secret = http.headers.get("Authorization", "").removeprefix("Bearer ")

    async def create(self, **body: Any) -> Any:
        try:
            request = self.http.build_request("POST", "chat/completions", json=body)
            response = await self.http.send(request, stream=bool(body.get("stream")))
            if response.is_error:
                await response.aread()
                await response.aclose()
                raise response_error(response, self.secret)
            if body.get("stream"):
                return Stream(response, self.secret)
            return fields(response.json())
        except httpx.HTTPError as exc:
            raise APIConnectionError("Cannot reach the model provider.") from exc
        except ValueError as exc:
            raise ModelError("The model provider returned an unreadable response.") from exc


class ModelClient:
    """The `client.chat.completions.create(...)` subset of the OpenAI SDK."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        timeout: float = 60,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.http = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}", "User-Agent": f"dark-cli/{__version__}"},
            timeout=httpx.Timeout(timeout, connect=10),
            transport=transport,
        )
        self.chat = SimpleNamespace(completions=Completions(self.http))

    async def models(self) -> list[dict]:
        """The provider's models, from the OpenAI-compatible /models endpoint."""
        try:
            response = await self.http.get("models")
            if response.is_error:
                raise response_error(response, self.chat.completions.secret)
            data = response.json().get("data")
        except httpx.HTTPError as exc:
            raise APIConnectionError("Cannot reach the model provider.") from exc
        except (ValueError, AttributeError) as exc:
            raise ModelError("The model provider returned an unreadable model list.") from exc
        if not isinstance(data, list):
            raise ModelError("The model provider returned an unreadable model list.")
        return [
            item
            for item in data
            if isinstance(item, dict)
            and isinstance(item.get("id"), str)
            and re.fullmatch(r"[\w./:-]{1,160}", item["id"])
        ]

    async def close(self) -> None:
        await self.http.aclose()
