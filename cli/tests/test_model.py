import json

import httpx
import pytest

from dark_cli.agent import Agent, ModelConfig
from dark_cli.model import (
    APIConnectionError,
    APIStatusError,
    AuthenticationError,
    ModelClient,
    RateLimitError,
)


def events(*items):
    return "".join(f"data: {json.dumps(item)}\n\n" for item in items) + "data: [DONE]\n\n"


def client(handler):
    return ModelClient(
        api_key="test-key",
        base_url="https://model.example/v1",
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.asyncio
async def test_streamed_text_and_tool_call_fragments_reach_the_agent(tmp_path):
    requests = []

    def handler(request):
        requests.append(request)
        body = ": keep-alive\n\n" + events(
            {"choices": [{"delta": {"content": "Hel", "reasoning_content": "think"}}]},
            {
                "choices": [
                    {
                        "delta": {
                            "content": "lo",
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call-1",
                                    "function": {"name": "read_file", "arguments": '{"pa'},
                                }
                            ],
                        }
                    }
                ]
            },
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [{"index": 0, "function": {"arguments": 'th": "a"}'}}]
                        }
                    }
                ]
            },
            {"choices": [], "usage": {"total_tokens": 3}},
        )
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    agent = Agent(
        ModelConfig("https://model.example/v1", "test", "test-key"),
        tmp_path,
        client=client(handler),
    )
    message = await agent.completion([{"role": "user", "content": "hi"}], [])
    assert message["content"] == "Hello"
    assert message["reasoning_content"] == "think"
    assert message["tool_calls"][0]["id"] == "call-1"
    assert json.loads(message["tool_calls"][0]["function"]["arguments"]) == {"path": "a"}
    request = requests[0]
    assert request.url == "https://model.example/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer test-key"
    assert json.loads(request.content)["stream"] is True


@pytest.mark.asyncio
async def test_single_completion_reads_message_content(tmp_path):
    def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": "Quantity is -2"}}]})

    agent = Agent(
        ModelConfig("https://model.example/v1", "test", "test-key"),
        tmp_path,
        client=client(handler),
    )
    assert (
        await agent.describe_image("data:image/png;base64,abc", "What quantity?")
        == "Quantity is -2"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "error"),
    [
        (401, AuthenticationError),
        (403, AuthenticationError),
        (429, RateLimitError),
        (500, APIStatusError),
    ],
)
async def test_provider_errors_keep_their_meaning(status, error):
    def handler(request):
        return httpx.Response(status, json={"error": {"message": "provider said no"}})

    with pytest.raises(error, match="provider said no") as raised:
        await client(handler).chat.completions.create(model="m", messages=[], stream=True)
    assert raised.value.status_code == status


@pytest.mark.asyncio
async def test_error_inside_a_stream_is_raised_not_ignored():
    def handler(request):
        return httpx.Response(
            200, text=events({"error": {"code": 502, "message": "upstream failed"}})
        )

    stream = await client(handler).chat.completions.create(model="m", messages=[], stream=True)
    with pytest.raises(APIStatusError, match="upstream failed"):
        async with stream:
            async for _ in stream:
                pass


@pytest.mark.asyncio
async def test_unreachable_provider_is_a_connection_error():
    def handler(request):
        raise httpx.ConnectError("offline", request=request)

    with pytest.raises(APIConnectionError):
        await client(handler).chat.completions.create(model="m", messages=[], stream=True)


@pytest.mark.asyncio
async def test_provider_cannot_echo_a_credential_in_an_error():
    def handler(request):
        return httpx.Response(400, json={"error": {"message": "Invalid key test-key"}})

    with pytest.raises(APIStatusError) as raised:
        await client(handler).chat.completions.create(model="m", messages=[], stream=True)
    assert "test-key" not in str(raised.value)
    assert "[redacted]" in str(raised.value)


@pytest.mark.asyncio
async def test_incomplete_stream_does_not_execute_a_partial_tool_call(tmp_path):
    def handler(request):
        body = events(
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call-1",
                                    "function": {
                                        "name": "write_file",
                                        "arguments": '{"path":"unsafe","content":"x"}',
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
        ).replace("data: [DONE]\n\n", "")
        return httpx.Response(200, text=body)

    agent = Agent(
        ModelConfig("https://model.example/v1", "test", "test-key"),
        tmp_path,
        client=client(handler),
    )
    with pytest.raises(APIConnectionError, match="before completion"):
        await agent.turn("write a file")
    assert not (tmp_path / "unsafe").exists()
