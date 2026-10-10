"""Add LangGraph orchestration tables: consent, suppression, tool audits, follow ups

Revision ID: 002
Revises: 001
Create Date: 2026-10-10

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None

def upgrade():
    # 1. contact_consents
    op.create_table(
        'contact_consents',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('contact_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('contacts.id', ondelete='CASCADE'), nullable=True),
        sa.Column('phone_number', sa.String(30), nullable=False),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('consent_status', sa.String(50), nullable=False, server_default='consented'),
        sa.Column('channel', sa.String(50), nullable=False, server_default='voice'),
        sa.Column('proof_reference', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    )
    op.create_index(op.f('ix_contact_consents_id'), 'contact_consents', ['id'], unique=False)
    op.create_index(op.f('ix_contact_consents_contact_id'), 'contact_consents', ['contact_id'], unique=False)
    op.create_index(op.f('ix_contact_consents_phone_number'), 'contact_consents', ['phone_number'], unique=False)
    op.create_index(op.f('ix_contact_consents_organization_id'), 'contact_consents', ['organization_id'], unique=False)
    op.create_index(op.f('ix_contact_consents_consent_status'), 'contact_consents', ['consent_status'], unique=False)

    # 2. suppression_records
    op.create_table(
        'suppression_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('phone_number', sa.String(30), nullable=False),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('reason', sa.String(100), nullable=False, server_default='opt_out'),
        sa.Column('source_call_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('calls.id', ondelete='SET NULL'), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index(op.f('ix_suppression_records_id'), 'suppression_records', ['id'], unique=False)
    op.create_index(op.f('ix_suppression_records_phone_number'), 'suppression_records', ['phone_number'], unique=False)
    op.create_index(op.f('ix_suppression_records_organization_id'), 'suppression_records', ['organization_id'], unique=False)
    op.create_index(op.f('ix_suppression_records_reason'), 'suppression_records', ['reason'], unique=False)

    # 3. tool_execution_audit_logs
    op.create_table(
        'tool_execution_audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('call_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('calls.id', ondelete='CASCADE'), nullable=True),
        sa.Column('campaign_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('campaigns.id', ondelete='SET NULL'), nullable=True),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('tool_name', sa.String(100), nullable=False),
        sa.Column('status', sa.String(30), nullable=False),
        sa.Column('execution_duration_ms', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('arguments', sa.JSON(), nullable=True),
        sa.Column('result_summary', sa.JSON(), nullable=True),
        sa.Column('correlation_id', sa.String(100), nullable=True),
        sa.Column('error_message', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index(op.f('ix_tool_execution_audit_logs_id'), 'tool_execution_audit_logs', ['id'], unique=False)
    op.create_index(op.f('ix_tool_execution_audit_logs_call_id'), 'tool_execution_audit_logs', ['call_id'], unique=False)
    op.create_index(op.f('ix_tool_execution_audit_logs_organization_id'), 'tool_execution_audit_logs', ['organization_id'], unique=False)
    op.create_index(op.f('ix_tool_execution_audit_logs_tool_name'), 'tool_execution_audit_logs', ['tool_name'], unique=False)
    op.create_index(op.f('ix_tool_execution_audit_logs_status'), 'tool_execution_audit_logs', ['status'], unique=False)
    op.create_index(op.f('ix_tool_execution_audit_logs_created_at'), 'tool_execution_audit_logs', ['created_at'], unique=False)

    # 4. call_follow_ups
    op.create_table(
        'call_follow_ups',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('call_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('calls.id', ondelete='CASCADE'), nullable=False),
        sa.Column('contact_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('contacts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('campaign_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('campaigns.id', ondelete='SET NULL'), nullable=True),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('scheduled_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('channel', sa.String(50), nullable=False, server_default='voice'),
        sa.Column('status', sa.String(30), nullable=False, server_default='scheduled'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    )
    op.create_index(op.f('ix_call_follow_ups_id'), 'call_follow_ups', ['id'], unique=False)
    op.create_index(op.f('ix_call_follow_ups_call_id'), 'call_follow_ups', ['call_id'], unique=False)
    op.create_index(op.f('ix_call_follow_ups_contact_id'), 'call_follow_ups', ['contact_id'], unique=False)
    op.create_index(op.f('ix_call_follow_ups_scheduled_time'), 'call_follow_ups', ['scheduled_time'], unique=False)
    op.create_index(op.f('ix_call_follow_ups_status'), 'call_follow_ups', ['status'], unique=False)

def downgrade():
    op.drop_table('call_follow_ups')
    op.drop_table('tool_execution_audit_logs')
    op.drop_table('suppression_records')
    op.drop_table('contact_consents')
