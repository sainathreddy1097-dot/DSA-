"""compliance playbooks

Revision ID: 54c7bd3a3c12
Revises: 28f3a2a8c291
"""

from alembic import op
import sqlalchemy as sa

revision = "54c7bd3a3c12"
down_revision = "28f3a2a8c291"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("playbooks", sa.Column("id", sa.String(24), primary_key=True), sa.Column("name", sa.String(160), nullable=False), sa.Column("version", sa.String(30), nullable=False), sa.Column("contract_type", sa.String(80), nullable=False), sa.Column("jurisdiction", sa.String(120), nullable=False), sa.Column("status", sa.String(20), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False), sa.UniqueConstraint("name", "version"))
    op.create_index(op.f("ix_playbooks_status"), "playbooks", ["status"])
    op.create_table("playbook_rules", sa.Column("id", sa.String(32), primary_key=True), sa.Column("playbook_id", sa.String(24), sa.ForeignKey("playbooks.id"), nullable=False), sa.Column("clause_category", sa.String(160), nullable=False), sa.Column("required_phrases_json", sa.Text(), nullable=False), sa.Column("prohibited_phrases_json", sa.Text(), nullable=False), sa.Column("risk", sa.String(10), nullable=False), sa.Column("remediation", sa.Text(), nullable=False))
    op.create_index(op.f("ix_playbook_rules_playbook_id"), "playbook_rules", ["playbook_id"])
    op.create_table("findings", sa.Column("id", sa.String(32), primary_key=True), sa.Column("contract_id", sa.String(16), sa.ForeignKey("contracts.id"), nullable=False), sa.Column("version_id", sa.String(24), sa.ForeignKey("contract_versions.id"), nullable=False), sa.Column("clause_id", sa.String(32), sa.ForeignKey("clauses.id"), nullable=True), sa.Column("rule_id", sa.String(32), sa.ForeignKey("playbook_rules.id"), nullable=False), sa.Column("status", sa.String(20), nullable=False), sa.Column("risk", sa.String(10), nullable=False), sa.Column("evidence", sa.Text(), nullable=False), sa.Column("remediation", sa.Text(), nullable=False), sa.Column("override_notes", sa.Text(), nullable=True), sa.Column("overridden_at", sa.DateTime(), nullable=True), sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False), sa.UniqueConstraint("version_id", "rule_id"))
    for column in ("contract_id", "version_id", "rule_id", "status", "risk"):
        op.create_index(f"ix_findings_{column}", "findings", [column])


def downgrade() -> None:
    for column in ("risk", "status", "rule_id", "version_id", "contract_id"):
        op.drop_index(f"ix_findings_{column}", table_name="findings")
    op.drop_table("findings")
    op.drop_index(op.f("ix_playbook_rules_playbook_id"), table_name="playbook_rules")
    op.drop_table("playbook_rules")
    op.drop_index(op.f("ix_playbooks_status"), table_name="playbooks")
    op.drop_table("playbooks")