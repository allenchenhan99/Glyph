from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from glyph.config import get_settings
from glyph.contract_ai import create_implementation_contract_provider
from glyph.contract_jobs import (
    ImplementationContractJobExecutor,
    list_queued_contract_job_ids,
    recover_interrupted_contract_jobs,
)
from glyph.contract_routes import router as contract_router
from glyph.database import create_session_factory
from glyph.documents import router as documents_router
from glyph.research_ai import create_research_map_provider
from glyph.research_jobs import (
    ResearchMapJobExecutor,
    list_queued_job_ids,
    recover_interrupted_jobs,
)
from glyph.research_routes import router as research_router


def create_app() -> FastAPI:
    settings = get_settings()
    settings.book_dir.mkdir(parents=True, exist_ok=True)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    session_factory = create_session_factory(settings)

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
            contract_executor.shutdown()
            research_executor.shutdown()

    app = FastAPI(title="Glyph", lifespan=lifespan)
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.include_router(documents_router)
    app.include_router(research_router)
    app.include_router(contract_router)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "book_dir": str(settings.book_dir),
            "data_dir": str(settings.data_dir),
            "ocr_mode": settings.ocr_mode,
            "ai_mode": settings.ai_mode,
        }

    return app


app = create_app()
