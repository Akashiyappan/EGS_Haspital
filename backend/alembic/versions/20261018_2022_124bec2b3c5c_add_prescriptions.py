"""add_prescriptions

Revision ID: 124bec2b3c5c
Revises: eee5ae58e2fe
Create Date: 2026-10-18 20:22:59.670269

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = '124bec2b3c5c'
down_revision: str | None = 'eee5ae58e2fe'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'prescriptions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('appointment_id', sa.Integer(), nullable=True),
        sa.Column('doctor_id', sa.Integer(), nullable=False),
        sa.Column('patient_id', sa.Integer(), nullable=False),
        sa.Column('diagnosis', sa.String(length=500), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('advice', sa.Text(), nullable=True),
        sa.Column('follow_up_date', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True).with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True).with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False),
        sa.ForeignKeyConstraint(['appointment_id'], ['appointments.id'], name=op.f('fk_prescriptions_appointment_id_appointments'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['doctor_id'], ['doctors.id'], name=op.f('fk_prescriptions_doctor_id_doctors'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], name=op.f('fk_prescriptions_patient_id_patients'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_prescriptions'))
    )
    op.create_index('ix_prescriptions_appointment_id', 'prescriptions', ['appointment_id'], unique=False)
    op.create_index('ix_prescriptions_created_at', 'prescriptions', ['created_at'], unique=False)
    op.create_index('ix_prescriptions_doctor_id', 'prescriptions', ['doctor_id'], unique=False)
    op.create_index('ix_prescriptions_patient_id', 'prescriptions', ['patient_id'], unique=False)

    op.create_table(
        'prescription_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('prescription_id', sa.Integer(), nullable=False),
        sa.Column('medicine_name', sa.String(length=200), nullable=False),
        sa.Column('dosage', sa.String(length=100), nullable=False),
        sa.Column('frequency', sa.String(length=100), nullable=False),
        sa.Column('timing', sa.String(length=100), nullable=False),
        sa.Column('duration_days', sa.Integer(), nullable=False),
        sa.Column('instructions', sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(['prescription_id'], ['prescriptions.id'], name=op.f('fk_prescription_items_prescription_id_prescriptions'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_prescription_items'))
    )
    op.create_index('ix_prescription_items_prescription_id', 'prescription_items', ['prescription_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_prescription_items_prescription_id', table_name='prescription_items')
    op.drop_table('prescription_items')
    op.drop_index('ix_prescriptions_patient_id', table_name='prescriptions')
    op.drop_index('ix_prescriptions_doctor_id', table_name='prescriptions')
    op.drop_index('ix_prescriptions_created_at', table_name='prescriptions')
    op.drop_index('ix_prescriptions_appointment_id', table_name='prescriptions')
    op.drop_table('prescriptions')
