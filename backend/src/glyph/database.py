from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, event, inspect
from sqlalchemy.orm import Session, sessionmaker

from glyph.config import Settings

LEGACY_REVISION = "0001_legacy_baseline"
LEGACY_TABLES = {
    "blocks",
    "documents",
    "pages",
    "processing_jobs",
    "sections",
    "summaries",
}


class DatabaseMigrationError(RuntimeError):
    """Raised when a database cannot be upgraded without risking user data."""


def create_session_factory(settings: Settings) -> sessionmaker[Session]:
    ensure_sqlite_parent_exists(settings.database_url)
    upgrade_database(settings)
    engine = create_engine(
        settings.database_url, connect_args=sqlite_connect_args(settings.database_url)
    )
    enable_sqlite_foreign_keys(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def enable_sqlite_foreign_keys(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()


def ensure_sqlite_parent_exists(database_url: str) -> None:
    if database_url.startswith("sqlite:///"):
        Path(database_url.removeprefix("sqlite:///")).parent.mkdir(
            parents=True, exist_ok=True
        )


def sqlite_connect_args(database_url: str) -> dict[str, bool]:
    if database_url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


def upgrade_database(settings: Settings) -> None:
    engine = create_engine(
        settings.database_url, connect_args=sqlite_connect_args(settings.database_url)
    )
    try:
        prepare_legacy_database(engine)
    finally:
        engine.dispose()
    command.upgrade(alembic_config(settings.database_url), "head")


def prepare_legacy_database(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if not tables or "alembic_version" in tables:
        return
    if tables != LEGACY_TABLES:
        names = ", ".join(sorted(tables))
        raise DatabaseMigrationError(
            f"Database has an unrecognized schema ({names}); no changes were made."
        )
    ensure_legacy_formula_column(engine)
    config = alembic_config(str(engine.url))
    command.stamp(config, LEGACY_REVISION)


def ensure_legacy_formula_column(engine: Engine) -> None:
    columns = {column["name"] for column in inspect(engine).get_columns("blocks")}
    if "formula_latex" not in columns:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "ALTER TABLE blocks ADD COLUMN formula_latex TEXT"
            )


def alembic_config(database_url: str) -> Config:
    backend_dir = Path(__file__).resolve().parents[2]
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


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
