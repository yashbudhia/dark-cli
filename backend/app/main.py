"""Dark API: MongoDB accounts, sessions and user-owned run records."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Path, Request
from fastapi.responses import JSONResponse
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError, PyMongoError

from .auth import AuthError, AuthService
from .auth_routes import Principal, Service, router
from .email import make_mailer
from .models import DesktopReport, Finding, RefusalEvent, Run, RunStatus
from .settings import Settings


def create_app(
    settings: Settings | None = None, *, database=None, mailer=None
) -> FastAPI:
    config = settings or Settings.from_env()
    config.validate()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        client = None
        try:
            db = database
            if db is None and config.configured:
                client = MongoClient(
                    config.mongo_uri,
                    serverSelectionTimeoutMS=5000,
                    connectTimeoutMS=5000,
                    socketTimeoutMS=5000,
                    waitQueueTimeoutMS=5000,
                    tz_aware=True,
                )
                db = client[config.mongo_database]
            if db is not None and len(config.auth_secret) >= 32:
                auth = AuthService(db, config, mailer or make_mailer(config))
                auth.indexes()
                application.state.auth = auth
            yield
        finally:
            if client is not None:
                client.close()

    application = FastAPI(title="Dark API", version="0.2.0", lifespan=lifespan)
    application.state.settings = config
    application.state.auth = None
    application.include_router(router)

    @application.middleware("http")
    async def private_responses(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @application.exception_handler(AuthError)
    async def auth_error(request: Request, exc: AuthError):
        return JSONResponse(
            status_code=exc.status,
            content={"error": exc.code, "detail": exc.message},
            headers={"Retry-After": str(exc.retry_after)}
            if exc.retry_after is not None
            else None,
        )

    @application.exception_handler(PyMongoError)
    async def database_error(request: Request, exc: PyMongoError):
        return JSONResponse(
            status_code=503,
            content={"detail": "Database is unavailable. Try again later."},
        )

    @application.get("/health")
    def health() -> dict:
        return {"status": "ok", "auth_configured": application.state.auth is not None}

    def owned_run(auth: AuthService, owner: str, run_id: str) -> dict:
        run = auth.db.runs.find_one({"owner_id": owner, "id": run_id})
        if run is None:
            raise HTTPException(404, "run not found")
        return run

    def replace_owned(collection, query: dict, value: dict) -> None:
        try:
            collection.replace_one(query, value, upsert=True)
        except DuplicateKeyError:
            # Concurrent idempotent imports may race to insert the unique owner/id.
            if not collection.replace_one(query, value).matched_count:
                raise

    @application.post("/api/runs", status_code=201)
    def create_run(run: Run, identity: Principal, auth: Service) -> Run:
        try:
            auth.db.runs.insert_one(
                {**run.model_dump(mode="json"), "owner_id": identity[0]["_id"]}
            )
        except DuplicateKeyError as exc:
            raise HTTPException(409, "run already exists") from exc
        return run

    @application.get("/api/runs")
    def list_runs(identity: Principal, auth: Service) -> list[Run]:
        return [
            Run.model_validate(row)
            for row in auth.db.runs.find(
                {"owner_id": identity[0]["_id"]}, {"desktop_report": 0}
            )
            .sort("started_at", -1)
            .limit(100)
        ]

    @application.put("/api/runs/import/{fingerprint}")
    def import_desktop_run(
        report: DesktopReport,
        identity: Principal,
        auth: Service,
        fingerprint: str = Path(pattern=r"^[a-f0-9]{64}$"),
    ) -> Run:
        owner = identity[0]["_id"]
        run = Run(
            id=f"desktop_{fingerprint}",
            kind="desktop",
            target=report.window_title,
            goal=report.scenario or "Desktop observation",
            status=RunStatus(report.status),
            started_at=report.finished_at,
            finished_at=report.finished_at,
            desktop_report=report,
        )
        # Stable import IDs make a retry after an ambiguous network failure safe.
        replace_owned(
            auth.db.runs,
            {"owner_id": owner, "id": run.id},
            {**run.model_dump(mode="json"), "owner_id": owner},
        )
        return run

    @application.get("/api/runs/{run_id}")
    def get_run(run_id: str, identity: Principal, auth: Service) -> Run:
        return Run.model_validate(owned_run(auth, identity[0]["_id"], run_id))

    @application.post("/api/runs/{run_id}/findings", status_code=201)
    def add_finding(
        run_id: str, finding: Finding, identity: Principal, auth: Service
    ) -> Finding:
        owner = identity[0]["_id"]
        owned_run(auth, owner, run_id)
        finding.run_id = run_id
        replace_owned(
            auth.db.findings,
            {"owner_id": owner, "run_id": run_id, "id": finding.id},
            {**finding.model_dump(mode="json"), "owner_id": owner},
        )
        return finding

    @application.get("/api/runs/{run_id}/findings")
    def list_findings(run_id: str, identity: Principal, auth: Service) -> list[Finding]:
        owner = identity[0]["_id"]
        owned_run(auth, owner, run_id)
        return [
            Finding.model_validate(row)
            for row in auth.db.findings.find({"owner_id": owner, "run_id": run_id})
        ]

    @application.post("/api/runs/{run_id}/refusals", status_code=201)
    def add_refusal(
        run_id: str, event: RefusalEvent, identity: Principal, auth: Service
    ) -> RefusalEvent:
        owner = identity[0]["_id"]
        owned_run(auth, owner, run_id)
        event.run_id = run_id
        replace_owned(
            auth.db.refusals,
            {"owner_id": owner, "run_id": run_id, "id": event.id},
            {**event.model_dump(mode="json"), "owner_id": owner},
        )
        return event

    @application.get("/api/runs/{run_id}/refusals")
    def list_refusals(
        run_id: str, identity: Principal, auth: Service
    ) -> list[RefusalEvent]:
        owner = identity[0]["_id"]
        owned_run(auth, owner, run_id)
        return [
            RefusalEvent.model_validate(row)
            for row in auth.db.refusals.find({"owner_id": owner, "run_id": run_id})
        ]

    return application


app = create_app()
