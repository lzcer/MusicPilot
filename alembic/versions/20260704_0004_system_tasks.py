"""Add system task queue tables.

Revision ID: 20260704_0004
Revises: 20260624_0003
Create Date: 2026-07-04
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260704_0004"
down_revision: str | None = "20260624_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "system_tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("chain_id", sa.String(length=64), nullable=False),
        sa.Column("parent_task_id", sa.Integer(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("resource_keys", sa.JSON(), nullable=False),
        sa.Column("inheritable_key", sa.String(length=256), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index(op.f("ix_system_tasks_chain_id"), "system_tasks", ["chain_id"])
    op.create_index(op.f("ix_system_tasks_status"), "system_tasks", ["status"])
    op.create_index(op.f("ix_system_tasks_task_type"), "system_tasks", ["task_type"])
    op.create_table(
        "system_task_resource_leases",
        sa.Column("resource_key", sa.String(length=256), nullable=False),
        sa.Column("holder_kind", sa.String(length=32), nullable=False),
        sa.Column("holder_id", sa.String(length=64), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=True),
        sa.Column("chain_id", sa.String(length=64), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("resource_key"),
    )
    op.create_index(
        op.f("ix_system_task_resource_leases_chain_id"),
        "system_task_resource_leases",
        ["chain_id"],
    )
    op.create_index(
        op.f("ix_system_task_resource_leases_holder_id"),
        "system_task_resource_leases",
        ["holder_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_system_task_resource_leases_holder_id"),
        table_name="system_task_resource_leases",
    )
    op.drop_index(
        op.f("ix_system_task_resource_leases_chain_id"),
        table_name="system_task_resource_leases",
    )
    op.drop_table("system_task_resource_leases")
    op.drop_index(op.f("ix_system_tasks_task_type"), table_name="system_tasks")
    op.drop_index(op.f("ix_system_tasks_status"), table_name="system_tasks")
    op.drop_index(op.f("ix_system_tasks_chain_id"), table_name="system_tasks")
    op.drop_table("system_tasks")
