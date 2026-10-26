"""dark-cli backend: stores runs, findings, and telemetry; serves the dashboard."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .models import Finding, RefusalEvent, Run

app = FastAPI(title="dark-cli backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store for the scaffold; SQLite lands with milestone 3.
_runs: dict[str, Run] = {}
_findings: dict[str, Finding] = {}
_refusals: dict[str, RefusalEvent] = {}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/runs", status_code=201)
def create_run(run: Run) -> Run:
    _runs[run.id] = run
    return run


@app.get("/api/runs")
def list_runs() -> list[Run]:
    return list(_runs.values())


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> Run:
    run = _runs.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run


@app.post("/api/runs/{run_id}/findings", status_code=201)
def add_finding(run_id: str, finding: Finding) -> Finding:
    if run_id not in _runs:
        raise HTTPException(status_code=404, detail="run not found")
    finding.run_id = run_id
    _findings[finding.id] = finding
    return finding


@app.get("/api/runs/{run_id}/findings")
def list_findings(run_id: str) -> list[Finding]:
    return [f for f in _findings.values() if f.run_id == run_id]


@app.post("/api/runs/{run_id}/refusals", status_code=201)
def add_refusal(run_id: str, event: RefusalEvent) -> RefusalEvent:
    if run_id not in _runs:
        raise HTTPException(status_code=404, detail="run not found")
    event.run_id = run_id
    _refusals[event.id] = event
    return event


@app.get("/api/runs/{run_id}/refusals")
def list_refusals(run_id: str) -> list[RefusalEvent]:
    return [r for r in _refusals.values() if r.run_id == run_id]
