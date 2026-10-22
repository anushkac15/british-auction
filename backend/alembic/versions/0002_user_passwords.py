"""user passwords for login

Revision ID: 0002_user_passwords
Revises: 0001_initial
Create Date: 2026-10-22
"""
import sqlalchemy as sa
from alembic import op

revision = "0002_user_passwords"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable: users created before this migration can't log in until a password is set (the seed does this).
    op.add_column("users", sa.Column("password_hash", sa.String(255), nullable=True))
    op.create_index("uq_users_email_lower", "users", [sa.text("lower(email)")], unique=True)


def downgrade() -> None:
    op.drop_index("uq_users_email_lower", table_name="users")
    op.drop_column("users", "password_hash")
