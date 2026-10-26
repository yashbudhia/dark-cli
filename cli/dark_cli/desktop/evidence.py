"""Keep tool results and assertions separate from model decisions."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


def now() -> str:
    return datetime.now(UTC).isoformat()


class Evidence:
    def __init__(self, root: Path) -> None:
        self.path = root / f"{datetime.now(UTC):%Y%m%dT%H%M%S}-{uuid4().hex[:8]}"
        self.path.mkdir(parents=True, exist_ok=False)
        self.sequence = 0

    def save(self, name: str, value: Any) -> None:
        (self.path / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    def event(self, kind: str, **data: Any) -> None:
        self.sequence += 1
        record = {"seq": self.sequence, "at": now(), "kind": kind, **data}
        with (self.path / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")

    def finish(self, status: str, **data: Any) -> dict[str, Any]:
        report = {
            "status": status,
            "finished_at": now(),
            "verified_finding": False,
            "evidence_dir": str(self.path.resolve()),
            **data,
        }
        self.save("report.json", report)
        return report
