from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from glyph.config import Settings
from glyph.database import create_session_factory

LEGACY_TABLES = {
    "blocks",
    "documents",
    "pages",
    "processing_jobs",
    "sections",
    "summaries",
}

LEGACY_SCHEMA = (
    """
    CREATE TABLE documents (
        id VARCHAR(36) PRIMARY KEY,
        title VARCHAR(512) NOT NULL,
        source_path VARCHAR(2048) NOT NULL UNIQUE,
        content_hash VARCHAR(64) NOT NULL,
        file_type VARCHAR(16) NOT NULL,
        status VARCHAR(32) NOT NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL
    )
    """,
    """
    CREATE TABLE processing_jobs (
        id VARCHAR(36) PRIMARY KEY,
        document_id VARCHAR(36) NOT NULL REFERENCES documents(id),
        status VARCHAR(32) NOT NULL,
        stage VARCHAR(64) NOT NULL,
        progress FLOAT NOT NULL,
        error_message TEXT,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL
    )
    """,
    """
    CREATE TABLE pages (
        id VARCHAR(36) PRIMARY KEY,
        document_id VARCHAR(36) NOT NULL REFERENCES documents(id),
        page_number INTEGER NOT NULL,
        image_path VARCHAR(2048),
        raw_text TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE sections (
        id VARCHAR(36) PRIMARY KEY,
        document_id VARCHAR(36) NOT NULL REFERENCES documents(id),
        title VARCHAR(512) NOT NULL,
        path VARCHAR(2048) NOT NULL,
        order_index INTEGER NOT NULL,
        parent_id VARCHAR(36) REFERENCES sections(id),
        summary TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE blocks (
        id VARCHAR(36) PRIMARY KEY,
        document_id VARCHAR(36) NOT NULL REFERENCES documents(id),
        section_id VARCHAR(36) REFERENCES sections(id),
        order_index INTEGER NOT NULL,
        page_number INTEGER NOT NULL,
        block_type VARCHAR(32) NOT NULL,
        source_text TEXT NOT NULL,
        translated_text TEXT NOT NULL,
        confidence FLOAT NOT NULL
    )
    """,
    """
    CREATE TABLE summaries (
        id VARCHAR(36) PRIMARY KEY,
        document_id VARCHAR(36) NOT NULL REFERENCES documents(id),
        section_id VARCHAR(36) REFERENCES sections(id),
        summary_text TEXT NOT NULL,
        created_at DATETIME NOT NULL
    )
    """,
)


def make_settings(tmp_path: Path, database_name: str = "glyph.sqlite3") -> Settings:
    data_dir = tmp_path / "data"
    return Settings(
        book_dir=tmp_path / "book",
        data_dir=data_dir,
        database_url=f"sqlite:///{data_dir / database_name}",
        ocr_mode="mock",
        ai_mode="mock",
        unlimited_ocr_repo=None,
        unlimited_ocr_command=None,
    )


def create_legacy_database(settings: Settings) -> None:
    engine = create_unmigrated_engine(settings)
    with engine.begin() as connection:
        for statement in LEGACY_SCHEMA:
            connection.exec_driver_sql(statement)
        connection.exec_driver_sql(
            """
            INSERT INTO documents (
                id, title, source_path, content_hash, file_type, status,
                created_at, updated_at
            ) VALUES (
                'document-1', 'Legacy paper', '/tmp/legacy.pdf', 'legacy-hash',
                'pdf', 'completed', '2026-01-01', '2026-01-01'
            )
            """
        )
        connection.exec_driver_sql(
            """
            INSERT INTO blocks (
                id, document_id, section_id, order_index, page_number,
                block_type, source_text, translated_text, confidence
            ) VALUES (
                'block-1', 'document-1', NULL, 0, 1, 'paragraph',
                'Legacy source', '舊譯文', 1.0
            )
            """
        )


def create_unmigrated_engine(settings: Settings):
    database_path = Path(settings.database_url.removeprefix("sqlite:///"))
    database_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(
        settings.database_url, connect_args={"check_same_thread": False}
    )


def test_empty_database_is_created_at_migration_head(tmp_path):
    factory = create_session_factory(make_settings(tmp_path))
    inspector = inspect(factory.kw["bind"])

    assert set(inspector.get_table_names()) > LEGACY_TABLES
    assert "alembic_version" in inspector.get_table_names()
    assert "processed_content_hash" in {
        column["name"] for column in inspector.get_columns("documents")
    }


def test_legacy_database_is_stamped_and_preserves_document_data(tmp_path):
    settings = make_settings(tmp_path)
    create_legacy_database(settings)

    factory = create_session_factory(settings)

    with factory() as session:
        document = session.execute(
            text("SELECT title, content_hash FROM documents WHERE id = 'document-1'")
        ).one()
        block = session.execute(
            text("SELECT source_text, translated_text FROM blocks WHERE id = 'block-1'")
        ).one()
    assert document == ("Legacy paper", "legacy-hash")
    assert block == ("Legacy source", "舊譯文")


def test_completed_legacy_document_backfills_processed_hash(tmp_path):
    settings = make_settings(tmp_path)
    create_legacy_database(settings)

    factory = create_session_factory(settings)

    with factory() as session:
        processed_hash = session.execute(
            text("SELECT processed_content_hash FROM documents WHERE id = 'document-1'")
        ).scalar_one()
    assert processed_hash == "legacy-hash"


def test_legacy_database_adds_formula_latex_column(tmp_path):
    settings = make_settings(tmp_path)
    create_legacy_database(settings)

    factory = create_session_factory(settings)

    columns = {
        column["name"] for column in inspect(factory.kw["bind"]).get_columns("blocks")
    }
    assert "formula_latex" in columns


def test_unrecognized_partial_schema_fails_without_dropping_tables(tmp_path):
    settings = make_settings(tmp_path)
    engine = create_unmigrated_engine(settings)
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE documents (id TEXT PRIMARY KEY)")

    with pytest.raises(RuntimeError, match="unrecognized"):
        create_session_factory(settings)

    inspector = inspect(engine)
    assert inspector.get_table_names() == ["documents"]
    assert [column["name"] for column in inspector.get_columns("documents")] == ["id"]
