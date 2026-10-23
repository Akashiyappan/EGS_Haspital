"""add patient prescription requests

Revision ID: a91cd20e11f2
Revises: 124bec2b3c5c
Create Date: 2026-10-18 20:30:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "a91cd20e11f2"
down_revision: str | None = "124bec2b3c5c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "prescription_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("doctor_id", sa.Integer(), nullable=False),
        sa.Column("appointment_id", sa.Integer(), nullable=True),
        sa.Column("reason", sa.String(length=1000), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True).with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True).with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["doctor_id"], ["doctors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_prescription_requests_patient_id", "prescription_requests", ["patient_id"])
    op.create_index("ix_prescription_requests_doctor_id", "prescription_requests", ["doctor_id"])


def downgrade() -> None:
    op.drop_index("ix_prescription_requests_doctor_id", table_name="prescription_requests")
    op.drop_index("ix_prescription_requests_patient_id", table_name="prescription_requests")
    op.drop_table("prescription_requests")
