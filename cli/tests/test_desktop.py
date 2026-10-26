import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from mcp.types import CallToolResult, TextContent
from pydantic import ValidationError
from typer.testing import CliRunner

from dark_cli.cli import app
from dark_cli.desktop.decisions import choose_route
from dark_cli.desktop.evidence import Evidence
from dark_cli.desktop.scenario import Scenario, exercise
from dark_cli.desktop.windows import (
    DesktopError,
    WindowsDesktop,
    select_window,
    snapshot_text,
    unpack,
)


def result(data, **kwargs):
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(data))], **kwargs)


def test_ambiguous_window_selection_never_picks_first_match():
    windows = [{"title": "Fixture", "handle": "1"}, {"title": "Fixture", "handle": "2"}]
    with pytest.raises(DesktopError, match="found 2"):
        select_window({"windows": windows}, "Fixture")


def test_window_selection_uses_exact_title_and_returned_handle():
    windows = [
        {"title": "Fixture - unrelated", "handle": "1"},
        {"title": "Fixture", "handle": "42"},
    ]
    assert select_window({"windows": windows}, "fixture")["handle"] == "42"


@pytest.mark.parametrize("data", [{"success": False, "error": "access denied"}, {"isError": True}])
def test_tool_failure_is_not_protocol_success(data):
    with pytest.raises(DesktopError):
        unpack(result(data))


def test_mcp_error_flag_is_not_ignored():
    with pytest.raises(DesktopError):
        unpack(result({"message": "blocked"}, isError=True))


def test_non_json_tool_response_fails_explicitly():
    with pytest.raises(DesktopError, match="non-JSON"):
        unpack(CallToolResult(content=[TextContent(type="text", text="unexpected output")]))


def test_probe_reads_displayed_text_instead_of_protocol_metadata():
    text = snapshot_text(
        {
            "success": True,
            "hint": "Ready",
            "snapshotToken": "secret-token",
            "tree": [
                {
                    "name": "Inventory",
                    "enabled": True,
                    "children": [
                        {"name": "Quantity", "value": "3", "automationId": "quantityInput"}
                    ],
                }
            ],
        }
    )
    assert text == "Inventory\nQuantity\n3"
    assert "Ready" not in text
    assert "enabled" not in text


def test_scenario_rejects_unchecked_actions_after_an_assertion():
    with pytest.raises(ValidationError, match="must end"):
        Scenario(
            name="Unchecked save",
            window_title="Fixture",
            steps=[
                {"action": "assert_text", "name": "Status", "text": "Ready"},
                {"action": "click", "name": "Save"},
            ],
        )


def test_scenario_requires_assertions_and_rejects_arbitrary_actions():
    with pytest.raises(ValidationError, match="observable result"):
        Scenario(
            name="No assertion", window_title="Fixture", steps=[{"action": "click", "name": "Save"}]
        )
    with pytest.raises(ValidationError):
        Scenario(
            name="Shell", window_title="Fixture", steps=[{"action": "shell", "text": "whoami"}]
        )
    with pytest.raises(ValidationError):
        Scenario(
            name="Empty check",
            window_title="Fixture",
            steps=[{"action": "assert_text", "name": "Status", "text": ""}],
        )


async def test_mutation_timeout_is_logged_unknown_and_never_retried(tmp_path):
    evidence = Evidence(tmp_path)
    session = SimpleNamespace(call_tool=AsyncMock(side_effect=TimeoutError))
    desktop = WindowsDesktop(session, {"ui_click"}, evidence)
    with pytest.raises(DesktopError, match="outcome is unknown"):
        await desktop.call("ui_click", {"windowHandle": "42", "elementId": "observed-id"})
    session.call_tool.assert_awaited_once()
    events = [
        json.loads(line) for line in (evidence.path / "events.jsonl").read_text().splitlines()
    ]
    assert events[-1]["outcome"] == "unknown"


async def test_adapter_understands_released_server_element_ids():
    session = SimpleNamespace(
        call_tool=AsyncMock(
            return_value=result(
                {
                    "success": True,
                    "items": [{"id": "opaque-current-id", "name": "Save"}],
                }
            )
        )
    )
    desktop = WindowsDesktop(session, {"ui_find"})
    assert await desktop.find("42", {"automationId": "saveButton"}) == "opaque-current-id"
    arguments = session.call_tool.await_args.args[1]
    assert arguments["requireUnique"] is True


async def test_assertion_cannot_pass_on_metadata_or_a_partial_numeric_match(tmp_path):
    scenario = Scenario(
        name="Exact quantity",
        window_title="Fixture",
        steps=[
            {"action": "assert_text", "automation_id": "statusLabel", "text": "Saved quantity: 3"}
        ],
    )
    desktop = SimpleNamespace(
        select=AsyncMock(return_value={"handle": "42", "title": "Fixture"}),
        find=AsyncMock(return_value="current-id"),
        call=AsyncMock(
            return_value={"text": "Saved quantity: 30", "description": "Saved quantity: 3"}
        ),
    )
    report = await exercise(desktop, scenario, Evidence(tmp_path))
    assert report["status"] == "failed"


async def test_scenario_rediscovers_selectors_and_stops_at_failed_assertion(tmp_path):
    desktop = SimpleNamespace(
        select=AsyncMock(return_value={"handle": "42", "title": "Fixture"}),
        find=AsyncMock(side_effect=["fresh-save", "fresh-status"]),
        call=AsyncMock(side_effect=[{"success": True}, {"text": "Saved negative quantity"}]),
    )
    scenario = Scenario(
        name="Negative",
        window_title="Fixture",
        steps=[
            {"action": "click", "automation_id": "saveButton"},
            {"action": "assert_text", "automation_id": "statusLabel", "text": "Rejected"},
            {"action": "click", "automation_id": "mustNotRun"},
            {"action": "assert_text", "automation_id": "statusLabel", "text": "Never read"},
        ],
    )
    evidence = Evidence(tmp_path)
    report = await exercise(desktop, scenario, evidence)
    assert report["status"] == "failed"
    assert report["verified_finding"] is False
    assert desktop.find.await_count == 2
    assert desktop.call.await_args_list[1].args[1]["elementId"] == "fresh-status"
    assert (evidence.path / "report.json").exists()


def test_exercise_defaults_to_preview_without_connecting(monkeypatch, tmp_path):
    scenario = tmp_path / "scenario.json"
    scenario.write_text(
        json.dumps(
            {
                "name": "Preview",
                "window_title": "Fixture",
                "steps": [{"action": "assert_text", "name": "Status", "text": "Ready"}],
            }
        )
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("Preview must not connect to the desktop")

    monkeypatch.setattr("dark_cli.desktop.cli.connect", forbidden)
    response = CliRunner().invoke(app, ["desktop", "exercise", str(scenario)])
    assert response.exit_code == 0
    assert json.loads(response.stdout)["executed"] is False


async def test_jev_request_uses_typed_choices_and_validates_result(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    monkeypatch.setenv("DARK_JEV_BASE_URL", "")
    monkeypatch.setenv("DARK_JEV_MODEL", "")

    def handler(request):
        payload = json.loads(request.content)
        assert request.url == "https://api.typesafe.ai/v1/systemone"
        assert payload["questions"]["next_step"]["type"] == "choice"
        assert payload["state"]["goal"] == "Inspect the fixture"
        assert payload["model"] == "jev-latest"
        return httpx.Response(
            200, json={"answers": {"next_step": {"choice": "inspect_controls", "confidence": 0.7}}}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        decision = await choose_route("Inspect the fixture", {"name": "Save"}, client=client)
    assert decision["choice"] == "inspect_controls"
    assert decision["executed"] is False


@pytest.mark.parametrize(
    "answer",
    [
        {"choice": "run_shell", "confidence": 0.99},
        {"choice": "inspect_controls", "confidence": 2},
        {"choice": "inspect_controls", "confidence": True},
        {"choice": "inspect_controls"},
    ],
)
async def test_jev_invalid_decision_is_rejected(monkeypatch, answer):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"answers": {"next_step": answer}})
    )
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(DesktopError):
            await choose_route("Inspect", {}, client=client)


async def test_jev_missing_key_makes_no_network_call(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    with pytest.raises(DesktopError, match="TYPESAFE_API_KEY"):
        await choose_route("Inspect", {})
