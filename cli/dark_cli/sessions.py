"""Persist chat conversations under the config directory so they can be resumed.

Saving is best effort: a conversation that cannot be written simply cannot be
resumed later. Files live beside the CLI's other preferences and are pruned to the
most recent MAX_SESSIONS. Saving redacts configured credentials before writing.
"""

from __future__ import annotations

import json
import math
import os
import re
import tempfile
import time
import uuid
from pathlib import Path

from .config import app_directory

MAX_SESSIONS = 40
MAX_BYTES = 4_000_000
_ID = re.compile(r"\A\d{8}T\d{6}-[0-9a-f]{8}\Z")


def _base() -> Path:
    configured = os.getenv("DARK_CONFIG_DIR")
    return Path(configured).expanduser() if configured else app_directory()


def directory() -> Path:
    return _base() / "sessions"


def history_file() -> Path:
    return _base() / "history"


def new_id() -> str:
    return time.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]


def _title(messages: list[dict]) -> str:
    for message in messages:
        if message.get("role") == "user" and isinstance(message.get("content"), str):
            text = " ".join(message["content"].split())
            if text:
                return text[:80]
    return "(no prompt)"


def turns(messages: list[dict]) -> int:
    return sum(1 for message in messages if message.get("role") == "user")


def save(
    session_id: str, root: str, model: str, messages: list[dict], *, secrets: tuple[str, ...] = ()
) -> None:
    """Write or overwrite one conversation. Empty conversations are skipped."""
    if os.getenv("DARK_NO_HISTORY") or not _ID.match(session_id) or not messages:
        return
    from .agent import clean

    def scrub(value):
        if isinstance(value, str):
            return clean(value, *secrets)
        if isinstance(value, dict):
            return {key: scrub(item) for key, item in value.items()}
        if isinstance(value, list):
            return [scrub(item) for item in value]
        return value

    messages = scrub(messages)
    record = {
        "id": session_id,
        "updated": time.time(),
        "root": root,
        "model": model,
        "title": _title(messages),
        "messages": messages,
    }
    temporary = None
    try:
        payload = json.dumps(record, ensure_ascii=False)
        if len(payload.encode("utf-8")) > MAX_BYTES:
            return
        folder = directory()
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name != "nt":
            folder.chmod(0o700)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=folder, suffix=".tmp", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
        temporary.replace(folder / f"{session_id}.json")
        _prune(folder)
    except (OSError, ValueError, TypeError):
        pass
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def _prune(folder: Path) -> None:
    saved = sorted(folder.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    for stale in saved[MAX_SESSIONS:]:
        stale.unlink(missing_ok=True)


def recent(limit: int = 10, *, root: str | None = None) -> list[dict]:
    """Summaries of the most recently updated conversations, newest first."""
    try:
        files = sorted(
            directory().glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True
        )
    except OSError:
        return []
    summaries = []
    for path in files:
        if len(summaries) >= max(0, limit):
            break
        record = _read(path)
        if record is None:
            continue
        if root is not None and record.get("root") != root:
            continue
        summaries.append(
            {
                "id": record["id"],
                "title": record.get("title") or "(no prompt)",
                "model": record.get("model") or "",
                "root": record.get("root") or "",
                "updated": record.get("updated") or path.stat().st_mtime,
                "turns": turns(record["messages"]),
            }
        )
    return summaries


def load(session_id: str) -> dict | None:
    if not _ID.match(session_id):
        return None
    return _read(directory() / f"{session_id}.json")


def _read(path: Path) -> dict | None:
    try:
        if path.stat().st_size > MAX_BYTES:
            return None
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(record, dict) or not isinstance(record.get("messages"), list):
        return None
    if not _ID.fullmatch(path.stem):
        return None
    if any(
        not isinstance(message, dict)
        or message.get("role") not in {"user", "assistant", "tool"}
        or (message.get("content") is not None and not isinstance(message["content"], str))
        for message in record["messages"]
    ):
        return None
    if any(not isinstance(record.get(key, ""), str) for key in ("root", "model", "title")):
        return None
    updated = record.get("updated", 0)
    if not isinstance(updated, (int, float)) or not math.isfinite(updated):
        return None
    record["id"] = path.stem
    return record
