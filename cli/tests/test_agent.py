import asyncio
import json
import os
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


def test_native_store_key_is_redacted_without_an_environment_variable(tmp_path):
    config = ModelConfig("https://model.example/v1", "test", "native-only-credential")
    agent = Agent(config, tmp_path)
    assert agent.clean("provider echoed native-only-credential") == "provider echoed [redacted]"
    assert "native-only-credential" not in repr(config)


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
    for path in ("../outside.txt", ".env", ".git/config"):
        with pytest.raises(AgentError):
            await agent.tool("write_file", {"path": path, "content": "bad"})
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


@pytest.mark.parametrize(("arguments", "resume"), [([], False), (["--resume"], True)])
def test_default_cli_opens_chat_instead_of_help(monkeypatch, arguments, resume):
    from dark_cli import chat

    calls = []
    monkeypatch.setattr(chat, "launch", lambda resume=False: calls.append(resume))
    result = CliRunner().invoke(app, arguments)
    assert result.exit_code == 0 and calls == [resume]
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
    result = await agent.tool("view_image", {"path": "fixture.png", "question": "What quantity?"})
    assert result["description"] == "Quantity is -2"
    system, user = create.call_args.kwargs["messages"]
    assert system["role"] == "system" and "vision helper" in system["content"]
    content = user["content"]
    assert "What quantity?" in content[0]["text"]
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


@pytest.mark.asyncio
async def test_model_connection_is_reused_until_chat_closes(tmp_path, monkeypatch):
    from dark_cli import model

    client = fake_client([chunk("First answer")], [chunk("Second answer")])
    client.close = AsyncMock()
    created = []

    def factory(**kwargs):
        created.append(kwargs)
        return client

    monkeypatch.setattr(model, "ModelClient", factory)
    agent = Agent(ModelConfig("https://model.example/v1", "test", "test-key"), tmp_path)
    await agent.turn("first")
    await agent.turn("second")
    assert len(created) == 1
    client.close.assert_not_awaited()
    await agent.close()
    client.close.assert_awaited_once()


def test_chat_startup_defers_network_and_desktop_libraries():
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import dark_cli.chat; "
            "assert not {'openai', 'httpx', 'mcp'} & set(sys.modules), sorted(sys.modules)",
        ],
        capture_output=True,
        timeout=15,
    )
    assert result.returncode == 0


def test_fast_command_switches_model_and_keeps_slash_session_working(monkeypatch):
    from dark_cli import chat
    from dark_cli.agent import DEFAULT_BASE

    saved = []
    monkeypatch.setattr(
        chat.ModelConfig,
        "load",
        lambda: ModelConfig(DEFAULT_BASE, "glm-5.3-flash-abliterated", "test-key"),
    )
    monkeypatch.setattr(chat.ModelConfig, "save", lambda config: saved.append(config.model))
    result = CliRunner().invoke(app, [], input="/fast\n/model\n/exit\n")
    assert result.exit_code == 0
    assert saved == ["deepseek-v4.1-flash-fast"]
    assert "deepseek-v4.1-flash-fast" in result.output


@pytest.mark.asyncio
async def test_fast_model_retains_supported_vision_model(tmp_path):
    from dark_cli.agent import DEFAULT_BASE, DEFAULT_MODEL

    create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="image observed"))]
        )
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    agent = Agent(
        ModelConfig(DEFAULT_BASE, "deepseek-v4.1-flash-fast", "test-key"), tmp_path, client=client
    )
    await agent.describe_image("data:image/png;base64,abc", "describe")
    assert create.call_args.kwargs["model"] == DEFAULT_MODEL


@pytest.mark.asyncio
async def test_configured_model_key_does_not_bypass_account_login(tmp_path, monkeypatch):
    from dark_cli import chat

    monkeypatch.setattr(chat.Credentials, "get", lambda _: None)
    instance = chat.Chat(tmp_path, ModelConfig("https://model.example/v1", "test", "test-key"))
    instance.agent.turn = AsyncMock()
    assert await instance.execute("hi") is False
    instance.agent.turn.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [200, 401])
async def test_chat_requires_a_server_validated_session(tmp_path, monkeypatch, status):
    import httpx

    from dark_cli import chat

    monkeypatch.setattr(chat.Credentials, "get", lambda _: "test-session-token")
    real = chat.AccountClient
    monkeypatch.setattr(
        chat,
        "AccountClient",
        lambda server: real(
            server,
            httpx.MockTransport(
                lambda request: httpx.Response(
                    status, json={"user": {"email": "test@example.com"}}
                ),
            ),
        ),
    )
    instance = chat.Chat(tmp_path, ModelConfig("https://model.example/v1", "test", "test-key"))
    instance.agent.turn = AsyncMock()
    assert await instance.execute("hi") is (status == 200)
    assert instance.agent.turn.await_count == int(status == 200)


@pytest.mark.asyncio
async def test_revoked_session_blocks_the_next_task(tmp_path, monkeypatch):
    import httpx

    from dark_cli import chat

    checks = []
    monkeypatch.setattr(chat.Credentials, "get", lambda _: "test-session-token")
    real = chat.AccountClient

    def respond(request):
        checks.append(request.url.path)
        return httpx.Response(
            200 if len(checks) == 1 else 401,
            json={"user": {"email": "test@example.com"}},
        )

    monkeypatch.setattr(
        chat, "AccountClient", lambda server: real(server, httpx.MockTransport(respond))
    )
    instance = chat.Chat(tmp_path, ModelConfig("https://model.example/v1", "test", "test-key"))
    instance.agent.turn = AsyncMock()
    assert await instance.execute("first")
    assert not await instance.execute("second")
    assert len(checks) == 2
    assert instance.agent.turn.await_count == 1


@pytest.mark.asyncio
async def test_preparation_never_contacts_the_model_before_login(tmp_path, monkeypatch):
    from dark_cli import chat

    monkeypatch.setattr(chat.Credentials, "get", lambda _: None)
    instance = chat.Chat(tmp_path, ModelConfig("https://model.example/v1", "test", "test-key"))
    await instance.prepare()
    assert instance.agent.client is None


@pytest.mark.asyncio
async def test_desktop_server_stays_connected_across_turns_until_chat_closes(tmp_path, monkeypatch):
    from contextlib import asynccontextmanager

    from dark_cli.desktop import windows

    lifecycle = []
    session = SimpleNamespace(
        list_tools=AsyncMock(
            return_value=SimpleNamespace(
                tools=[SimpleNamespace(name="ui_click", description="Click", inputSchema={})]
            )
        ),
        call_tool=AsyncMock(
            return_value=SimpleNamespace(
                content=[SimpleNamespace(type="text", text="clicked")], isError=False
            )
        ),
    )

    @asynccontextmanager
    async def connect(**_):
        lifecycle.append("open")
        try:
            yield SimpleNamespace(session=session)
        finally:
            lifecycle.append("close")

    monkeypatch.setattr(windows, "connect", connect)
    click = [chunk(call=call_fragment("desktop__ui_click", "{}", "click"))]
    client = fake_client(click, [chunk("Clicked")], click, [chunk("Clicked again")], [chunk("Hi")])
    agent = Agent(
        ModelConfig("https://model.example/v1", "test", "test-key"), tmp_path, client=client
    )
    await agent.turn("click save")
    await agent.turn("click save again")
    assert lifecycle == ["open"]
    assert session.call_tool.await_count == 2
    assert agent.desktop_schemas, "consecutive desktop turns keep the schemas loaded"
    await agent.turn("say hi")
    assert agent.desktop_schemas == [] and lifecycle == ["open"]
    await agent.close()
    assert lifecycle == ["open", "close"]


@pytest.mark.asyncio
@pytest.mark.skipif(os.name != "nt", reason="the overlay is Windows-only")
async def test_overlay_frames_the_window_points_at_controls_and_scans_on_screenshots(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("DARK_NO_OVERLAY")
    written = []
    stdin = SimpleNamespace(write=written.append, drain=AsyncMock(), close=lambda: None)
    agent = Agent(ModelConfig("https://model.example/v1", "test", "test-key"), tmp_path)
    agent.overlay = SimpleNamespace(returncode=None, stdin=stdin)
    agent.remember_points(
        [json.dumps({"items": [{"id": "save-id", "name": "Save", "click": [1115, 751, 0]}]})]
    )
    await agent.show_on_screen("ui_click", {"windowHandle": "42", "elementId": "save-id"})
    await agent.show_on_screen("ui_read", {"windowHandle": "42", "elementId": "save-id"})
    await agent.show_on_screen("screenshot_control", {"windowHandle": "42"})
    commands = [json.loads(line) for line in written]
    assert commands == [
        {"window": "42"},
        {"path": [[1115, 751]]},
        {"window": "42"},
        {"window": "42"},
        {"scan": True},
    ]


@pytest.mark.asyncio
async def test_stopping_the_first_task_leaves_startup_preparation_running(tmp_path):
    from dark_cli import chat

    instance = chat.Chat(tmp_path, ModelConfig("https://model.example/v1", "test", "test-key"))
    instance.require_account = lambda: None
    instance.agent.turn = AsyncMock()
    release = asyncio.Event()
    preparing = asyncio.create_task(release.wait())
    instance.preparing = preparing
    first = asyncio.create_task(instance.execute("first"))
    await asyncio.sleep(0.05)
    first.cancel()
    assert await first is False
    assert not preparing.cancelled()
    assert await instance.execute("second") is True
    release.set()


def test_batches_point_at_each_control_they_act_on(tmp_path):
    agent = Agent(ModelConfig("https://model.example/v1", "test", "test-key"), tmp_path)
    agent.remember_points(
        [
            json.dumps(
                {
                    "tree": [
                        {"id": "q", "automationId": "quantityInput", "click": [900, 700, 0]},
                        {"id": "s", "name": "Save", "click": [1115, 751, 0]},
                    ]
                }
            )
        ]
    )
    steps = [
        {"action": "find", "automationId": "quantityInput", "requireUnique": True},
        {"action": "type", "elementId": "$prev", "text": "-2"},
        {"action": "find", "name": "Save"},
        {"action": "click", "elementId": "$prev"},
        {"action": "find", "name": "Unknown"},
        {"action": "click", "elementId": "$prev"},
        {"action": "key", "key": "enter"},
    ]
    assert agent.batch_path({"steps": json.dumps(steps)}) == [(900, 700), (1115, 751)]
    assert agent.batch_path({"steps": "not json"}) == []


def test_screenshots_go_to_the_vision_model_whichever_model_leads(tmp_path, monkeypatch):
    from dark_cli.agent import DEFAULT_BASE, VISION_MODEL

    monkeypatch.delenv("DARK_VISION_MODEL", raising=False)
    for model in ("deepseek-v4.1-flash-fast", "minimax-m3.1-flash", "glm-5.3-abliterated"):
        agent = Agent(ModelConfig(DEFAULT_BASE, model, "test-key"), tmp_path)
        assert agent.vision_model() == VISION_MODEL
    other = Agent(ModelConfig("https://model.example/v1", "their-model", "test-key"), tmp_path)
    assert other.vision_model() == "their-model"
    monkeypatch.setenv("DARK_VISION_MODEL", "custom-vision")
    assert other.vision_model() == "custom-vision"


def test_chat_saves_each_turn_and_can_resume_it(tmp_path):
    from dark_cli import chat, sessions

    instance = chat.Chat(tmp_path, ModelConfig("https://model.example/v1", "glm-x", "test-key"))
    instance.agent.messages = [
        {"role": "user", "content": "find the bug"},
        {"role": "assistant", "content": "Found it in save()."},
    ]
    first_id = instance.session_id
    instance.save_session()
    assert [entry["id"] for entry in sessions.recent()] == [first_id]

    # A fresh chat lists the saved conversation and resumes it by number.
    other = chat.Chat(tmp_path, ModelConfig("https://model.example/v1", "glm-x", "test-key"))
    other.list_sessions()
    assert other.resume_ids == [first_id]
    other.resume("1")
    assert other.session_id == first_id
    assert other.agent.messages[0]["content"] == "find the bug"


def test_clear_starts_a_new_session_without_erasing_the_saved_one(tmp_path):
    from dark_cli import chat, sessions

    instance = chat.Chat(tmp_path, ModelConfig("https://model.example/v1", "glm-x", "test-key"))
    instance.agent.messages = [{"role": "user", "content": "keep me"}]
    instance.save_session()
    saved_id = instance.session_id
    instance.agent.clear()
    instance.session_id = sessions.new_id()
    assert instance.session_id != saved_id
    assert sessions.load(saved_id) is not None


def test_resume_rejects_an_unknown_number(tmp_path):
    from dark_cli import chat

    instance = chat.Chat(tmp_path, ModelConfig("https://model.example/v1", "glm-x", "test-key"))
    with pytest.raises(AgentError):
        instance.resume("7")


def test_launch_resume_reopens_the_most_recent_conversation(tmp_path):
    from dark_cli import chat

    first = chat.Chat(tmp_path, ModelConfig("https://model.example/v1", "glm-x", "test-key"))
    first.agent.messages = [{"role": "user", "content": "earlier work"}]
    first.save_session()
    later = chat.Chat(tmp_path, ModelConfig("https://model.example/v1", "glm-x", "test-key"))
    later.resume_last()
    assert later.session_id == first.session_id
    assert later.agent.messages[0]["content"] == "earlier work"


def test_resume_does_not_import_another_workspaces_context(tmp_path):
    from dark_cli import chat

    config = ModelConfig("https://model.example/v1", "test", "native-secret")
    first = chat.Chat(tmp_path / "first", config)
    first.agent.messages = [{"role": "user", "content": "work in first"}]
    first.save_session()
    second = chat.Chat(tmp_path / "second", config)
    second.resume_last()
    assert second.agent.messages == []
    assert second.session_id != first.session_id


def test_input_history_redacts_the_current_model_key(tmp_path):
    from dark_cli import chat, sessions

    instance = chat.Chat(tmp_path, ModelConfig("https://model.example/v1", "test", "first-secret"))
    history = instance.history()
    history.store_string("do not store first-secret")
    instance.config = ModelConfig("https://model.example/v1", "test", "second-secret")
    history.store_string("do not store second-secret")
    text = sessions.history_file().read_text(encoding="utf-8")
    assert "first-secret" not in text and "second-secret" not in text
