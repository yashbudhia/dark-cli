"""Explicit desktop exercises with fresh selectors and deterministic assertions."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .evidence import Evidence
from .windows import DesktopError, WindowsDesktop


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["click", "type", "assert_text"]
    automation_id: str | None = None
    name: str | None = None
    control_type: str | None = None
    text: str | None = None
    match: Literal["exact", "contains"] = "exact"

    @model_validator(mode="after")
    def validate_step(self) -> Step:
        if not (self.automation_id or self.name):
            raise ValueError("Every step needs an automation_id or exact name")
        if self.action in {"type", "assert_text"} and (self.text is None or not self.text.strip()):
            raise ValueError("Typing and assertions require nonempty text")
        return self

    def selector(self) -> dict[str, Any]:
        return {
            key: value
            for key, value in {
                "automationId": self.automation_id,
                "name": self.name,
                "controlType": self.control_type,
            }.items()
            if value is not None
        }


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    window_title: str = Field(min_length=1)
    steps: list[Step] = Field(min_length=1, max_length=25)

    @model_validator(mode="after")
    def require_assertion(self) -> Scenario:
        if self.steps[-1].action != "assert_text":
            raise ValueError("A scenario must end with an observable result assertion")
        return self


def load_scenario(path: Path) -> Scenario:
    return Scenario.model_validate_json(path.read_text(encoding="utf-8"))


async def exercise(
    desktop: WindowsDesktop, scenario: Scenario, evidence: Evidence
) -> dict[str, Any]:
    evidence.save("scenario.json", scenario.model_dump(mode="json"))
    window = await desktop.select(scenario.window_title)
    handle = str(window["handle"])
    assertions: list[dict[str, Any]] = []
    for index, step in enumerate(scenario.steps):
        # Re-discover before every operation: never save session element IDs in a replay.
        element = await desktop.find(handle, step.selector())
        if step.action == "click":
            await desktop.call("ui_click", {"windowHandle": handle, "elementId": element})
        elif step.action == "type":
            await desktop.call(
                "ui_type",
                {
                    "windowHandle": handle,
                    "elementId": element,
                    "text": step.text,
                    "clearFirst": True,
                },
            )
        else:
            value = await desktop.call("ui_read", {"windowHandle": handle, "elementId": element})
            observed = value.get("text") if isinstance(value, dict) else None
            if not isinstance(observed, str):
                raise DesktopError("ui_read returned no text; cannot verify the selected control")
            expected_text = step.text.casefold()
            actual_text = observed.casefold()
            passed = (
                expected_text == actual_text
                if step.match == "exact"
                else expected_text in actual_text
            )
            assertion = {
                "step": index + 1,
                "expected_text": step.text,
                "match": step.match,
                "passed": passed,
                "observed": value,
            }
            assertions.append(assertion)
            evidence.event("assertion", **assertion)
            if not passed:
                return evidence.finish(
                    "failed",
                    scenario=scenario.name,
                    window=window,
                    assertions=assertions,
                    reason="Expected text was absent from the selected control",
                )
    return evidence.finish("passed", scenario=scenario.name, window=window, assertions=assertions)
