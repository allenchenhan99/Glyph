"""Evidence-linked summary versions, claims, quotes and generation jobs."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_document_summaries"
down_revision: str | None = "0006_processing_job_reliability"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "summary_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "document_id",
            sa.String(length=36),
            sa.ForeignKey("documents.id"),
            nullable=False,
        ),
        sa.Column(
            "previous_version_id",
            sa.String(length=36),
            sa.ForeignKey("summary_versions.id"),
            nullable=True,
        ),
        sa.Column("source_content_hash", sa.String(length=64), nullable=False),
        sa.Column("reader_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model_name", sa.String(length=200), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_summary_versions_document_id", "summary_versions", ["document_id"]
    )
    op.create_index(
        "uq_summary_active_version",
        "summary_versions",
        ["document_id"],
        unique=True,
        sqlite_where=sa.text("is_active = 1"),
    )
    op.create_table(
        "summary_claims",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "version_id",
            sa.String(length=36),
            sa.ForeignKey("summary_versions.id"),
            nullable=False,
        ),
        sa.Column("section_path", sa.String(length=2048), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
    )
    op.create_index("ix_summary_claims_version_id", "summary_claims", ["version_id"])
    op.create_table(
        "summary_evidence",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "claim_id",
            sa.String(length=36),
            sa.ForeignKey("summary_claims.id"),
            nullable=False,
        ),
        sa.Column(
            "block_id", sa.String(length=36), sa.ForeignKey("blocks.id"), nullable=False
        ),
        sa.Column("quote_text", sa.Text(), nullable=False),
        sa.Column("quote_start", sa.Integer(), nullable=False),
        sa.Column("quote_end", sa.Integer(), nullable=False),
        sa.Column("source_quote_hash", sa.String(length=64), nullable=False),
        sa.UniqueConstraint("claim_id", "block_id", "quote_start", "quote_end"),
    )
    op.create_index("ix_summary_evidence_block_id", "summary_evidence", ["block_id"])
    op.create_table(
        "summary_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "document_id",
            sa.String(length=36),
            sa.ForeignKey("documents.id"),
            nullable=False,
        ),
        sa.Column(
            "version_id",
            sa.String(length=36),
            sa.ForeignKey("summary_versions.id"),
            nullable=True,
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("stage", sa.String(length=64), nullable=False),
        sa.Column("progress", sa.Float(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_summary_jobs_document_status", "summary_jobs", ["document_id", "status"]
    )
    op.create_index(
        "uq_summary_active_job",
        "summary_jobs",
        ["document_id"],
        unique=True,
        sqlite_where=sa.text("status IN ('queued', 'running')"),
    )


def downgrade() -> None:
    op.drop_table("summary_jobs")
    op.drop_table("summary_evidence")
    op.drop_table("summary_claims")
    op.drop_table("summary_versions")
