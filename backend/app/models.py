"""Domain models: runs, findings, refusal telemetry."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _id() -> str:
    return uuid.uuid4().hex[:12]


class RunStatus(str, Enum):
    pending = "pending"
    exploring = "exploring"
    challenging = "challenging"
    verifying = "verifying"
    done = "done"
    failed = "failed"


class Severity(str, Enum):
    info = "info"
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class Run(BaseModel):
    id: str = Field(default_factory=_id)
    target: str
    goal: str
    status: RunStatus = RunStatus.pending
    started_at: datetime = Field(default_factory=_now)
    finished_at: datetime | None = None


class Finding(BaseModel):
    """A finding only counts once it reproduces from the recorded action log."""

    id: str = Field(default_factory=_id)
    run_id: str
    title: str
    severity: Severity = Severity.info
    hypothesis: str = ""
    evidence: list[str] = Field(default_factory=list)  # screenshot paths, network errors
    reproduction: list[str] = Field(default_factory=list)  # recorded action log
    verified: bool = False
    regression_test: str | None = None  # generated Playwright/UIA test path
    created_at: datetime = Field(default_factory=_now)


class RefusalEvent(BaseModel):
    """One model refusal or friction event, for base-vs-abliterated telemetry."""

    id: str = Field(default_factory=_id)
    run_id: str
    model: str
    stage: str  # planner | operator | verifier-judge
    refused: bool = False
    detail: str = ""
    created_at: datetime = Field(default_factory=_now)
