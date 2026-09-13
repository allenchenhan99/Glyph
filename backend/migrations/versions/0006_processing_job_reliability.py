"""Durable processing jobs: progress counters, cancellation, provider metadata."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_processing_job_reliability"
down_revision: str | None = "0005_contract_job_map_selection"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("processing_jobs") as batch:
        batch.add_column(sa.Column("completed_blocks", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("total_blocks", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column(
                "cancel_requested",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
        batch.add_column(sa.Column("provider", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("model", sa.String(length=200), nullable=True))
        batch.add_column(
            sa.Column("source_content_hash", sa.String(length=64), nullable=True)
        )
    # Work left queued or running by a previous process cannot be resumed safely:
    # its session credentials are gone. Mark it interrupted; the user can retry.
    op.execute(
        "UPDATE processing_jobs SET status = 'interrupted', stage = 'interrupted', "
        "error_message = 'Processing was interrupted by a restart. Retry to continue; "
        "validated translation batches are reused from the local cache.' "
        "WHERE status IN ('queued', 'running')"
    )
    op.execute(
        "UPDATE documents SET status = CASE "
        "WHEN processed_content_hash IS NULL THEN 'discovered' "
        "WHEN processed_content_hash = content_hash THEN 'completed' "
        "ELSE 'stale' END "
        "WHERE status = 'processing'"
    )
    op.create_index(
        "ix_processing_jobs_active_document",
        "processing_jobs",
        ["document_id"],
        unique=True,
        sqlite_where=sa.text("status IN ('queued', 'running')"),
    )


def downgrade() -> None:
    op.drop_index("ix_processing_jobs_active_document", table_name="processing_jobs")
    with op.batch_alter_table("processing_jobs") as batch:
        batch.drop_column("source_content_hash")
        batch.drop_column("model")
        batch.drop_column("provider")
        batch.drop_column("cancel_requested")
        batch.drop_column("total_blocks")
        batch.drop_column("completed_blocks")
