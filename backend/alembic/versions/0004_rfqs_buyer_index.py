"""index rfqs.buyer_id for buyers' RFQ lists

Revision ID: 0004_rfqs_buyer_index
Revises: 0003_fix_check_constraint_names
Create Date: 2026-10-23
"""
from alembic import op

revision = "0004_rfqs_buyer_index"
down_revision = "0003_fix_check_constraint_names"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_rfqs_buyer_id", "rfqs", ["buyer_id"])


def downgrade() -> None:
    op.drop_index("ix_rfqs_buyer_id", table_name="rfqs")
