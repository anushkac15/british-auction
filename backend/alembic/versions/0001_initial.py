"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-22
"""
import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

ROLES = ("BUYER", "SUPPLIER")
STATUSES = ("UPCOMING", "ACTIVE", "CLOSED", "FORCE_CLOSED")
TRIGGERS = ("ANY_BID", "ANY_RANK_CHANGE", "L1_CHANGE")
EVENTS = (
    "RFQ_CREATED",
    "AUCTION_STARTED",
    "BID_SUBMITTED",
    "TIME_EXTENDED",
    "EXTENSION_CAPPED",
    "CLOSED",
    "FORCE_CLOSED",
)
ONCE_PER_RFQ_WHERE = (
    "event_type IN ('RFQ_CREATED', 'AUCTION_STARTED', 'EXTENSION_CAPPED', 'CLOSED', 'FORCE_CLOSED')"
)
MONEY = sa.Numeric(12, 2)
TS = sa.DateTime(timezone=True)


def _enum(values: tuple[str, ...], name: str, length: int) -> sa.Enum:
    return sa.Enum(*values, native_enum=False, length=length, name=name, create_constraint=True)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("email", sa.String(200), nullable=False),
        sa.Column("role", _enum(ROLES, "ck_users_role", 20), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "rfqs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("reference_id", sa.String(50), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("buyer_id", sa.Integer(), nullable=False),
        sa.Column("pickup_date", sa.Date(), nullable=False),
        sa.Column("bid_start_at", TS, nullable=False),
        sa.Column("original_bid_close_at", TS, nullable=False),
        sa.Column("bid_close_at", TS, nullable=False),
        sa.Column("forced_close_at", TS, nullable=False),
        sa.Column("status", _enum(STATUSES, "ck_rfqs_auction_status", 20), nullable=False),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_rfqs"),
        sa.UniqueConstraint("reference_id", name="uq_rfqs_reference_id"),
        sa.ForeignKeyConstraint(["buyer_id"], ["users.id"], name="fk_rfqs_buyer_id_users"),
        sa.CheckConstraint("original_bid_close_at > bid_start_at", name="ck_rfqs_original_close_after_start"),
        sa.CheckConstraint("forced_close_at > original_bid_close_at", name="ck_rfqs_forced_after_original_close"),
        sa.CheckConstraint("bid_close_at > bid_start_at", name="ck_rfqs_close_after_start"),
        sa.CheckConstraint("bid_close_at <= forced_close_at", name="ck_rfqs_close_not_after_forced"),
        sa.CheckConstraint("bid_close_at >= original_bid_close_at", name="ck_rfqs_close_never_moves_back"),
    )
    op.create_index("ix_rfqs_status", "rfqs", ["status"])

    op.create_table(
        "auction_configs",
        sa.Column("rfq_id", sa.Integer(), nullable=False),
        sa.Column("trigger_window_minutes", sa.Integer(), nullable=False),
        sa.Column("extension_minutes", sa.Integer(), nullable=False),
        sa.Column("trigger_type", _enum(TRIGGERS, "ck_auction_configs_trigger_type", 20), nullable=False),
        sa.PrimaryKeyConstraint("rfq_id", name="pk_auction_configs"),
        sa.ForeignKeyConstraint(
            ["rfq_id"], ["rfqs.id"], name="fk_auction_configs_rfq_id_rfqs", ondelete="CASCADE"
        ),
        sa.CheckConstraint("trigger_window_minutes BETWEEN 1 AND 60", name="ck_auction_configs_trigger_window_range"),
        sa.CheckConstraint("extension_minutes BETWEEN 1 AND 60", name="ck_auction_configs_extension_range"),
    )

    op.create_table(
        "bids",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("rfq_id", sa.Integer(), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("carrier_name", sa.String(120), nullable=False),
        sa.Column("freight_charges", MONEY, nullable=False),
        sa.Column("origin_charges", MONEY, nullable=False),
        sa.Column("destination_charges", MONEY, nullable=False),
        sa.Column(
            "total_price",
            MONEY,
            sa.Computed("freight_charges + origin_charges + destination_charges", persisted=True),
            nullable=False,
        ),
        sa.Column("transit_time_days", sa.Integer(), nullable=False),
        sa.Column("quote_validity_date", sa.Date(), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_bids"),
        sa.ForeignKeyConstraint(["rfq_id"], ["rfqs.id"], name="fk_bids_rfq_id_rfqs", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["supplier_id"], ["users.id"], name="fk_bids_supplier_id_users"),
        sa.CheckConstraint("freight_charges >= 0", name="ck_bids_freight_non_negative"),
        sa.CheckConstraint("origin_charges >= 0", name="ck_bids_origin_non_negative"),
        sa.CheckConstraint("destination_charges >= 0", name="ck_bids_destination_non_negative"),
        sa.CheckConstraint("transit_time_days > 0", name="ck_bids_transit_positive"),
    )
    op.create_index(
        "ix_bids_rfq_supplier_created",
        "bids",
        ["rfq_id", "supplier_id", sa.text("created_at DESC")],
    )

    op.create_table(
        "activity_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("rfq_id", sa.Integer(), nullable=False),
        sa.Column("event_type", _enum(EVENTS, "ck_activity_logs_event_type", 30), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=True),
        sa.Column("bid_id", sa.Integer(), nullable=True),
        sa.Column("old_close_at", TS, nullable=True),
        sa.Column("new_close_at", TS, nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_activity_logs"),
        sa.ForeignKeyConstraint(
            ["rfq_id"], ["rfqs.id"], name="fk_activity_logs_rfq_id_rfqs", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["supplier_id"], ["users.id"], name="fk_activity_logs_supplier_id_users"
        ),
        sa.ForeignKeyConstraint(
            ["bid_id"], ["bids.id"], name="fk_activity_logs_bid_id_bids", ondelete="CASCADE"
        ),
    )
    op.create_index("ix_activity_logs_rfq_created", "activity_logs", ["rfq_id", "created_at"])
    op.create_index(
        "uq_activity_logs_once_per_rfq",
        "activity_logs",
        ["rfq_id", "event_type"],
        unique=True,
        postgresql_where=sa.text(ONCE_PER_RFQ_WHERE),
    )


def downgrade() -> None:
    op.drop_table("activity_logs")
    op.drop_table("bids")
    op.drop_table("auction_configs")
    op.drop_table("rfqs")
    op.drop_table("users")
