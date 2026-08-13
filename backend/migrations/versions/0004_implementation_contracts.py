"""Add auditable Implementation Contract storage."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_implementation_contracts"
down_revision: str | None = "0003_research_maps"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "implementation_contract_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("research_map_version_id", sa.String(length=36), nullable=False),
        sa.Column("previous_version_id", sa.String(length=36), nullable=True),
        sa.Column("source_content_hash", sa.String(length=64), nullable=False),
        sa.Column("research_map_signature", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("readiness", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"]),
        sa.ForeignKeyConstraint(
            ["previous_version_id"], ["implementation_contract_versions.id"]
        ),
        sa.ForeignKeyConstraint(
            ["research_map_version_id"], ["research_map_versions.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_implementation_contract_versions_document_id",
        "implementation_contract_versions",
        ["document_id"],
    )
    op.create_index(
        "ix_implementation_contract_versions_research_map_id",
        "implementation_contract_versions",
        ["research_map_version_id"],
    )
    op.create_index(
        "uq_implementation_contract_active_document",
        "implementation_contract_versions",
        ["document_id"],
        unique=True,
        sqlite_where=sa.text("is_active = 1"),
    )

    op.create_table(
        "implementation_contract_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("contract_version_id", sa.String(length=36), nullable=False),
        sa.Column("item_key", sa.String(length=128), nullable=False),
        sa.Column("section", sa.String(length=64), nullable=False),
        sa.Column("item_type", sa.String(length=64), nullable=False),
        sa.Column("draft_value_json", sa.Text(), nullable=True),
        sa.Column("origin", sa.String(length=32), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("is_blocking", sa.Boolean(), nullable=False),
        sa.Column("is_optional", sa.Boolean(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("item_signature", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["contract_version_id"], ["implementation_contract_versions.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("contract_version_id", "item_key"),
    )
    op.create_index(
        "ix_implementation_contract_items_version_order",
        "implementation_contract_items",
        ["contract_version_id", "display_order"],
    )
    op.create_index(
        "ix_implementation_contract_items_signature",
        "implementation_contract_items",
        ["item_signature"],
    )

    op.create_table(
        "implementation_contract_evidence",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("item_id", sa.String(length=36), nullable=False),
        sa.Column("block_id", sa.String(length=36), nullable=False),
        sa.Column("research_node_id", sa.String(length=36), nullable=True),
        sa.Column("locator_type", sa.String(length=32), nullable=False),
        sa.Column("quote_text", sa.Text(), nullable=False),
        sa.Column("quote_start", sa.Integer(), nullable=False),
        sa.Column("quote_end", sa.Integer(), nullable=False),
        sa.Column("source_quote_hash", sa.String(length=64), nullable=False),
        sa.Column("relation", sa.String(length=32), nullable=False),
        sa.Column("source_label", sa.String(length=512), nullable=True),
        sa.ForeignKeyConstraint(["block_id"], ["blocks.id"]),
        sa.ForeignKeyConstraint(["item_id"], ["implementation_contract_items.id"]),
        sa.ForeignKeyConstraint(["research_node_id"], ["research_nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "item_id", "block_id", "quote_start", "quote_end", "relation"
        ),
    )
    op.create_index(
        "ix_implementation_contract_evidence_item_id",
        "implementation_contract_evidence",
        ["item_id"],
    )
    op.create_index(
        "ix_implementation_contract_evidence_block_id",
        "implementation_contract_evidence",
        ["block_id"],
    )
    op.create_index(
        "ix_implementation_contract_evidence_node_id",
        "implementation_contract_evidence",
        ["research_node_id"],
    )

    op.create_table(
        "implementation_contract_resolutions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("item_id", sa.String(length=36), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("supersedes_resolution_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("resolved_value_json", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("based_on_contract_version_id", sa.String(length=36), nullable=False),
        sa.Column("based_on_item_signature", sa.String(length=64), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["based_on_contract_version_id"],
            ["implementation_contract_versions.id"],
        ),
        sa.ForeignKeyConstraint(["item_id"], ["implementation_contract_items.id"]),
        sa.ForeignKeyConstraint(
            ["supersedes_resolution_id"], ["implementation_contract_resolutions.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("item_id", "request_id"),
        sa.UniqueConstraint("item_id", "revision_number"),
    )
    op.create_index(
        "ix_implementation_contract_resolutions_item_time",
        "implementation_contract_resolutions",
        ["item_id", "resolved_at"],
    )

    op.create_table(
        "implementation_contract_issues",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("contract_version_id", sa.String(length=36), nullable=False),
        sa.Column("item_id", sa.String(length=36), nullable=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["contract_version_id"], ["implementation_contract_versions.id"]
        ),
        sa.ForeignKeyConstraint(["item_id"], ["implementation_contract_items.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_implementation_contract_issues_version_id",
        "implementation_contract_issues",
        ["contract_version_id"],
    )

    op.create_table(
        "implementation_contract_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("contract_version_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("stage", sa.String(length=64), nullable=False),
        sa.Column("progress", sa.Float(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("lease_token", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["contract_version_id"], ["implementation_contract_versions.id"]
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_implementation_contract_jobs_document_status",
        "implementation_contract_jobs",
        ["document_id", "status"],
    )
    op.create_index(
        "uq_implementation_contract_active_job",
        "implementation_contract_jobs",
        ["document_id"],
        unique=True,
        sqlite_where=sa.text("status IN ('queued', 'running')"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_implementation_contract_active_job",
        table_name="implementation_contract_jobs",
    )
    op.drop_index(
        "ix_implementation_contract_jobs_document_status",
        table_name="implementation_contract_jobs",
    )
    op.drop_table("implementation_contract_jobs")
    op.drop_index(
        "ix_implementation_contract_issues_version_id",
        table_name="implementation_contract_issues",
    )
    op.drop_table("implementation_contract_issues")
    op.drop_index(
        "ix_implementation_contract_resolutions_item_time",
        table_name="implementation_contract_resolutions",
    )
    op.drop_table("implementation_contract_resolutions")
    op.drop_index(
        "ix_implementation_contract_evidence_node_id",
        table_name="implementation_contract_evidence",
    )
    op.drop_index(
        "ix_implementation_contract_evidence_block_id",
        table_name="implementation_contract_evidence",
    )
    op.drop_index(
        "ix_implementation_contract_evidence_item_id",
        table_name="implementation_contract_evidence",
    )
    op.drop_table("implementation_contract_evidence")
    op.drop_index(
        "ix_implementation_contract_items_signature",
        table_name="implementation_contract_items",
    )
    op.drop_index(
        "ix_implementation_contract_items_version_order",
        table_name="implementation_contract_items",
    )
    op.drop_table("implementation_contract_items")
    op.drop_index(
        "uq_implementation_contract_active_document",
        table_name="implementation_contract_versions",
    )
    op.drop_index(
        "ix_implementation_contract_versions_research_map_id",
        table_name="implementation_contract_versions",
    )
    op.drop_index(
        "ix_implementation_contract_versions_document_id",
        table_name="implementation_contract_versions",
    )
    op.drop_table("implementation_contract_versions")
