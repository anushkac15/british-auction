"""fix doubled check constraint names

0001 passed full names (e.g. "ck_bids_transit_positive") while the metadata naming
convention also prefixes "ck_<table>_", so the database got "ck_bids_ck_bids_transit_positive".
Rename them to the names the models and docs/schema.md use.

Revision ID: 0003_fix_check_constraint_names
Revises: 0002_user_passwords
Create Date: 2026-10-23
"""
from alembic import op

revision = "0003_fix_check_constraint_names"
down_revision = "0002_user_passwords"
branch_labels = None
depends_on = None

CHECKS = {
    "users": ["role"],
    "rfqs": [
        "auction_status",
        "original_close_after_start",
        "forced_after_original_close",
        "close_after_start",
        "close_not_after_forced",
        "close_never_moves_back",
    ],
    "auction_configs": ["trigger_type", "trigger_window_range", "extension_range"],
    "bids": ["freight_non_negative", "origin_non_negative", "destination_non_negative", "transit_positive"],
    "activity_logs": ["event_type"],
}


def _rename(doubled_to_single: bool) -> None:
    for table, names in CHECKS.items():
        for name in names:
            single = f"ck_{table}_{name}"
            doubled = f"ck_{table}_{single}"
            old, new = (doubled, single) if doubled_to_single else (single, doubled)
            op.execute(f'ALTER TABLE {table} RENAME CONSTRAINT "{old}" TO "{new}"')


def upgrade() -> None:
    _rename(doubled_to_single=True)


def downgrade() -> None:
    _rename(doubled_to_single=False)
