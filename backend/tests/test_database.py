from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import create_engine, inspect, text

from glyph import models as model_module
from glyph.config import Settings
from glyph.database import alembic_config, create_session_factory
from glyph.models import (
    ResearchEvidence,
    ResearchMapIssue,
    ResearchMapJob,
    ResearchMapVersion,
    ResearchNode,
    ResearchNodeReview,
)

LEGACY_TABLES = {
    "blocks",
    "documents",
    "pages",
    "processing_jobs",
    "sections",
    "summaries",
}

RESEARCH_MAP_TABLES = {
    "research_evidence",
    "research_map_issues",
    "research_map_jobs",
    "research_map_versions",
    "research_node_reviews",
    "research_nodes",
}

CONTRACT_TABLES = {
    "implementation_contract_evidence",
    "implementation_contract_issues",
    "implementation_contract_items",
    "implementation_contract_jobs",
    "implementation_contract_resolutions",
    "implementation_contract_versions",
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


def create_revision_0003_database(settings: Settings) -> dict[str, tuple[tuple, ...]]:
    database_path = Path(settings.database_url.removeprefix("sqlite:///"))
    database_path.parent.mkdir(parents=True, exist_ok=True)
    command.upgrade(alembic_config(settings.database_url), "0003_research_maps")
    engine = create_unmigrated_engine(settings)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO documents ("
                "id, title, source_path, content_hash, processed_content_hash, "
                "file_type, status, created_at, updated_at"
                ") VALUES ("
                "'document-0003', 'Mapped paper', '/tmp/mapped.pdf', "
                "'source-hash', 'source-hash', 'pdf', 'completed', "
                "'2026-08-12 10:00:00', '2026-08-12 10:00:00'"
                ")"
            )
        )
        connection.execute(
            text(
                "INSERT INTO blocks ("
                "id, document_id, source_content_hash, section_id, order_index, "
                "page_number, block_type, source_text, translated_text, "
                "formula_latex, confidence"
                ") VALUES ("
                "'block-0003', 'document-0003', 'source-hash', NULL, 0, 1, "
                "'paragraph', 'The signal is formed monthly.', "
                "'此訊號每月形成。', NULL, 1.0"
                ")"
            )
        )
        connection.execute(
            text(
                "INSERT INTO research_map_versions ("
                "id, document_id, previous_version_id, source_content_hash, "
                "schema_version, provider, model_name, status, is_active, "
                "created_at, completed_at"
                ") VALUES ("
                "'map-0003', 'document-0003', NULL, 'source-hash', '1', "
                "'mock', NULL, 'complete', 1, '2026-08-12 10:01:00', "
                "'2026-08-12 10:02:00'"
                ")"
            )
        )
        connection.execute(
            text(
                "INSERT INTO research_nodes ("
                "id, map_version_id, parent_node_id, node_key, node_type, "
                "title, claim_text, explanation, provenance, evidence_quality, "
                "display_order, node_signature"
                ") VALUES ("
                "'node-0003', 'map-0003', NULL, 'signal_definition.1', "
                "'signal_definition', 'Signal', 'The signal is formed monthly.', "
                "'Formation timing.', 'author_explicit', 'direct', 0, "
                "'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'"
                ")"
            )
        )
        connection.execute(
            text(
                "INSERT INTO research_evidence ("
                "id, node_id, block_id, locator_type, quote_text, quote_start, "
                "quote_end, source_quote_hash, relation, source_label"
                ") VALUES ("
                "'evidence-0003', 'node-0003', 'block-0003', 'text_span', "
                "'The signal is formed monthly.', 0, 29, "
                "'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', "
                "'supports', NULL"
                ")"
            )
        )
        connection.execute(
            text(
                "INSERT INTO research_node_reviews ("
                "id, node_id, revision_number, supersedes_review_id, status, "
                "corrected_claim_text, review_note, based_on_map_version_id, "
                "based_on_node_signature, reviewed_at"
                ") VALUES ("
                "'review-0003', 'node-0003', 1, NULL, 'confirmed', NULL, "
                "'Checked against the source.', 'map-0003', "
                "'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', "
                "'2026-08-12 10:03:00'"
                ")"
            )
        )
    return snapshot_tables(
        engine,
        (
            "documents",
            "blocks",
            "research_map_versions",
            "research_nodes",
            "research_evidence",
            "research_node_reviews",
        ),
    )


def snapshot_tables(
    engine, table_names: tuple[str, ...]
) -> dict[str, tuple[tuple, ...]]:
    with engine.connect() as connection:
        return {
            table_name: tuple(
                tuple(row)
                for row in connection.execute(
                    text(f"SELECT * FROM {table_name} ORDER BY id")
                )
            )
            for table_name in table_names
        }


def test_empty_database_is_created_at_migration_head(tmp_path):
    factory = create_session_factory(make_settings(tmp_path))
    inspector = inspect(factory.kw["bind"])

    assert set(inspector.get_table_names()) >= (
        LEGACY_TABLES | RESEARCH_MAP_TABLES | CONTRACT_TABLES
    )
    assert "alembic_version" in inspector.get_table_names()
    assert "processed_content_hash" in {
        column["name"] for column in inspector.get_columns("documents")
    }
    assert "source_content_hash" in {
        column["name"] for column in inspector.get_columns("blocks")
    }


def test_runtime_sqlite_connections_enforce_foreign_keys(tmp_path):
    factory = create_session_factory(make_settings(tmp_path))

    with factory() as session:
        enabled = session.execute(text("PRAGMA foreign_keys")).scalar_one()

    assert enabled == 1


def test_contract_migration_preserves_reader_and_research_map(tmp_path):
    settings = make_settings(tmp_path)
    before = create_revision_0003_database(settings)

    factory = create_session_factory(settings)
    engine = factory.kw["bind"]
    after = snapshot_tables(engine, tuple(before))
    inspector = inspect(engine)

    assert after == before
    assert set(inspector.get_table_names()) >= CONTRACT_TABLES
    with factory() as session:
        counts = {
            table_name: session.execute(
                text(f"SELECT COUNT(*) FROM {table_name}")
            ).scalar_one()
            for table_name in CONTRACT_TABLES
        }
        revision = session.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
    assert counts == dict.fromkeys(CONTRACT_TABLES, 0)
    assert revision == "0005_contract_job_map_selection"


def test_contract_migration_declares_expected_foreign_keys(tmp_path):
    factory = create_session_factory(make_settings(tmp_path))
    inspector = inspect(factory.kw["bind"])
    expected_targets = {
        "implementation_contract_versions": {
            "documents",
            "implementation_contract_versions",
            "research_map_versions",
        },
        "implementation_contract_items": {"implementation_contract_versions"},
        "implementation_contract_evidence": {
            "blocks",
            "implementation_contract_items",
            "research_nodes",
        },
        "implementation_contract_resolutions": {
            "implementation_contract_items",
            "implementation_contract_resolutions",
            "implementation_contract_versions",
        },
        "implementation_contract_issues": {
            "implementation_contract_items",
            "implementation_contract_versions",
        },
        "implementation_contract_jobs": {
            "documents",
            "implementation_contract_versions",
            "research_map_versions",
        },
    }

    for table_name, targets in expected_targets.items():
        actual_targets = {
            foreign_key["referred_table"]
            for foreign_key in inspector.get_foreign_keys(table_name)
        }
        assert actual_targets == targets


def test_contract_migration_declares_identity_and_active_row_constraints(tmp_path):
    factory = create_session_factory(make_settings(tmp_path))
    inspector = inspect(factory.kw["bind"])

    expected_unique_columns = {
        "implementation_contract_versions": set(),
        "implementation_contract_items": {("contract_version_id", "item_key")},
        "implementation_contract_evidence": {
            ("item_id", "block_id", "quote_start", "quote_end", "relation")
        },
        "implementation_contract_resolutions": {
            ("item_id", "revision_number"),
            ("item_id", "request_id"),
        },
    }
    for table_name, expected in expected_unique_columns.items():
        actual = {
            tuple(constraint["column_names"])
            for constraint in inspector.get_unique_constraints(table_name)
        }
        assert actual == expected

    version_indexes = {
        item["name"]: item
        for item in inspector.get_indexes("implementation_contract_versions")
    }
    job_indexes = {
        item["name"]: item
        for item in inspector.get_indexes("implementation_contract_jobs")
    }
    assert version_indexes["uq_implementation_contract_active_document"]["unique"] == 1
    assert job_indexes["uq_implementation_contract_active_job"]["unique"] == 1
    assert "requested_research_map_version_id" in {
        column["name"]
        for column in inspector.get_columns("implementation_contract_jobs")
    }


def test_contract_job_map_selection_migration_preserves_existing_jobs(tmp_path):
    settings = make_settings(tmp_path)
    create_unmigrated_engine(settings).dispose()
    command.upgrade(
        alembic_config(settings.database_url), "0004_implementation_contracts"
    )
    engine = create_engine(settings.database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO documents "
                "(id, title, source_path, content_hash, processed_content_hash, "
                "file_type, status, created_at, updated_at) VALUES "
                "('document-job', 'Job paper', '/tmp/job.pdf', :hash, :hash, "
                "'pdf', 'completed', '2026-01-01', '2026-01-01')"
            ),
            {"hash": "a" * 64},
        )
        connection.execute(
            text(
                "INSERT INTO implementation_contract_jobs "
                "(id, document_id, contract_version_id, status, stage, progress, "
                "error_message, attempt_count, lease_token, created_at, updated_at) "
                "VALUES ('job-existing', 'document-job', NULL, 'queued', 'queued', "
                "0, NULL, 0, NULL, '2026-01-01', '2026-01-01')"
            )
        )
    engine.dispose()

    factory = create_session_factory(settings)

    with factory() as session:
        row = session.execute(
            text(
                "SELECT id, document_id, contract_version_id, "
                "requested_research_map_version_id, status, stage, progress, "
                "error_message, attempt_count, lease_token, created_at, updated_at "
                "FROM implementation_contract_jobs WHERE id = 'job-existing'"
            )
        ).one()
        revision = session.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()

    assert row == (
        "job-existing",
        "document-job",
        None,
        None,
        "queued",
        "queued",
        0.0,
        None,
        0,
        None,
        "2026-01-01",
        "2026-01-01",
    )
    assert revision == "0005_contract_job_map_selection"


def test_contract_models_expose_domain_relationships():
    expected_relationships = {
        "ImplementationContractVersion": {
            "document",
            "research_map_version",
            "previous_version",
            "items",
            "issues",
            "jobs",
            "resolutions",
        },
        "ImplementationContractItem": {
            "contract_version",
            "evidence",
            "resolutions",
            "issues",
        },
        "ImplementationContractEvidence": {"item", "block", "research_node"},
        "ImplementationContractResolution": {
            "item",
            "supersedes_resolution",
            "based_on_contract_version",
        },
        "ImplementationContractIssue": {"contract_version", "item"},
        "ImplementationContractJob": {
            "document",
            "contract_version",
            "requested_research_map_version",
        },
    }
    contract_models = {
        name: getattr(model_module, name, None) for name in expected_relationships
    }
    assert all(contract_models.values()), "contract ORM models are missing"
    for name, relationships in expected_relationships.items():
        assert set(inspect(contract_models[name]).relationships.keys()) == relationships


def test_research_map_migration_declares_expected_foreign_keys(tmp_path):
    factory = create_session_factory(make_settings(tmp_path))
    inspector = inspect(factory.kw["bind"])

    expected_targets = {
        "research_map_versions": {"documents", "research_map_versions"},
        "research_nodes": {"research_map_versions", "research_nodes"},
        "research_evidence": {"research_nodes", "blocks"},
        "research_node_reviews": {
            "research_nodes",
            "research_map_versions",
            "research_node_reviews",
        },
        "research_map_issues": {"research_map_versions", "research_nodes"},
        "research_map_jobs": {"documents", "research_map_versions"},
    }

    for table_name, targets in expected_targets.items():
        actual_targets = {
            foreign_key["referred_table"]
            for foreign_key in inspector.get_foreign_keys(table_name)
        }
        assert actual_targets == targets


def test_research_map_migration_declares_identity_and_active_row_constraints(
    tmp_path,
):
    factory = create_session_factory(make_settings(tmp_path))
    inspector = inspect(factory.kw["bind"])

    version_constraints = inspector.get_unique_constraints("research_map_versions")
    node_constraints = inspector.get_unique_constraints("research_nodes")
    evidence_constraints = inspector.get_unique_constraints("research_evidence")
    review_constraints = inspector.get_unique_constraints("research_node_reviews")
    assert {tuple(item["column_names"]) for item in version_constraints} == set()
    assert {tuple(item["column_names"]) for item in node_constraints} == {
        ("map_version_id", "node_key")
    }
    assert {tuple(item["column_names"]) for item in evidence_constraints} == {
        ("node_id", "block_id", "quote_start", "quote_end", "relation")
    }
    assert {tuple(item["column_names"]) for item in review_constraints} == {
        ("node_id", "revision_number")
    }

    version_indexes = {
        item["name"]: item for item in inspector.get_indexes("research_map_versions")
    }
    job_indexes = {
        item["name"]: item for item in inspector.get_indexes("research_map_jobs")
    }
    assert version_indexes["uq_research_map_active_document"]["unique"] == 1
    assert job_indexes["uq_research_map_active_job"]["unique"] == 1


def test_research_map_models_expose_domain_relationships():
    expected_relationships = {
        ResearchMapVersion: {
            "document",
            "previous_version",
            "nodes",
            "issues",
            "jobs",
            "reviews",
            "implementation_contract_versions",
            "requested_implementation_contract_jobs",
        },
        ResearchNode: {
            "map_version",
            "parent",
            "children",
            "evidence",
            "reviews",
            "issues",
            "implementation_contract_evidence",
        },
        ResearchEvidence: {"node", "block"},
        ResearchNodeReview: {
            "node",
            "based_on_map_version",
            "supersedes_review",
        },
        ResearchMapIssue: {"map_version", "node"},
        ResearchMapJob: {"document", "map_version"},
    }

    for model, relationships in expected_relationships.items():
        assert set(inspect(model).relationships.keys()) == relationships


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


def test_research_map_migration_preserves_reader_and_invents_no_map_rows(tmp_path):
    settings = make_settings(tmp_path)
    create_legacy_database(settings)

    factory = create_session_factory(settings)

    with factory() as session:
        document = session.execute(
            text(
                "SELECT id, title, source_path, content_hash, file_type, status, "
                "created_at, updated_at FROM documents WHERE id = 'document-1'"
            )
        ).one()
        block = session.execute(
            text(
                "SELECT id, document_id, section_id, order_index, page_number, "
                "block_type, source_text, translated_text, confidence "
                "FROM blocks WHERE id = 'block-1'"
            )
        ).one()
        map_row_counts = {
            table_name: session.execute(
                text(f"SELECT COUNT(*) FROM {table_name}")
            ).scalar_one()
            for table_name in RESEARCH_MAP_TABLES
        }
        revision = session.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
        block_source_hash = session.execute(
            text("SELECT source_content_hash FROM blocks WHERE id = 'block-1'")
        ).scalar_one()

    assert document == (
        "document-1",
        "Legacy paper",
        "/tmp/legacy.pdf",
        "legacy-hash",
        "pdf",
        "completed",
        "2026-01-01",
        "2026-01-01",
    )
    assert block == (
        "block-1",
        "document-1",
        None,
        0,
        1,
        "paragraph",
        "Legacy source",
        "舊譯文",
        1.0,
    )
    assert map_row_counts == dict.fromkeys(RESEARCH_MAP_TABLES, 0)
    assert block_source_hash == "legacy-hash"
    assert revision == "0005_contract_job_map_selection"


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
