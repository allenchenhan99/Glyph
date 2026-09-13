from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from glyph.config import get_settings, resolve_translation_settings
from glyph.contract_ai import create_implementation_contract_provider
from glyph.contract_jobs import (
    ImplementationContractJobExecutor,
    list_queued_contract_job_ids,
    recover_interrupted_contract_jobs,
)
from glyph.contract_routes import router as contract_router
from glyph.database import DatabaseMigrationError, create_session_factory
from glyph.documents import router as documents_router
from glyph.processing_jobs import ProcessingJobExecutor, mark_interrupted_jobs
from glyph.provider_settings import router as provider_settings_router
from glyph.research_ai import create_research_map_provider
from glyph.research_jobs import (
    ResearchMapJobExecutor,
    list_queued_job_ids,
    recover_interrupted_jobs,
)
from glyph.research_routes import router as research_router
from glyph.summary_jobs import SummaryJobExecutor, mark_interrupted_summary_jobs
from glyph.summary_routes import router as summary_router
from glyph.workspace import blocked_workspace, describe_workspace
from glyph.workspace import router as workspace_router

DATABASE_RECOVERY = (
    "The Glyph database in {data_dir} uses an unsupported schema and was left "
    "unchanged. Recovery: keep that file where it is, choose a new empty "
    "GLYPH_DATA_DIR (and update GLYPH_DATABASE_URL if you set it explicitly), "
    "then restart Glyph. Glyph never moves, deletes, resets or converts the old "
    "database automatically."
)
CONFIGURATION_RECOVERY = (
    "Glyph could not start because of an invalid configuration value: {problem}. "
    "Fix that environment variable in .env or your shell, then restart Glyph. "
    "No data was changed."
)


def create_app() -> FastAPI:
    try:
        settings = get_settings()
    except ValueError as exc:
        # Config errors name the variable and the allowed shape, never the value.
        return create_diagnostic_app(CONFIGURATION_RECOVERY.format(problem=exc))
    settings.book_dir.mkdir(parents=True, exist_ok=True)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    try:
        session_factory = create_session_factory(settings)
    except DatabaseMigrationError:
        return create_diagnostic_app(
            DATABASE_RECOVERY.format(data_dir=settings.data_dir)
        )
    # Unfinished document jobs from a previous process cannot be resumed without
    # their in-memory credentials; surface them as interrupted, never replay them.
    with session_factory.begin() as session:
        mark_interrupted_jobs(session, settings)
        mark_interrupted_summary_jobs(session)
    processing_executor = ProcessingJobExecutor(session_factory, settings)
    summary_executor = SummaryJobExecutor(session_factory, settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        research_executor = ResearchMapJobExecutor(
            session_factory,
            lambda: create_research_map_provider(settings),
        )
        contract_executor = ImplementationContractJobExecutor(
            session_factory,
            lambda: create_implementation_contract_provider(settings),
        )
        app.state.research_job_executor = research_executor
        app.state.contract_job_executor = contract_executor
        with session_factory.begin() as session:
            recover_interrupted_jobs(session, settings.research_job_max_attempts)
            recover_interrupted_contract_jobs(
                session, settings.research_job_max_attempts
            )
            queued_research_job_ids = list_queued_job_ids(session)
            queued_contract_job_ids = list_queued_contract_job_ids(session)
        for job_id in queued_research_job_ids:
            research_executor.submit(job_id)
        for job_id in queued_contract_job_ids:
            contract_executor.submit(job_id)
        try:
            yield
        finally:
            summary_executor.shutdown()
            processing_executor.shutdown()
            contract_executor.shutdown()
            research_executor.shutdown()

    app = FastAPI(title="Glyph", lifespan=lifespan)
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.processing_job_executor = processing_executor
    app.state.summary_job_executor = summary_executor
    app.state.workspace_view = lambda: describe_workspace(settings)
    app.include_router(workspace_router)
    app.include_router(documents_router)
    app.include_router(summary_router)
    app.include_router(research_router)
    app.include_router(contract_router)
    app.include_router(provider_settings_router)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "book_dir": str(settings.book_dir),
            "data_dir": str(settings.data_dir),
            "ocr_mode": settings.ocr_mode,
            "ai_mode": settings.ai_mode,
            "translation_provider": resolve_translation_settings(settings).provider,
        }

    return app


def create_diagnostic_app(recovery: str) -> FastAPI:
    """Serve only workspace and health so the UI can show recovery guidance."""
    app = FastAPI(title="Glyph (recovery required)")
    app.state.settings = None
    app.state.workspace_view = lambda: blocked_workspace(recovery)
    app.include_router(workspace_router)

    @app.get("/api/health")
    def blocked_health() -> dict[str, str]:
        return {"status": "blocked", "recovery": recovery}

    @app.api_route(
        "/api/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        include_in_schema=False,
    )
    def unavailable(path: str) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"detail": f"Glyph needs recovery before use. {recovery}"},
        )

    return app


app = create_app()
