"""Adapter for the separately installed, MIT-licensed Windows MCP server.

Never launch through a shell or rely on npm/PowerShell command shims. Each
exercise keeps one MCP session alive because element IDs belong to that session.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .evidence import Evidence

SERVER_VERSION = "1.3.28"
REQUIRED_TOOLS = {"window_management", "ui_snapshot", "ui_find", "ui_read", "ui_click", "ui_type"}


class DesktopError(RuntimeError):
    """An actionable desktop or protocol error."""


def repository_root() -> Path:
    for directory in (Path.cwd(), *Path.cwd().parents):
        if (directory / "cli" / "dark_cli").is_dir():
            return directory
    return Path.cwd()


def executable() -> str:
    configured = os.environ.get("DARK_WINDOWS_MCP_PATH", "").strip()
    candidate = (
        Path(configured).expanduser()
        if configured
        else repository_root()
        / ".tools"
        / f"windows-mcp-v{SERVER_VERSION}"
        / "server"
        / "Sbroenne.WindowsMcp.exe"
    )
    if candidate.is_file():
        return str(candidate.resolve())
    found = shutil.which(configured or "Sbroenne.WindowsMcp.exe")
    if found:
        return str(Path(found).resolve())
    raise DesktopError(
        "Windows MCP server not found. Run scripts/setup-desktop.ps1 from the repository "
        "or set DARK_WINDOWS_MCP_PATH to Sbroenne.WindowsMcp.exe."
    )


def unpack(result: Any) -> Any:
    """Decode MCP JSON text without mistaking protocol success for tool success."""
    if result.isError:
        message = " ".join(getattr(item, "text", "") for item in result.content)
        raise DesktopError(message or "Desktop tool returned an error")
    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        data = structured
    else:
        texts = [item.text for item in result.content if item.type == "text"]
        if len(texts) != 1:
            raise DesktopError(
                "Expected one structured tool result; received a different MCP content shape"
            )
        try:
            data = json.loads(texts[0])
        except json.JSONDecodeError as exc:
            raise DesktopError(
                "Desktop server returned non-JSON output: " + texts[0][:200]
            ) from exc
    if isinstance(data, dict) and (data.get("success") is False or data.get("isError") is True):
        raise DesktopError(json.dumps(data, ensure_ascii=False)[:1200])
    return data


def windows_in(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        windows = data.get("windows")
        if isinstance(windows, list):
            return [item for item in windows if isinstance(item, dict)]
    raise DesktopError("Unrecognized window list from Windows MCP; inspect the server version")


def select_window(data: Any, title: str) -> dict[str, Any]:
    matches = [
        window
        for window in windows_in(data)
        if str(window.get("title", "")).casefold() == title.casefold()
    ]
    if len(matches) != 1:
        raise DesktopError(
            f"Expected exactly one window titled {title!r}; found {len(matches)}. Use desktop windows first."
        )
    window = matches[0]
    if not str(window.get("handle", "")).isdecimal():
        raise DesktopError("Selected window has no valid handle")
    return window


def snapshot_text(data: Any) -> str:
    """Extract displayed labels/values, excluding protocol metadata and IDs."""
    if not isinstance(data, dict) or not isinstance(data.get("tree"), list):
        raise DesktopError("Snapshot has no accessibility tree; cannot check displayed text")
    parts: list[str] = []

    def visit(nodes: list[Any]) -> None:
        for node in nodes:
            if not isinstance(node, dict):
                continue
            for field in ("name", "value", "text"):
                value = node.get(field)
                if isinstance(value, str):
                    parts.append(value)
            children = node.get("children", [])
            if isinstance(children, list):
                visit(children)

    visit(data["tree"])
    return "\n".join(parts)


class WindowsDesktop:
    def __init__(
        self, session: ClientSession, tools: set[str], evidence: Evidence | None = None
    ) -> None:
        self.session = session
        self.tools = tools
        self.evidence = evidence

    async def call(self, name: str, arguments: dict[str, Any]) -> Any:
        if name not in self.tools:
            raise DesktopError(f"Required tool {name!r} is not exposed by the desktop server")
        if self.evidence:
            self.evidence.event("tool_call", tool=name, arguments=arguments)
        try:
            # Never retry mutations: a timeout can occur after the action committed.
            result = await asyncio.wait_for(self.session.call_tool(name, arguments), timeout=30)
            data = unpack(result)
        except TimeoutError as exc:
            if self.evidence:
                self.evidence.event("tool_error", tool=name, error="timeout", outcome="unknown")
            raise DesktopError(
                f"{name} timed out; outcome is unknown. Reobserve before any retry."
            ) from exc
        except Exception as exc:
            if self.evidence:
                self.evidence.event("tool_error", tool=name, error=str(exc))
            raise
        if self.evidence:
            self.evidence.event("tool_result", tool=name, result=data)
        return data

    async def windows(self) -> Any:
        return await self.call("window_management", {"action": "list"})

    async def select(self, title: str) -> dict[str, Any]:
        return select_window(await self.windows(), title)

    async def snapshot(self, handle: str) -> Any:
        return await self.call(
            "ui_snapshot", {"windowHandle": handle, "mode": "auto", "maxDepth": 8}
        )

    async def find(self, handle: str, selector: dict[str, Any]) -> str:
        data = await self.call(
            "ui_find", {"windowHandle": handle, "requireUnique": True, **selector}
        )
        # Pinned release v1.3.28 returns items[].id, not an arbitrary nested ID.
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
            raise DesktopError("Expected exactly one discovered control in ui_find items")
        element_id = items[0].get("id")
        if not isinstance(element_id, str) or not element_id:
            raise DesktopError("Discovered control has no element ID")
        return element_id


@asynccontextmanager
async def connect(evidence: Evidence | None = None) -> AsyncIterator[WindowsDesktop]:
    if os.name != "nt":
        raise DesktopError("The desktop adapter requires Windows 10/11")
    params = StdioServerParameters(command=executable(), args=[])
    with open(os.devnull, "w") as errlog:
        async with stdio_client(params, errlog=errlog) as (read, write):
            async with ClientSession(read, write) as session:
                info = await asyncio.wait_for(session.initialize(), timeout=20)
                listing = await asyncio.wait_for(session.list_tools(), timeout=20)
                names = {tool.name for tool in listing.tools}
                missing = REQUIRED_TOOLS - names
                if missing:
                    raise DesktopError(
                        "Incompatible desktop server; missing tools: " + ", ".join(sorted(missing))
                    )
                if evidence:
                    evidence.save("server.json", info.serverInfo.model_dump(mode="json"))
                yield WindowsDesktop(session, names, evidence)
