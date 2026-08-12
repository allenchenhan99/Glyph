"""Track the source hash used by the last successful reader output."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_reliability_fields"
down_revision: str | None = "0001_legacy_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("processed_content_hash", sa.String(length=64), nullable=True),
    )
    op.execute(
        "UPDATE documents SET processed_content_hash = content_hash "
        "WHERE status = 'completed'"
    )


def downgrade() -> None:
    op.drop_column("documents", "processed_content_hash")
