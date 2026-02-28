"""add compatibility storage tables

Revision ID: 20260301_02
Revises: 20260301_01
Create Date: 2026-03-01
"""

from alembic import op
import sqlalchemy as sa


revision = "20260301_02"
down_revision = "20260301_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cv_files",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_cv_files_user_id", "cv_files", ["user_id"])

    op.create_table(
        "trend_snapshots",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("ran_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("keyword", sa.String(length=255), nullable=False),
        sa.Column("job_count", sa.Integer(), nullable=False),
        sa.Column("skill_counts", sa.JSON(), nullable=False),
        sa.Column("role_counts", sa.JSON(), nullable=False),
    )
    op.create_index("ix_trend_snapshots_ran_at", "trend_snapshots", ["ran_at"])

    op.create_table(
        "query_state",
        sa.Column("key", sa.String(length=64), primary_key=True),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("query_state")
    op.drop_index("ix_trend_snapshots_ran_at", table_name="trend_snapshots")
    op.drop_table("trend_snapshots")
    op.drop_index("ix_cv_files_user_id", table_name="cv_files")
    op.drop_table("cv_files")
