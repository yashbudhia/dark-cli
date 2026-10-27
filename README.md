# dark-cli

Dark connects your terminal to an account, inspects authorized Windows apps,
runs explicit test scenarios, and saves reports with expected versus observed text.
The account and report service uses MongoDB, Cloudflare email codes, and a Next.js
workspace. Model-guided scanning and CTF solving remain planned work.

## Implemented demo

```powershell
dark doctor
dark login
dark whoami
dark runs upload .dark\runs\<run-directory> --dry-run
dark runs upload .dark\runs\<run-directory> --open
dark runs list
dark logout
```

Native desktop probes and explicit scenarios produce local evidence without
requiring an account. Report upload is explicit. See [the demo walkthrough](docs/DEMO.md).

## Planned scanning workflow

The following natural-language pipeline is scaffolded, and its commands exit with
a not-implemented status until the model-guided operator is ready.

```
dark scan http://localhost:3000 --goal "Test the archive workflow"
```

1. **Explore** — map the target's workflows and expected behavior
2. **Challenge** — probe edge cases: empty states, malformed inputs, auth boundaries
3. **Verify** — replay suspected failures in fresh state from a recorded action log (no model in the loop)
4. **Report** — reproduction steps, evidence, and a runnable regression test

A finding only counts once it reproduces.

## Layout

| Folder | Stack | Purpose |
|---|---|---|
| `cli/` | Python + Typer | Account login, diagnostics, desktop checks, report upload/list/show |
| `backend/` | FastAPI + MongoDB | Email accounts, sessions, pairing and owner-scoped reports |
| `frontend/` | Next.js + React + TypeScript | Landing page, sign-in and account/report workspace |

```mermaid
flowchart LR
  term([You]) -->|"dark scan"| cli["CLI<br/>explore, challenge, verify, report"]
  cli -->|"runs + findings"| api["Backend<br/>FastAPI store"]
  api -->|"REST"| ui["Frontend<br/>findings dashboard"]
  cli -->|"OpenAI-compatible"| models["Model endpoints<br/>abliterated + vision"]
  cli -->|"Playwright / UIA"| target["Authorized target<br/>Juice Shop, CTF, your app"]
```

## Principles

- **Verified findings only.** Replay from a recorded action log in freshly reset state. Screenshots suggest; replay proves.
- **Abliteration measured, not assumed.** Base vs abliterated on confirmed findings, false positives, refusals hit, cost — every run emits telemetry.
- **Authorized targets only.** Own apps, lab environments, sanctioned CTFs, in-scope bug-bounty programs. Anything else is out of scope, full stop.

## Quickstart

```powershell
.\scripts\setup-service.ps1 -Dev
# Fill MongoDB and Cloudflare values in the generated root .env.
.\scripts\start-service.ps1
# http://127.0.0.1:3000
```

The auth secret is generated once and preserved. Ctrl+C stops the API and website.
Use `-Production` for a production build, or run `scripts/verify-service.ps1` for
automated verification. Full setup and acceptance steps: [docs/DEMO.md](docs/DEMO.md).

Install only the terminal client with `uv tool install ./cli` if the service is
hosted elsewhere, then use `dark login --server https://your-website.example`.
Model endpoints are optional for the implemented account/report demo.

## Accounts and saved reports

Email sign-in, MongoDB storage and browser-approved CLI pairing are implemented.
Configure the backend credentials in [docs/AUTH.md](docs/AUTH.md), then open
`http://127.0.0.1:3000/login` and run `dark login` to connect your terminal.

```powershell
dark whoami
dark runs upload .dark\runs\<run-directory> --dry-run
dark runs upload .dark\runs\<run-directory> --open
dark runs list
dark runs show <run-id>
dark logout
```

Uploads send a report summary and assertions to your account. The dashboard shows
expected versus observed text and supports revoking connected computers. Raw
snapshots, screenshots and event logs stay local. A failed assertion remains a
test result and is not automatically promoted to a verified security finding.

## Native Windows milestone

The desktop slice runs independently of the backend/dashboard. It uses the
[Windows MCP server](https://github.com/sbroenne/mcp-windows) over stdio, with its
native executable resolved by absolute path. The local setup pins release
`v1.3.28` and verifies the download's SHA-256. The binary stays in ignored
`.tools/`; no system installation or .NET SDK is required for the server.

From the repository root, in PowerShell:

```powershell
uv venv .venv
uv pip install --python .venv\Scripts\python.exe -e './cli[dev]'
.\scripts\setup-desktop.ps1
.\.venv\Scripts\dark.exe desktop doctor
.\.venv\Scripts\dark.exe desktop windows
```

`doctor` performs a real MCP handshake and checks required tools. To inspect an
application, use its exact, unique window title from `desktop windows`:

```powershell
.\.venv\Scripts\dark.exe desktop probe --title 'My App' --screenshot
.\.venv\Scripts\dark.exe desktop probe --title 'My App' --expect 'Ready'
```

Probes do not click or type. `--expect` checks displayed control labels and values,
excluding protocol metadata. The PNG, snapshot, append-only event log and report stay
under `.dark/runs/`. Reports distinguish observation, passed checks, failed
checks, and infrastructure errors. A passed check is not a verified vulnerability.

### Disposable native demo

The included WinForms fixture deliberately accepts negative inventory quantities.
It does not access other apps, accounts, or external services. Its build script
uses the Windows .NET Framework compiler, then opens a visible test window.

```powershell
.\scripts\start-desktop-fixture.ps1
.\.venv\Scripts\dark.exe desktop probe --title 'Dark Desktop Fixture' --expect Ready --screenshot

# Without --apply, validate and preview only.
.\.venv\Scripts\dark.exe desktop exercise examples\desktop\positive.json
.\.venv\Scripts\dark.exe desktop exercise examples\desktop\positive.json --apply

# Expected failure: the fixture saves -2 instead of rejecting it. Exit code 1.
.\.venv\Scripts\dark.exe desktop exercise examples\desktop\negative.json --apply
```

Exercises contain explicit `click`, `type`, and `assert_text` steps. Assertions
compare the selected control's text exactly (ignoring case) by default; set `"match": "contains"`
for a substring check. Each operation rediscovers a unique element using its
automation ID or exact name. Opaque session element IDs are never stored as
replay selectors. Scenarios must end with an assertion, and a failed assertion
stops the exercise. Mutations are not
automatically retried after timeouts, because their outcome may be unknown.

The example scenarios reset the fixture and assert `Ready` before proceeding.
For another app, a new run does not reset its data: define and verify its reset
procedure before treating repeated failures as reproducible findings. A saved
run's `scenario.json` can be supplied to `desktop exercise` to repeat it.

### Optional Jev decision preview

Set `TYPESAFE_API_KEY` in `.env`, then:

```powershell
.\.venv\Scripts\dark.exe desktop decide --title 'Dark Desktop Fixture' --goal 'Inspect the inventory controls'
```

This sends the selected window's accessibility snapshot and goal to TypeSafe.
Jev chooses among four bounded next-step categories; its answer is recorded but
never executed. No model key is needed for probes or explicit exercises. Jev's
HTTP contract is covered with mocked responses; live Jev behavior still needs
evaluation with a configured key. Keep target content and local evidence private.

The natural-language exploratory `dark scan` pipeline and CTF mode remain
scaffolds. The next milestone is model-guided control selection on this tested
adapter, followed by fresh-state replay and finding export. Excel, PowerPoint,
and arbitrary-app reliability are not yet implemented or validated here.

### Verification

```powershell
.\.venv\Scripts\python.exe -m pytest cli\tests -q
.\.venv\Scripts\python.exe -m ruff check cli

# With the disposable fixture open: tests only that app, without model calls.
.\.venv\Scripts\python.exe scripts\smoke-desktop.py
```

Tests cover ambiguous targets, protocol/tool failures, mutation timeouts, exact
assertions, preview mode, released-server element IDs, and Jev response validation.

## Roadmap

Weekend plan: [docs/PLAN.md](docs/PLAN.md).
