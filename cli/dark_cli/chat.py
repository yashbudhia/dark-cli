"""Dark's conversational terminal UI, slash commands and cancellable agent turns."""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import signal
import sys
import time
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import DummyHistory, InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from . import __version__
from .agent import BUILTINS, DEFAULT_BASE, DEFAULT_MODEL, Agent, AgentError, ModelConfig, clean

ACCENT = "#00ff88"
COMMANDS = {
    "/help": "Show commands and keyboard shortcuts",
    "/login": "Connect your Dark account in the browser",
    "/logout": "Revoke your account session",
    "/whoami": "Show your connected account",
    "/doctor": "Check the hosted service",
    "/provider": "Set your model endpoint and API key",
    "/model": "Show or change the model: /model <id>",
    "/fast": "Use the lower-latency Refuseless model",
    "/tools": "Show the agent's tools",
    "/desktop": "Run desktop commands: /desktop windows",
    "/runs": "Manage reports: /runs list",
    "/cwd": "Show or change the workspace: /cwd <path>",
    "/clear": "Start a new conversation",
    "/update": "Update the npm CLI and restart Dark",
    "/exit": "Close Dark",
}


class SlashCompleter(Completer):
    def get_completions(self, document, complete_event):
        prefix = document.text_before_cursor
        if prefix.startswith("/") and " " not in prefix and "\n" not in prefix:
            for name, description in COMMANDS.items():
                if name.startswith(prefix):
                    yield Completion(name, start_position=-len(prefix), display_meta=description)


def error_text(exc: Exception) -> str:
    if isinstance(exc, AgentError):
        return clean(str(exc))
    from openai import APIConnectionError, APIStatusError, AuthenticationError, RateLimitError

    if isinstance(exc, AuthenticationError):
        return "The model rejected the API key. Update it with /provider."
    if isinstance(exc, RateLimitError):
        return "The model provider is rate limiting requests or has no remaining credit. Try again shortly."
    if isinstance(exc, APIConnectionError):
        return "Cannot reach the model provider. Check your connection and /provider settings."
    if isinstance(exc, APIStatusError):
        return f"The model provider returned HTTP {exc.status_code}. Check the model ID with /model and endpoint with /provider."
    return clean(str(exc))[:500] or type(exc).__name__


class Chat:
    def __init__(self, root: Path | None = None, config: ModelConfig | None = None):
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(errors="replace")
        self.root = (root or Path.cwd()).resolve()
        self.console = Console(highlight=False)
        try:
            self.config = config or ModelConfig.load()
        except AgentError as exc:
            self.console.print(Text(str(exc), style="yellow"))
            self.config = ModelConfig(DEFAULT_BASE, DEFAULT_MODEL)
        self.live: Live | None = None
        self.text = ""
        self.started = 0.0
        bindings = KeyBindings()

        @bindings.add("escape", "enter")
        def newline(event):
            event.current_buffer.insert_text("\n")

        self.terminal = sys.stdin.isatty() and sys.stdout.isatty()
        self.session = (
            PromptSession(
                history=InMemoryHistory(),
                completer=SlashCompleter(),
                auto_suggest=AutoSuggestFromHistory(),
                key_bindings=bindings,
                style=Style.from_dict(
                    {
                        "prompt": "#00ff88 bold",
                        "bottom-toolbar": "bg:#101914 #81938a",
                        "completion-menu.completion": "bg:#101914 #dce8df",
                        "completion-menu.completion.current": "bg:#00ff88 #07100a",
                    }
                ),
            )
            if self.terminal
            else None
        )
        self.agent = Agent(self.config, self.root, event=self.event, ask=self.ask)

    def banner(self):
        title = Text.assemble(("dark", f"bold {ACCENT}"), (f" / {__version__}", "dim"))
        content = Text.assemble(
            (clean(str(self.root)), "dim"),
            "\n",
            (self.config.model, ACCENT),
            (
                "  ·  model key configured"
                if self.config.key
                else "  ·  /provider to connect a model",
                "dim",
            ),
            "\n\nType a task. Dark will inspect, act, and check the result.\n",
            ("/help", ACCENT),
            (" commands  ·  alt+enter newline  ·  ctrl+c stop  ·  ctrl+d exit", "dim"),
        )
        self.console.print(
            Panel(content, title=title, title_align="left", border_style="#294535", padding=(1, 2))
        )

    async def input(self, label="❯ ", password=False, default="") -> str:
        if not self.terminal:
            if password:
                raise AgentError(
                    "Use /provider from an interactive terminal to enter a key securely."
                )
            line = sys.stdin.readline()
            if not line:
                raise EOFError
            return line.rstrip("\n")
        if password:
            return await PromptSession(history=DummyHistory()).prompt_async(label, is_password=True)
        if label != "❯ ":
            return await PromptSession(history=DummyHistory()).prompt_async(label, default=default)
        return await self.session.prompt_async(
            [("class:prompt", label)],
            complete_while_typing=True,
            bottom_toolbar=f" {self.config.model}  ·  /help  ·  {self.root.name} ",
        )

    async def ask(self, question: str) -> str:
        self.event("response_end", None)
        self.console.print(Text(question, style="bold"))
        return await self.input("answer › ")

    def event(self, kind, value):
        if kind == "thinking":
            self.text = ""
            if self.terminal:
                self.live = Live(
                    Spinner("dots", text="Thinking…", style=ACCENT),
                    console=self.console,
                    transient=True,
                    refresh_per_second=12,
                )
                self.live.start()
        elif kind == "text":
            self.text = value
            if self.live:
                self.live.update(Markdown(value))
        elif kind == "response_end":
            if self.live:
                self.live.stop()
                self.live = None
            if self.text:
                self.console.print(Markdown(self.text))
                self.console.print()
                self.text = ""
        elif kind == "tool_start":
            self.started = time.monotonic()
            name, args = value["name"], value["arguments"]
            summary = (
                args.get("command")
                or args.get("path")
                or args.get("question")
                or json.dumps(args, ensure_ascii=False)
            )
            self.console.print(
                Text.assemble(
                    ("● ", ACCENT),
                    (name.removeprefix("desktop__"), "bold"),
                    ("  " + clean(str(summary))[:180], "dim"),
                )
            )
        elif kind == "tool_end":
            error = value.get("error") or value.get("exit_code", 0)
            output = (
                value.get("output")
                or value.get("content")
                or value.get("result")
                or json.dumps(value, ensure_ascii=False)
            )
            lines = clean(str(output)).splitlines()
            for line in lines[:8]:
                self.console.print(Text("  │ " + line[:240], style="dim"))
            if len(lines) > 8:
                self.console.print(
                    Text(f"  │ … {len(lines) - 8} more lines returned to model", style="dim")
                )
            self.console.print(
                Text(
                    f"  {'✗' if error else '✓'} {time.monotonic() - self.started:.1f}s\n",
                    style="red" if error else "dim",
                )
            )

    async def configure(self):
        base = (
            await self.input("API base URL › ", default=self.config.base)
        ).strip() or self.config.base
        model = (
            await self.input("Model ID › ", default=self.config.model)
        ).strip() or self.config.model
        key = (await self.input("API key (hidden) › ", password=True)).strip()
        config = ModelConfig(base, model, key)
        if not key:
            raise AgentError("A model API key is required. Your existing settings were preserved.")
        config.save()
        await self.agent.close()
        self.config = config
        self.agent = Agent(config, self.root, event=self.event, ask=self.ask)
        self.console.print(
            Text("Model connected. Your key is in the native OS credential store.\n", style=ACCENT)
        )

    async def slash(self, line: str) -> bool:
        name, _, rest = line.partition(" ")
        rest = rest.strip()
        if name in ("/exit", "/quit"):
            return False
        if name == "/update":
            if os.environ.get("DARK_NPM_LAUNCHER"):
                raise SystemExit(85)
            self.console.print(
                Text("Update with: npm install -g dark-agent-cli@latest", style=ACCENT)
            )
            return True
        if name == "/help":
            table = Table(box=None, show_header=False, padding=(0, 2))
            for command, description in COMMANDS.items():
                table.add_row(Text(command, style=ACCENT), description)
            self.console.print(table)
        elif name == "/clear":
            self.agent.clear()
            self.console.clear()
            self.banner()
        elif name in ("/provider", "/settings"):
            await self.configure()
        elif name in ("/model", "/fast"):
            if name == "/fast":
                if self.config.base.rstrip("/") != DEFAULT_BASE:
                    raise AgentError("Use /model to choose a faster model from your provider.")
                rest = "deepseek-v4.1-flash-fast"
            if rest:
                config = ModelConfig(self.config.base, rest, self.config.key)
                config.save()
                await self.agent.close()
                self.config = config
                self.agent = Agent(config, self.root, event=self.event, ask=self.ask)
            self.console.print(Text(self.config.model, style=ACCENT))
        elif name == "/cwd":
            if rest:
                path = Path(rest.strip("\"'")).expanduser().resolve()
                if not path.is_dir():
                    raise AgentError("Workspace directory does not exist.")
                self.root = path
                await self.agent.close()
                self.agent = Agent(self.config, path, event=self.event, ask=self.ask)
            self.console.print(Text(str(self.root)))
        elif name == "/tools":
            for tool in BUILTINS:
                entry = tool["function"]
                self.console.print(
                    Text.assemble((entry["name"], ACCENT), "  ", entry["description"])
                )
            self.console.print(
                Text(
                    "Windows tools load on demand and keep one connection alive during a task.",
                    style="dim",
                )
            )
        elif name in ("/login", "/logout", "/whoami", "/doctor", "/desktop", "/runs"):
            args = [
                name[1:],
                *[part.strip("\"'") for part in shlex.split(rest, posix=os.name != "nt")],
            ]
            try:
                await self.interruptible(self.command(args))
            except asyncio.CancelledError:
                self.console.print(Text("Command cancelled.", style="yellow"))
        else:
            self.console.print(Text(f"Unknown command {name}. Type /help.", style="yellow"))
        return True

    async def command(self, args: list[str]):
        child = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "dark_cli",
            *args,
            cwd=self.root,
        )
        try:
            await child.wait()
        finally:
            if child.returncode is None:
                child.terminate()
                await child.wait()

    async def interruptible(self, operation):
        task = asyncio.create_task(operation)
        previous = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, lambda *_: task.cancel())
        try:
            return await task
        finally:
            signal.signal(signal.SIGINT, previous)

    async def execute(self, prompt: str) -> bool:
        started = time.monotonic()
        try:
            await self.interruptible(self.agent.turn(prompt))
            self.console.print(
                Text(
                    f"─ {self.agent.steps} tool calls · {time.monotonic() - started:.1f}s\n",
                    style="dim",
                )
            )
            return True
        except asyncio.CancelledError:
            self.console.print(
                Text(
                    "Stopped. Completed actions remain; inspect the result before retrying.\n",
                    style="yellow",
                )
            )
        except Exception as exc:
            self.console.print(Text(error_text(exc) + "\n", style="red"))
        finally:
            self.event("response_end", None)
        return False

    async def run(self, prompt: str | None = None) -> bool:
        if prompt is not None:
            return await self.execute(prompt)
        self.banner()
        while True:
            try:
                line = (await self.input()).strip()
                if not line:
                    continue
                if line.startswith("/"):
                    if not await self.slash(line):
                        break
                else:
                    await self.execute(line)
            except KeyboardInterrupt:
                self.console.print(Text("Type /exit to close Dark.", style="dim"))
            except EOFError:
                break
            except Exception as exc:
                self.console.print(Text(error_text(exc), style="red"))
        return True


def launch(prompt: str | None = None) -> bool:
    async def managed():
        chat = Chat()
        try:
            return await chat.run(prompt)
        finally:
            await chat.agent.close()

    try:
        return asyncio.run(managed())
    except (KeyboardInterrupt, EOFError):
        return False
    except Exception as exc:
        Console().print(Text(error_text(exc), style="red"))
        return False
