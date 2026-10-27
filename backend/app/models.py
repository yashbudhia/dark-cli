"""Domain models: runs, findings, refusal telemetry."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool


def _now() -> datetime:
    return datetime.now(UTC)


def _id() -> str:
    return uuid.uuid4().hex[:12]


class RunStatus(str, Enum):
    pending = "pending"
    exploring = "exploring"
    challenging = "challenging"
    verifying = "verifying"
    done = "done"
    failed = "failed"
    observed = "observed"
    passed = "passed"
    error = "error"
    preview = "preview"


class Severity(str, Enum):
    info = "info"
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class DesktopAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_text: str = Field(max_length=10000)
    observed_text: str | None = Field(default=None, max_length=10000)
    passed: StrictBool
    step: int | None = Field(default=None, ge=1, le=1000)
    match: Literal["exact", "contains"] = "contains"


class DesktopReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["observed", "passed", "failed", "error", "preview"]
    finished_at: datetime
    window_title: str = Field(default="Unknown window", max_length=1000)
    scenario: str | None = Field(default=None, max_length=2000)
    assertions: list[DesktopAssertion] = Field(default_factory=list, max_length=100)
    reason: str | None = Field(default=None, max_length=10000)
    error: str | None = Field(default=None, max_length=10000)
    verified_finding: Literal[False] = False


class Run(BaseModel):
    id: str = Field(default_factory=_id)
    target: str
    goal: str
    status: RunStatus = RunStatus.pending
    started_at: datetime = Field(default_factory=_now)
    finished_at: datetime | None = None
    kind: Literal["scan", "desktop"] = "scan"
    desktop_report: DesktopReport | None = None


class Finding(BaseModel):
    """A finding only counts once it reproduces from the recorded action log."""

    id: str = Field(default_factory=_id)
    run_id: str
    title: str
    severity: Severity = Severity.info
    hypothesis: str = ""
    evidence: list[str] = Field(
        default_factory=list
    )  # screenshot paths, network errors
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
