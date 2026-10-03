"""local actor access control

Revision ID: 28f3a2a8c291
Revises: 7d246ea44c29
"""

from alembic import op
import sqlalchemy as sa


revision = "28f3a2a8c291"
down_revision = "7d246ea44c29"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("role", sa.String(length=30), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_role"), "users", ["role"], unique=False)
    op.add_column("audit_events", sa.Column("actor_id", sa.String(length=16), nullable=True))
    op.add_column("audit_events", sa.Column("actor_role", sa.String(length=30), nullable=True))
    op.create_index(op.f("ix_audit_events_actor_id"), "audit_events", ["actor_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_audit_events_actor_id"), table_name="audit_events")
    op.drop_column("audit_events", "actor_role")
    op.drop_column("audit_events", "actor_id")
    op.drop_index(op.f("ix_users_role"), table_name="users")
    op.drop_table("users")