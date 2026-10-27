import asyncio
import json
from contextlib import AsyncExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from typer.testing import CliRunner

from dark_cli.agent import Agent, AgentError, ModelConfig, clean
from dark_cli.cli import app


def chunk(content=None, call=None, reasoning=None):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(
                    content=content,
                    tool_calls=[call] if call else None,
                    reasoning_content=reasoning,
                )
            )
        ]
    )


def call_fragment(name=None, arguments=None, identifier=None, index=0):
    return SimpleNamespace(
        index=index, id=identifier, function=SimpleNamespace(name=name, arguments=arguments)
    )


class Stream:
    def __init__(self, items):
        self.items = items

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    def __aiter__(self):
        return self.iterate()

    async def iterate(self):
        for item in self.items:
            yield item


def fake_client(*streams):
    create = AsyncMock(side_effect=[Stream(s) for s in streams])
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


@pytest.mark.asyncio
async def test_streamed_tool_arguments_execute_and_observations_return_to_model(tmp_path):
    events = []
    client = fake_client(
        [
            chunk(reasoning="private model reasoning"),
            chunk(call=call_fragment("write_file", '{"path":"hello.txt",', "call_1")),
            chunk(call=call_fragment(arguments='"content":"hello agent"}')),
        ],
        [chunk("Created "), chunk("hello.txt.")],
    )
    agent = Agent(
        ModelConfig("https://model.example/v1", "test", "test-key"),
        tmp_path,
        event=lambda kind, value: events.append((kind, value)),
        client=client,
    )
    await agent.turn("Create hello.txt")
    assert (tmp_path / "hello.txt").read_text() == "hello agent"
    assert agent.steps == 1
    second = client.chat.completions.create.call_args_list[1].kwargs["messages"]
    assert second[-1]["role"] == "tool"
    assert json.loads(second[-1]["content"])["written"] == str(tmp_path / "hello.txt")
    assert second[-2]["reasoning_content"] == "private model reasoning"
    assert not any("private model reasoning" in str(value) for _, value in events)
    assert ("text", "Created hello.txt.") in events


@pytest.mark.asyncio
async def test_bad_arguments_and_unknown_tools_cannot_modify_files(tmp_path):
    original = set(tmp_path.iterdir())
    client = fake_client(
        [
            chunk(call=call_fragment("write_file", "[]", "bad")),
        ],
        [chunk(call=call_fragment("invented_tool", "{}", "unknown"))],
        [chunk("I could not execute those tools.")],
    )
    agent = Agent(
        ModelConfig("https://model.example/v1", "test", "test-key"), tmp_path, client=client
    )
    await agent.turn("task")
    assert set(tmp_path.iterdir()) == original
    errors = [json.loads(m["content"])["error"] for m in agent.messages if m["role"] == "tool"]
    assert len(errors) == 2 and "Unknown tool" in errors[-1]


@pytest.mark.asyncio
async def test_file_tools_reject_parent_paths_and_credentials(tmp_path):
    agent = Agent(ModelConfig("https://model.example/v1", "test", "test-key"), tmp_path)
    async with AsyncExitStack() as stack:
        for path in ("../outside.txt", ".env", ".git/config"):
            with pytest.raises(AgentError):
                await agent.tool("write_file", {"path": path, "content": "bad"}, stack)
    assert not (tmp_path.parent / "outside.txt").exists()


@pytest.mark.asyncio
async def test_cancellation_preserves_action_context_and_next_turn_works(tmp_path):
    started = asyncio.Event()
    client = fake_client(
        [chunk(call=call_fragment("run_command", '{"command":"long task"}', "call_1"))],
        [chunk("Next turn works.")],
    )
    agent = Agent(
        ModelConfig("https://model.example/v1", "test", "test-key"), tmp_path, client=client
    )

    async def waiting(*_):
        started.set()
        await asyncio.sleep(60)

    agent.shell = waiting
    task = asyncio.create_task(agent.turn("long task"))
    await asyncio.wait_for(started.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    result = next(m for m in agent.messages if m["role"] == "tool")
    assert json.loads(result["content"])["outcome"] == "unknown"
    await agent.turn("new question")
    assert agent.messages[-1]["content"] == "Next turn works."


@pytest.mark.asyncio
async def test_timed_out_command_is_not_retried(tmp_path):
    client = fake_client(
        [chunk(call=call_fragment("run_command", '{"command":"mutation"}', "call_1"))],
        [chunk("The outcome is unknown.")],
    )
    agent = Agent(
        ModelConfig("https://model.example/v1", "test", "test-key"), tmp_path, client=client
    )
    agent.shell = AsyncMock(side_effect=TimeoutError)
    await agent.turn("task")
    agent.shell.assert_awaited_once()
    result = next(m for m in agent.messages if m["role"] == "tool")
    assert json.loads(result["content"])["outcome"] == "unknown"


@pytest.mark.asyncio
async def test_real_shell_captures_output_and_exit_code(tmp_path):
    agent = Agent(ModelConfig("https://model.example/v1", "test", "test-key"), tmp_path)
    result = await agent.shell("echo dark-agent-test", 5)
    assert result["exit_code"] == 0 and "dark-agent-test" in result["output"]


def test_default_cli_opens_chat_instead_of_help(monkeypatch):
    from dark_cli import chat

    calls = []
    monkeypatch.setattr(chat, "launch", lambda *args: calls.append(args))
    result = CliRunner().invoke(app, [])
    assert result.exit_code == 0 and calls == [()]
    assert "Usage:" not in result.output


def test_slash_help_and_exit_do_not_need_a_model_key(monkeypatch):
    from dark_cli import chat

    monkeypatch.setattr(
        chat.ModelConfig, "load", lambda: ModelConfig("https://model.example/v1", "test")
    )
    result = CliRunner().invoke(app, [], input="/help\n/exit\n")
    assert result.exit_code == 0
    assert (
        "/login" in result.output
        and "/provider" in result.output
        and "Type a task" in result.output
    )


def test_terminal_output_redacts_keys_and_control_sequences(monkeypatch):
    monkeypatch.setenv("DARK_API_KEY", "synthetic-private-key")
    assert clean("\x1b[31mhello synthetic-private-key\x1b[0m") == "hello [redacted]"


def test_model_settings_do_not_write_keys_to_preferences(monkeypatch, tmp_path):
    from dark_cli.auth import Credentials

    saved = {}
    backend = SimpleNamespace(set_password=lambda service, user, key: saved.update({service: key}))
    monkeypatch.setattr(Credentials, "backend", lambda: backend)
    config = ModelConfig("https://model.example/v1", "test", "synthetic-private-key")
    config.save()
    from dark_cli.config import settings_path

    text = settings_path().with_name("model.json").read_text()
    assert "synthetic-private-key" not in text
    assert saved["dark-cli:model:https://model.example/v1"] == "synthetic-private-key"


def test_update_command_hands_control_to_npm_launcher(monkeypatch):
    from dark_cli import chat

    monkeypatch.setenv("DARK_NPM_LAUNCHER", "test-launcher")
    monkeypatch.setattr(
        chat.ModelConfig, "load", lambda: ModelConfig("https://model.example/v1", "test")
    )
    runner = CliRunner()
    assert runner.invoke(app, ["update"]).exit_code == 85
    assert runner.invoke(app, [], input="/update\n").exit_code == 85


def test_invalid_saved_model_configuration_can_be_repaired_in_chat(monkeypatch):
    from dark_cli import chat

    def invalid():
        raise AgentError("Model settings are unreadable. Use /provider.")

    monkeypatch.setattr(chat.ModelConfig, "load", invalid)
    result = CliRunner().invoke(app, [], input="/help\n/exit\n")
    assert result.exit_code == 0 and "/provider" in result.output


@pytest.mark.asyncio
async def test_image_tool_sends_image_and_question_to_vision_model(tmp_path):
    image = tmp_path / "fixture.png"
    image.write_bytes(b"synthetic-image-bytes")
    create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Quantity is -2"))]
        )
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    agent = Agent(
        ModelConfig("https://model.example/v1", "vision-test", "test-key"), tmp_path, client=client
    )
    async with AsyncExitStack() as stack:
        result = await agent.tool(
            "view_image", {"path": "fixture.png", "question": "What quantity?"}, stack
        )
    assert result["description"] == "Quantity is -2"
    content = create.call_args.kwargs["messages"][0]["content"]
    assert "What quantity?" in content[0]["text"]
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
