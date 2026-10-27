// Output captured from dark 0.1.0 (help: 0.3.0) on 2026-10-27 against the bundled WinForms fixture
// (scripts/start-desktop-fixture.ps1). Status lines are the CLI's stderr; JSON is its stdout.
// Commands are shown as `dark` (uv tool install ./cli). "⋯" marks lines elided for length.

export type TerminalLine =
  | { kind: "prompt"; text: string }
  | { kind: "tick"; text: string; seconds: number }
  | { kind: "out"; text: string; tone?: "dim" | "fail" | "pass" };

const prompt = (text: string): TerminalLine => ({ kind: "prompt", text });
const tick = (text: string, seconds: number): TerminalLine => ({ kind: "tick", text, seconds });
const out = (text: string, tone?: "dim" | "fail" | "pass"): TerminalLine => ({ kind: "out", text, tone });
const elided = out("  ⋯", "dim");

export const exerciseApply: TerminalLine[] = [
  prompt("dark desktop exercise examples\\desktop\\negative.json --apply"),
  tick("connect Windows desktop server", 1.2),
  tick("window_management list", 0.2),
  tick("ui_find", 0.2),
  tick("ui_click", 0.1),
  tick("ui_find", 0.0),
  tick("ui_read", 0.0),
  tick("ui_find", 0.0),
  tick("ui_type", 0.1),
  tick("ui_find", 0.1),
  tick("ui_click", 0.1),
  tick("ui_find", 0.0),
  tick("ui_read", 0.0),
  out("{"),
  out('  "status": "failed",', "fail"),
  out('  "verified_finding": false,'),
  out('  "scenario": "Reject a negative inventory quantity (intentional fixture bug)",'),
  elided,
  out('      "expected_text": "Rejected: quantity must be nonnegative",', "fail"),
  out('      "match": "exact",'),
  out('      "passed": false,', "fail"),
  out('      "observed": {'),
  elided,
  out('        "text": "Saved quantity: -2"', "fail"),
  elided,
  out('  "reason": "Expected text was absent from the selected control"'),
  out("}"),
  prompt("$LASTEXITCODE"),
  out("1"),
];

export const probe: TerminalLine[] = [
  prompt("dark desktop probe --title 'Dark Desktop Fixture' --expect Ready --screenshot"),
  tick("connect Windows desktop server", 1.1),
  tick("window_management list", 0.2),
  tick("ui_snapshot", 0.3),
  tick("screenshot_control capture", 0.1),
  out("{"),
  out('  "status": "passed",', "pass"),
  out('  "verified_finding": false,'),
  elided,
  out('      "expected_text": "Ready",'),
  out('      "passed": true', "pass"),
  elided,
];

export const help: TerminalLine[] = [
  prompt("dark --help"),
  ...`
 Usage: dark [OPTIONS] COMMAND [ARGS]...

 Dark: an interactive agent for your code, terminal, and Windows desktop.

┌─ Options ───────────────────────────────────────────────────────────────────────────┐
│ --version                     Print the installed CLI version.                      │
│ --install-completion          Install completion for the current shell.             │
│ --show-completion             Show completion for the current shell, to copy it or  │
│                               customize the installation.                           │
│ --help                        Show this message and exit.                           │
└─────────────────────────────────────────────────────────────────────────────────────┘
┌─ Commands ──────────────────────────────────────────────────────────────────────────┐
│ doctor   Check service configuration and MongoDB connectivity without sending       │
│          email.                                                                     │
│ login    Sign in through the website and connect this computer.                     │
│ whoami   Show the account connected to this CLI.                                    │
│ logout   Revoke this CLI session and remove its local credential.                   │
│ chat     Open the interactive agent. This is also the default when running dark.    │
│ run      Run one natural-language task and exit.                                    │
│ update   Update the npm CLI to the latest release.                                  │
│ scan     Explore, challenge, verify, and report on an authorized target.            │
│ ctf      Sanctioned CTF challenges.                                                 │
│ desktop  Inspect Windows apps, record evidence, and run explicit desktop exercises. │
│ runs     Upload, list, and inspect saved desktop reports.                           │
└─────────────────────────────────────────────────────────────────────────────────────┘`
    .slice(1).split("\n").map((line) => out(line)),
];

// examples/desktop/negative.json, verbatim.
export const negativeScenario = `{
  "name": "Reject a negative inventory quantity (intentional fixture bug)",
  "window_title": "Dark Desktop Fixture",
  "steps": [
    {"action": "click", "automation_id": "resetButton"},
    {"action": "assert_text", "automation_id": "statusLabel", "text": "Ready"},
    {"action": "type", "automation_id": "quantityInput", "text": "-2"},
    {"action": "click", "automation_id": "saveButton"},
    {"action": "assert_text", "automation_id": "statusLabel", "text": "Rejected: quantity must be nonnegative"}
  ]
}`;

// Controls from the probe's snapshot.json (window title bar omitted).
export const snapshotControls = [
  { type: "Window", id: "", name: "Dark Desktop Fixture" },
  { type: "Text", id: "", name: "Inventory test target - negative quantities should be rejected." },
  { type: "Edit", id: "quantityInput", name: "Quantity", value: "1" },
  { type: "Button", id: "saveButton", name: "Save" },
  { type: "Button", id: "resetButton", name: "Reset" },
  { type: "Text", id: "statusLabel", name: "Ready", expected: true },
];

// Selected records from the failing exercise's events.jsonl (24 records in total).
export const eventRecords = [
  { seq: 3, kind: "tool_call", detail: "ui_find  automationId=resetButton" },
  { seq: 5, kind: "tool_call", detail: "ui_click  Reset" },
  { seq: 10, kind: "tool_result", detail: 'ui_read  "Ready"' },
  { seq: 11, kind: "assertion", detail: 'step 2  "Ready"', passed: true },
  { seq: 14, kind: "tool_call", detail: 'ui_type  quantityInput  "-2"' },
  { seq: 18, kind: "tool_call", detail: "ui_click  Save" },
  { seq: 23, kind: "tool_result", detail: 'ui_read  "Saved quantity: -2"' },
  { seq: 24, kind: "assertion", detail: 'step 5  "Rejected: quantity must be nonnegative"', passed: false },
];

// Files and sizes in bytes from the probe's run directory.
export const runDirectory = {
  path: ".dark\\runs\\20261027T073330-747e6866",
  files: [
    ["events.jsonl", 4395],
    ["report.json", 444],
    ["screenshot-result.json", 436],
    ["screenshot.png", 8902],
    ["server.json", 164],
    ["snapshot.json", 3864],
  ] as const,
};
