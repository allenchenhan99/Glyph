"""Add immutable, evidence-backed Research Map storage."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_research_maps"
down_revision: str | None = "0002_reliability_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "research_map_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("previous_version_id", sa.String(length=36), nullable=True),
        sa.Column("source_content_hash", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"]),
        sa.ForeignKeyConstraint(["previous_version_id"], ["research_map_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_research_map_versions_document_id",
        "research_map_versions",
        ["document_id"],
    )
    op.create_index(
        "uq_research_map_active_document",
        "research_map_versions",
        ["document_id"],
        unique=True,
        sqlite_where=sa.text("is_active = 1"),
    )

    op.create_table(
        "research_nodes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("map_version_id", sa.String(length=36), nullable=False),
        sa.Column("parent_node_id", sa.String(length=36), nullable=True),
        sa.Column("node_key", sa.String(length=128), nullable=False),
        sa.Column("node_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("claim_text", sa.Text(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("provenance", sa.String(length=32), nullable=False),
        sa.Column("evidence_quality", sa.String(length=32), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("node_signature", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["map_version_id"], ["research_map_versions.id"]),
        sa.ForeignKeyConstraint(["parent_node_id"], ["research_nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("map_version_id", "node_key"),
    )
    op.create_index(
        "ix_research_nodes_map_version_order",
        "research_nodes",
        ["map_version_id", "display_order"],
    )
    op.create_index("ix_research_nodes_signature", "research_nodes", ["node_signature"])

    op.create_table(
        "research_evidence",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("node_id", sa.String(length=36), nullable=False),
        sa.Column("block_id", sa.String(length=36), nullable=False),
        sa.Column("locator_type", sa.String(length=32), nullable=False),
        sa.Column("quote_text", sa.Text(), nullable=False),
        sa.Column("quote_start", sa.Integer(), nullable=False),
        sa.Column("quote_end", sa.Integer(), nullable=False),
        sa.Column("source_quote_hash", sa.String(length=64), nullable=False),
        sa.Column("relation", sa.String(length=32), nullable=False),
        sa.Column("source_label", sa.String(length=512), nullable=True),
        sa.ForeignKeyConstraint(["block_id"], ["blocks.id"]),
        sa.ForeignKeyConstraint(["node_id"], ["research_nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "node_id", "block_id", "quote_start", "quote_end", "relation"
        ),
    )
    op.create_index("ix_research_evidence_node_id", "research_evidence", ["node_id"])
    op.create_index("ix_research_evidence_block_id", "research_evidence", ["block_id"])

    op.create_table(
        "research_node_reviews",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("node_id", sa.String(length=36), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("supersedes_review_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("corrected_claim_text", sa.Text(), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("based_on_map_version_id", sa.String(length=36), nullable=False),
        sa.Column("based_on_node_signature", sa.String(length=64), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["based_on_map_version_id"], ["research_map_versions.id"]
        ),
        sa.ForeignKeyConstraint(["node_id"], ["research_nodes.id"]),
        sa.ForeignKeyConstraint(["supersedes_review_id"], ["research_node_reviews.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("node_id", "revision_number"),
    )
    op.create_index(
        "ix_research_node_reviews_node_time",
        "research_node_reviews",
        ["node_id", "reviewed_at"],
    )

    op.create_table(
        "research_map_issues",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("map_version_id", sa.String(length=36), nullable=False),
        sa.Column("node_id", sa.String(length=36), nullable=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["map_version_id"], ["research_map_versions.id"]),
        sa.ForeignKeyConstraint(["node_id"], ["research_nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_research_map_issues_version_id",
        "research_map_issues",
        ["map_version_id"],
    )

    op.create_table(
        "research_map_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("map_version_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("stage", sa.String(length=64), nullable=False),
        sa.Column("progress", sa.Float(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("lease_token", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"]),
        sa.ForeignKeyConstraint(["map_version_id"], ["research_map_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_research_map_jobs_document_status",
        "research_map_jobs",
        ["document_id", "status"],
    )
    op.create_index(
        "uq_research_map_active_job",
        "research_map_jobs",
        ["document_id"],
        unique=True,
        sqlite_where=sa.text("status IN ('queued', 'running')"),
    )


def downgrade() -> None:
    op.drop_index("uq_research_map_active_job", table_name="research_map_jobs")
    op.drop_index(
        "ix_research_map_jobs_document_status", table_name="research_map_jobs"
    )
    op.drop_table("research_map_jobs")
    op.drop_index("ix_research_map_issues_version_id", table_name="research_map_issues")
    op.drop_table("research_map_issues")
    op.drop_index(
        "ix_research_node_reviews_node_time", table_name="research_node_reviews"
    )
    op.drop_table("research_node_reviews")
    op.drop_index("ix_research_evidence_block_id", table_name="research_evidence")
    op.drop_index("ix_research_evidence_node_id", table_name="research_evidence")
    op.drop_table("research_evidence")
    op.drop_index("ix_research_nodes_signature", table_name="research_nodes")
    op.drop_index("ix_research_nodes_map_version_order", table_name="research_nodes")
    op.drop_table("research_nodes")
    op.drop_index("uq_research_map_active_document", table_name="research_map_versions")
    op.drop_index(
        "ix_research_map_versions_document_id", table_name="research_map_versions"
    )
    op.drop_table("research_map_versions")
