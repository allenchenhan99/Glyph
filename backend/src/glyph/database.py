from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session, sessionmaker

from glyph.config import Settings
from glyph.models import Base


def create_session_factory(settings: Settings) -> sessionmaker[Session]:
    if settings.database_url.startswith("sqlite:///"):
        db_path = Path(settings.database_url.removeprefix("sqlite:///"))
        db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    migrate_sqlite_schema(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def migrate_sqlite_schema(engine) -> None:
    if engine.dialect.name != "sqlite" or not inspect(engine).has_table("blocks"):
        return
    columns = {column["name"] for column in inspect(engine).get_columns("blocks")}
    if "formula_latex" not in columns:
        with engine.begin() as connection:
            connection.exec_driver_sql("ALTER TABLE blocks ADD COLUMN formula_latex TEXT")


def session_scope(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
