"""Persist the Research Map selected for a contract job."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_contract_job_map_selection"
down_revision: str | None = "0004_implementation_contracts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("implementation_contract_jobs") as batch_op:
        batch_op.add_column(
            sa.Column(
                "requested_research_map_version_id",
                sa.String(length=36),
                nullable=True,
            )
        )
        batch_op.create_foreign_key(
            "fk_contract_jobs_requested_research_map",
            "research_map_versions",
            ["requested_research_map_version_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("implementation_contract_jobs") as batch_op:
        batch_op.drop_constraint(
            "fk_contract_jobs_requested_research_map", type_="foreignkey"
        )
        batch_op.drop_column("requested_research_map_version_id")
