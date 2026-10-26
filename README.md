# dark-cli

An AI red-teaming CLI that finds — and proves — security bugs in software you're authorized to test. Abliterated models power the attack side where mainstream models add refusal friction to legitimate security work.

## What it does

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
| `cli/` | Python + Typer | The `dark` command: scan, ctf, report |
| `backend/` | FastAPI | Stores runs, findings, refusal telemetry; serves the dashboard |
| `frontend/` | Vite + React | Findings dashboard |

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

```bash
# CLI
cd cli && pip install -e . && dark --help

# Backend
cd backend && pip install -e . && uvicorn app.main:app --reload

# Frontend
cd frontend && npm install && npm run dev   # http://localhost:5173
```

Model endpoints are configured via `.env` (see `.env.example`).

## Roadmap

Weekend plan: [docs/PLAN.md](docs/PLAN.md).
