from __future__ import annotations

from fastapi import FastAPI

from glyph.config import get_settings
from glyph.database import create_session_factory
from glyph.documents import router as documents_router


def create_app() -> FastAPI:
    settings = get_settings()
    settings.book_dir.mkdir(parents=True, exist_ok=True)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    app = FastAPI(title="Glyph")
    app.state.settings = settings
    app.state.session_factory = create_session_factory(settings)
    app.include_router(documents_router)

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
