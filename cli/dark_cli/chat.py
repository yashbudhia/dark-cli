"""Dark's conversational terminal UI, slash commands and cancellable agent turns."""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import json
import os
import shlex
import shutil
import signal
import sys
import threading
import time
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import DummyHistory, FileHistory, InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from . import __version__, sessions
from .agent import BUILTINS, DEFAULT_BASE, DEFAULT_MODEL, Agent, AgentError, ModelConfig, clean
from .auth import AccountClient, Credentials, LoginError, account_email, server_url
from .config import configured_server

ACCENT = "#00ff88"
# The mascot in the terminal: a face in nerd glasses beside a blinking cursor.
FACES = {
    "thinking": ["◕‿◕", "◕‿◕", "◔‿◔", "◔‿◔", "◕‿◕", "◕‿◕", "-‿-", "◕‿◕"],
    "looking": ["◉_◉", "◉_◉", "◎_◎", "◎_◎"],
    "working": ["◕‿◕", "◕‿◕", "◕‿◕", "◕‿◕", "◕‿◕", "-‿-"],
}
COMMANDS = {
    "/help": "Show commands and keyboard shortcuts",
    "/login": "Connect your Dark account in the browser",
    "/logout": "Revoke your account session",
    "/whoami": "Show your connected account",
    "/doctor": "Check the hosted service",
    "/provider": "Set your model endpoint and API key",
    "/models": "List your provider's models",
    "/model": "Show or change the model: /model <id or number from /models>",
    "/fast": "Use the lower-latency Refuseless model",
    "/tools": "Show the agent's tools",
    "/desktop": "Run desktop commands: /desktop windows",
    "/runs": "Manage reports: /runs list",
    "/cwd": "Show or change the workspace: /cwd <path>",
    "/resume": "Resume a recent conversation: /resume or /resume <number>",
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


def background(function, *args) -> asyncio.Future:
    """Run a blocking call in a daemon thread, which never delays closing Dark."""
    loop = asyncio.get_running_loop()
    future = loop.create_future()

    def settle(succeeded, value):
        if not future.done():
            (future.set_result if succeeded else future.set_exception)(value)

    def run():
        try:
            succeeded, value = True, function(*args)
        except BaseException as exc:
            succeeded, value = False, exc
        try:
            loop.call_soon_threadsafe(settle, succeeded, value)
        except RuntimeError:
            pass  # Dark closed first.

    threading.Thread(target=run, daemon=True).start()
    return future


def mascot(mood: str, text: str) -> Spinner:
    spinner = Spinner("dots", text=text, style=ACCENT)
    spinner.frames = [
        f"[{face}]{'▌' if index % 2 == 0 else ' '}" for index, face in enumerate(FACES[mood])
    ]
    spinner.interval = 180
    return spinner


def preload(*modules: str) -> None:
    for module in modules:
        importlib.import_module(module)


def ago(timestamp: float) -> str:
    seconds = max(0.0, time.time() - timestamp)
    for amount, unit in ((86400, "d"), (3600, "h"), (60, "m")):
        if seconds >= amount:
            return f"{int(seconds // amount)}{unit} ago"
    return "just now"


def error_text(exc: Exception) -> str:
    if isinstance(exc, (AgentError, LoginError)):
        return clean(str(exc))
    from .model import APIConnectionError, APIStatusError, AuthenticationError, RateLimitError

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
        self.model_ids: list[str] = []
        self.resume_ids: list[str] = []
        self.session_id = sessions.new_id()
        self.preparing: asyncio.Future | None = None
        bindings = KeyBindings()

        @bindings.add("escape", "enter")
        def newline(event):
            event.current_buffer.insert_text("\n")

        self.terminal = sys.stdin.isatty() and sys.stdout.isatty()
        self.session = (
            PromptSession(
                history=self.history(),
                completer=SlashCompleter(),
                auto_suggest=AutoSuggestFromHistory(),
                key_bindings=bindings,
                style=Style.from_dict(
                    {
                        "prompt": "#00ff88 bold",
                        # The fence drawn above and below the input, not a filled bar.
                        "bottom-toolbar": "noreverse bg:default",
                        "toolbar-rule": "#2a322d",
                        "toolbar-text": "#81938a",
                        "completion-menu.completion": "bg:#101914 #dce8df",
                        "completion-menu.completion.current": "bg:#00ff88 #07100a",
                    }
                ),
            )
            if self.terminal
            else None
        )
        self.agent = Agent(self.config, self.root, event=self.event, ask=self.ask)

    def history(self):
        """Recall input lines across runs, falling back to memory if the file is unusable."""
        try:
            if os.getenv("DARK_NO_HISTORY"):
                return InMemoryHistory()
            path = sessions.history_file()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch(mode=0o600, exist_ok=True)
            if os.name != "nt":
                path.chmod(0o600)
            chat = self

            class RedactedHistory(FileHistory):
                def store_string(self, string: str) -> None:
                    super().store_string(clean(string, chat.config.key))

            return RedactedHistory(str(path))
        except OSError:
            return InMemoryHistory()

    def banner(self):
        title = Text.assemble(
            ("dark", f"bold {ACCENT}"), (f" / {__version__} ", "dim"), ("[◕‿◕]", ACCENT)
        )
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
            ("Dark account required · /login to connect\n", "dim"),
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
            # PowerShell starts piped text with a byte order mark.
            return line.rstrip("\n").lstrip("\ufeff")
        if password:
            return await PromptSession(history=DummyHistory()).prompt_async(label, is_password=True)
        if label != "❯ ":
            return await PromptSession(history=DummyHistory()).prompt_async(label, default=default)
        # A rule above and the toolbar's rule below fence the input off from the
        # scrolling output, so it stays easy to find.
        self.console.print(Text("─" * self.console.width, style="#2a322d"))
        return await self.session.prompt_async(
            [("class:prompt", label)],
            complete_while_typing=True,
            bottom_toolbar=self.toolbar,
        )

    def toolbar(self) -> FormattedText:
        width = shutil.get_terminal_size((80, 24)).columns
        return FormattedText(
            [
                ("class:toolbar-rule", "─" * width + "\n"),
                ("class:toolbar-text", f"  {self.config.model}  ·  /help  ·  {self.root.name}  "),
            ]
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
                    mascot("thinking", "Thinking…"),
                    console=self.console,
                    transient=True,
                    refresh_per_second=12,
                )
                self.live.start()
        elif kind == "text":
            from rich.markdown import Markdown

            self.text = value
            if self.live:
                self.live.update(Markdown(value))
        elif kind == "response_end":
            from rich.markdown import Markdown

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
            if self.terminal and name.startswith("desktop__"):
                looking = name == "desktop__screenshot_control"
                self.live = Live(
                    mascot(
                        "looking" if looking else "working",
                        f"Looking at the screen with {self.agent.vision_model()}…"
                        if looking
                        else "Controlling the desktop…",
                    ),
                    console=self.console,
                    transient=True,
                    refresh_per_second=12,
                )
                self.live.start()
        elif kind == "tool_end":
            if self.live:
                self.live.stop()
                self.live = None
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
        self.session_id = sessions.new_id()
        self.model_ids = []
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
        elif name == "/resume":
            self.resume(rest)
        elif name == "/clear":
            self.agent.clear()
            self.session_id = sessions.new_id()
            self.console.clear()
            self.banner()
        elif name in ("/provider", "/settings"):
            await self.configure()
        elif name == "/models":
            await self.list_models()
        elif name in ("/model", "/fast"):
            if (
                name == "/model"
                and rest.isdecimal()
                and self.model_ids
                and not 1 <= int(rest) <= len(self.model_ids)
            ):
                raise AgentError("No model with that number. Type /models to list them.")
            if rest.isdecimal() and 1 <= int(rest) <= len(self.model_ids):
                rest = self.model_ids[int(rest) - 1]
            if name == "/fast":
                if self.config.base.rstrip("/") != DEFAULT_BASE:
                    raise AgentError("Use /model to choose a faster model from your provider.")
                rest = "deepseek-v4.1-flash-fast"
            if rest:
                config = ModelConfig(self.config.base, rest, self.config.key)
                config.save()
                messages = self.agent.messages
                await self.agent.close()
                self.config = config
                self.agent = Agent(config, self.root, event=self.event, ask=self.ask)
                self.agent.messages = messages
            self.console.print(Text(self.config.model, style=ACCENT))
        elif name == "/cwd":
            if rest:
                path = Path(rest.strip("\"'")).expanduser().resolve()
                if not path.is_dir():
                    raise AgentError("Workspace directory does not exist.")
                self.root = path
                await self.agent.close()
                self.agent = Agent(self.config, path, event=self.event, ask=self.ask)
                self.session_id = sessions.new_id()
                self.resume_ids = []
            self.console.print(Text(str(self.root)))
        elif name == "/tools":
            for tool in BUILTINS:
                entry = tool["function"]
                self.console.print(
                    Text.assemble((entry["name"], ACCENT), "  ", entry["description"])
                )
            self.console.print(
                Text(
                    "Windows tools load on demand and keep one connection alive until Dark closes.",
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

    async def list_models(self):
        if not self.config.key:
            raise AgentError("Connect a model with /provider to list its models.")
        models = await self.agent.connect().models()
        self.model_ids = [model["id"] for model in models]
        table = Table(box=None, show_header=False, padding=(0, 2))
        for number, model in enumerate(models, start=1):
            context = model.get("context_length")
            if isinstance(context, int):
                size = (
                    f"{round(context / 2**20)}M"
                    if context >= 2**20
                    else f"{round(context / 1024)}K"
                )
                context = f"{size} context"
            current = model["id"] == self.config.model
            table.add_row(
                Text(str(number), style="dim"),
                Text(model["id"], style=f"bold {ACCENT}" if current else ""),
                Text(context if isinstance(context, str) else "", style="dim"),
                Text("● current" if current else "", style=ACCENT),
            )
        self.console.print(table)
        self.console.print(
            Text(
                f"Switch with /model <number>. Screenshots are read by {self.agent.vision_model()}.",
                style="dim",
            )
        )

    def save_session(self):
        sessions.save(
            self.session_id,
            str(self.root),
            self.config.model,
            self.agent.messages,
            secrets=(self.config.key,),
        )

    def resume(self, rest: str):
        if rest.isdecimal():
            if not self.resume_ids:
                self.resume_ids = [entry["id"] for entry in sessions.recent(root=str(self.root))]
            index = int(rest)
            if not 1 <= index <= len(self.resume_ids):
                raise AgentError("No conversation with that number. Type /resume to list them.")
            record = sessions.load(self.resume_ids[index - 1])
            if record is None:
                raise AgentError("That conversation is no longer available.")
            self.adopt(record, recap=True)
        else:
            self.list_sessions()

    def list_sessions(self):
        summaries = sessions.recent(root=str(self.root))
        if not summaries:
            self.console.print(Text("No saved conversations yet.", style="dim"))
            return
        self.resume_ids = [entry["id"] for entry in summaries]
        table = Table(box=None, show_header=False, padding=(0, 2))
        for number, entry in enumerate(summaries, start=1):
            current = entry["id"] == self.session_id
            table.add_row(
                Text(str(number), style="dim"),
                Text(ago(entry["updated"]), style="dim"),
                Text(entry["title"][:60], style=ACCENT if current else ""),
                Text(f"{entry['turns']} turn{'' if entry['turns'] == 1 else 's'}", style="dim"),
                Text("● current" if current else "", style=ACCENT),
            )
        self.console.print(table)
        self.console.print(Text("Resume with /resume <number>.", style="dim"))

    def adopt(self, record: dict, recap: bool):
        if record.get("root") != str(self.root):
            raise AgentError(
                "This conversation belongs to another workspace. Use /cwd to open it first."
            )
        self.session_id = record["id"]
        self.agent.clear()
        self.agent.messages.extend(record.get("messages", []))
        count = sessions.turns(self.agent.messages)
        self.console.print(
            Text.assemble(
                ("Resumed ", ACCENT),
                (f"“{record.get('title', '')}”", f"bold {ACCENT}"),
                (f"  ·  {count} turn{'' if count == 1 else 's'}\n", "dim"),
            )
        )
        if not recap:
            return
        # Show the last reply so the thread has context on screen before the next turn.
        for message in reversed(self.agent.messages):
            if message.get("role") == "assistant" and str(message.get("content") or "").strip():
                from rich.markdown import Markdown

                self.console.print(Markdown(message["content"]))
                self.console.print()
                break

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

        async def authorized_turn():
            preparing, self.preparing = self.preparing, None
            if preparing is not None:
                # wait() lets Ctrl+C stop this task without cancelling the preparation.
                await asyncio.wait({preparing})
            await background(self.require_account)
            await self.agent.turn(prompt)

        try:
            await self.interruptible(authorized_turn())
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
            self.save_session()
        return False

    async def prepare(self):
        """Preload imports without contacting a provider before account validation."""
        # Imports run off the event loop so the prompt stays responsive.
        with contextlib.suppress(Exception):
            await background(preload, "dark_cli.model", "rich.markdown")
        await asyncio.gather(
            *([background(preload, "mcp.client.stdio")] if os.name == "nt" else []),
            return_exceptions=True,
        )

    def require_account(self):
        server = server_url(configured_server(None))
        token = Credentials(server).get()
        if not token:
            raise LoginError(
                "Sign in with /login before sending a task. A configured model key does not sign you into Dark."
            )
        client = AccountClient(server)
        try:
            account_email(
                client.require_success(client.request("GET", "/api/auth/me", token=token))
            )
        finally:
            client.close()

    def resume_last(self):
        # A launch-time convenience: with nothing to resume, just open a fresh chat.
        summaries = sessions.recent(1, root=str(self.root))
        record = sessions.load(summaries[0]["id"]) if summaries else None
        if record is not None:
            self.adopt(record, recap=self.terminal)

    async def run(self, prompt: str | None = None, resume: bool = False) -> bool:
        if prompt is not None or self.terminal:
            self.preparing = asyncio.create_task(self.prepare())
        if resume:
            self.resume_last()
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


def launch(prompt: str | None = None, resume: bool = False) -> bool:
    async def managed():
        chat = Chat()
        try:
            return await chat.run(prompt, resume=resume)
        finally:
            await chat.agent.close()

    try:
        return asyncio.run(managed())
    except (KeyboardInterrupt, EOFError):
        return False
    except Exception as exc:
        Console().print(Text(error_text(exc), style="red"))
        return False
