"""Initial database schema

Revision ID: 001
Revises: 
Create Date: 2026-10-09

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Create users table
    op.create_table('users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('email', sa.String(255), nullable=False, unique=True),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('full_name', sa.String(255)),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('is_superuser', sa.Boolean(), nullable=False, default=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()'))
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)

    # Create contacts table
    op.create_table('contacts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('import_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('phone_number', sa.String(20), nullable=False),
        sa.Column('phone_number_normalized', sa.String(20), nullable=False, unique=True),
        sa.Column('name', sa.String(255)),
        sa.Column('email', sa.String(255)),
        sa.Column('language', sa.String(10), default='en'),
        sa.Column('custom_fields', sa.JSON(), nullable=True),
        sa.Column('validation_status', sa.String(20), default='valid'),
        sa.Column('validation_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()'))
    )
    op.create_index(op.f('ix_contacts_id'), 'contacts', ['id'], unique=False)
    op.create_index(op.f('ix_contacts_import_id'), 'contacts', ['import_id'], unique=False)
    op.create_index(op.f('ix_contacts_phone_number'), 'contacts', ['phone_number'], unique=False)
    op.create_index(op.f('ix_contacts_phone_number_normalized'), 'contacts', ['phone_number_normalized'], unique=True)

    # Create contact_imports table
    op.create_table('contact_imports',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('file_name', sa.String(255), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('row_count', sa.Integer(), nullable=False),
        sa.Column('success_count', sa.Integer(), default=0),
        sa.Column('failure_count', sa.Integer(), default=0),
        sa.Column('duplicate_count', sa.Integer(), default=0),
        sa.Column('status', sa.String(20), default='processing'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('column_mapping', sa.String(1000), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()'))
    )
    op.create_index(op.f('ix_contact_imports_id'), 'contact_imports', ['id'], unique=False)

    # Create campaigns table
    op.create_table('campaigns',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.Enum('draft', 'queued', 'in_progress', 'paused', 'completed', 'cancelled', 'failed', name='campaignstatus'), nullable=False, default='draft'),
        sa.Column('agent_prompt', sa.Text(), nullable=True),
        sa.Column('max_call_duration', sa.Integer(), default=300),
        sa.Column('max_retries', sa.Integer(), default=3),
        sa.Column('concurrency_limit', sa.Integer(), default=5),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('end_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('provider_config', sa.JSON(), nullable=True),
        sa.Column('total_contacts', sa.Integer(), default=0),
        sa.Column('queued_calls', sa.Integer(), default=0),
        sa.Column('in_progress_calls', sa.Integer(), default=0),
        sa.Column('completed_calls', sa.Integer(), default=0),
        sa.Column('failed_calls', sa.Integer(), default=0),
        sa.Column('no_answer_calls', sa.Integer(), default=0),
        sa.Column('answered_calls', sa.Integer(), default=0),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()'))
    )
    op.create_index(op.f('ix_campaigns_id'), 'campaigns', ['id'], unique=False)
    op.create_index(op.f('ix_campaigns_status'), 'campaigns', ['status'], unique=False)

    # Create campaign_contacts table
    op.create_table('campaign_contacts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('campaign_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('contact_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('status', sa.Enum('pending', 'queued', 'in_progress', 'completed', 'failed', 'skipped', name='campaigncontactstatus'), nullable=False, default='pending'),
        sa.Column('retry_count', sa.Integer(), default=0),
        sa.Column('last_error', sa.String(500), nullable=True),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()')),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ondelete='CASCADE')
    )
    op.create_index(op.f('ix_campaign_contacts_campaign_id'), 'campaign_contacts', ['campaign_id'], unique=False)
    op.create_index(op.f('ix_campaign_contacts_contact_id'), 'campaign_contacts', ['contact_id'], unique=False)
    op.create_index(op.f('ix_campaign_contacts_id'), 'campaign_contacts', ['id'], unique=False)
    op.create_index(op.f('ix_campaign_contacts_status'), 'campaign_contacts', ['status'], unique=False)

    # Create calls table
    op.create_table('calls',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('campaign_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('campaign_contact_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('contact_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('provider_call_id', sa.String(255), nullable=True),
        sa.Column('provider', sa.String(50), nullable=True),
        sa.Column('phone_number', sa.String(20), nullable=False),
        sa.Column('direction', sa.Enum('outbound', 'inbound', name='calldirection'), nullable=False, default='outbound'),
        sa.Column('status', sa.Enum('queued', 'ringing', 'in_progress', 'completed', 'failed', 'no_answer', 'busy', 'cancelled', 'rejected', name='callstatus'), nullable=False, default='queued'),
        sa.Column('queued_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_seconds', sa.Integer(), nullable=True),
        sa.Column('failure_reason', sa.Text(), nullable=True),
        sa.Column('hangup_cause', sa.String(100), nullable=True),
        sa.Column('ai_interactions', sa.Integer(), default=0),
        sa.Column('ai_confidence_score', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()')),
        sa.ForeignKeyConstraint(['campaign_contact_id'], ['campaign_contacts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ondelete='SET NULL')
    )
    op.create_index(op.f('ix_calls_campaign_contact_id'), 'calls', ['campaign_contact_id'], unique=False)
    op.create_index(op.f('ix_calls_campaign_id'), 'calls', ['campaign_id'], unique=False)
    op.create_index(op.f('ix_calls_contact_id'), 'calls', ['contact_id'], unique=False)
    op.create_index(op.f('ix_calls_id'), 'calls', ['id'], unique=False)
    op.create_index(op.f('ix_calls_provider_call_id'), 'calls', ['provider_call_id'], unique=False)
    op.create_index(op.f('ix_calls_status'), 'calls', ['status'], unique=False)

    # Create call_events table
    op.create_table('call_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('call_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('event_data', sa.JSON(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['call_id'], ['calls.id'], ondelete='CASCADE')
    )
    op.create_index(op.f('ix_call_events_call_id'), 'call_events', ['call_id'], unique=False)
    op.create_index(op.f('ix_call_events_event_type'), 'call_events', ['event_type'], unique=False)
    op.create_index(op.f('ix_call_events_id'), 'call_events', ['id'], unique=False)
    op.create_index(op.f('ix_call_events_timestamp'), 'call_events', ['timestamp'], unique=False)

    # Create transcripts table
    op.create_table('transcripts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('call_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('full_transcript', sa.Text(), nullable=True),
        sa.Column('word_count', sa.Integer(), default=0),
        sa.Column('language_detected', sa.String(10), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()')),
        sa.ForeignKeyConstraint(['call_id'], ['calls.id'], ondelete='CASCADE')
    )
    op.create_index(op.f('ix_transcripts_call_id'), 'transcripts', ['call_id'], unique=True)
    op.create_index(op.f('ix_transcripts_id'), 'transcripts', ['id'], unique=False)

    # Create extracted_call_results table
    op.create_table('extracted_call_results',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('call_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('customer_name', sa.String(255), nullable=True),
        sa.Column('customer_intent', sa.String(255), nullable=True),
        sa.Column('customer_rating', sa.Integer(), nullable=True),
        sa.Column('complaint', sa.Text(), nullable=True),
        sa.Column('follow_up_required', sa.String(20), nullable=True),
        sa.Column('follow_up_notes', sa.Text(), nullable=True),
        sa.Column('call_outcome', sa.String(100), nullable=True),
        sa.Column('raw_extracted_data', sa.JSON(), nullable=True),
        sa.Column('validation_status', sa.String(20), default='pending'),
        sa.Column('validation_errors', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()')),
        sa.ForeignKeyConstraint(['call_id'], ['calls.id'], ondelete='CASCADE')
    )
    op.create_index(op.f('ix_extracted_call_results_call_id'), 'extracted_call_results', ['call_id'], unique=True)
    op.create_index(op.f('ix_extracted_call_results_id'), 'extracted_call_results', ['id'], unique=False)

    # Create provider_configurations table
    op.create_table('provider_configurations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('provider_type', sa.Enum('telephony', 'stt', 'llm', 'tts', name='providertype'), nullable=False),
        sa.Column('provider_name', sa.String(50), nullable=False),
        sa.Column('is_active', sa.String(20), default='true'),
        sa.Column('configuration', sa.JSON(), nullable=True),
        sa.Column('display_name', sa.String(255), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()'))
    )
    op.create_index(op.f('ix_provider_configurations_id'), 'provider_configurations', ['id'], unique=False)
    op.create_index(op.f('ix_provider_configurations_provider_name'), 'provider_configurations', ['provider_name'], unique=False)
    op.create_index(op.f('ix_provider_configurations_provider_type'), 'provider_configurations', ['provider_type'], unique=False)

    # Create usage_records table
    op.create_table('usage_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('call_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('campaign_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('metric_type', sa.String(50), nullable=False),
        sa.Column('provider', sa.String(50), nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('unit', sa.String(20), nullable=False),
        sa.Column('estimated_cost', sa.Numeric(10, 4), nullable=True),
        sa.Column('currency', sa.String(3), default='USD'),
        sa.Column('recorded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['call_id'], ['calls.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='SET NULL')
    )
    op.create_index(op.f('ix_usage_records_campaign_id'), 'usage_records', ['campaign_id'], unique=False)
    op.create_index(op.f('ix_usage_records_call_id'), 'usage_records', ['call_id'], unique=False)
    op.create_index(op.f('ix_usage_records_id'), 'usage_records', ['id'], unique=False)
    op.create_index(op.f('ix_usage_records_metric_type'), 'usage_records', ['metric_type'], unique=False)
    op.create_index(op.f('ix_usage_records_recorded_at'), 'usage_records', ['recorded_at'], unique=False)

    # Create audit_logs table
    op.create_table('audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('entity_type', sa.String(50), nullable=False),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('changes', sa.JSON(), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.String(500), nullable=True),
        sa.Column('success', sa.String(20), default='true'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL')
    )
    op.create_index(op.f('ix_audit_logs_action'), 'audit_logs', ['action'], unique=False)
    op.create_index(op.f('ix_audit_logs_created_at'), 'audit_logs', ['created_at'], unique=False)
    op.create_index(op.f('ix_audit_logs_entity_id'), 'audit_logs', ['entity_id'], unique=False)
    op.create_index(op.f('ix_audit_logs_entity_type'), 'audit_logs', ['entity_type'], unique=False)
    op.create_index(op.f('ix_audit_logs_id'), 'audit_logs', ['id'], unique=False)
    op.create_index(op.f('ix_audit_logs_user_id'), 'audit_logs', ['user_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_audit_logs_user_id'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_id'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_entity_type'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_entity_id'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_created_at'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_action'), table_name='audit_logs')
    op.drop_table('audit_logs')

    op.drop_index(op.f('ix_usage_records_recorded_at'), table_name='usage_records')
    op.drop_index(op.f('ix_usage_records_metric_type'), table_name='usage_records')
    op.drop_index(op.f('ix_usage_records_id'), table_name='usage_records')
    op.drop_index(op.f('ix_usage_records_call_id'), table_name='usage_records')
    op.drop_index(op.f('ix_usage_records_campaign_id'), table_name='usage_records')
    op.drop_table('usage_records')

    op.drop_index(op.f('ix_provider_configurations_provider_type'), table_name='provider_configurations')
    op.drop_index(op.f('ix_provider_configurations_provider_name'), table_name='provider_configurations')
    op.drop_index(op.f('ix_provider_configurations_id'), table_name='provider_configurations')
    op.drop_table('provider_configurations')

    op.drop_index(op.f('ix_extracted_call_results_id'), table_name='extracted_call_results')
    op.drop_index(op.f('ix_extracted_call_results_call_id'), table_name='extracted_call_results')
    op.drop_table('extracted_call_results')

    op.drop_index(op.f('ix_transcripts_id'), table_name='transcripts')
    op.drop_index(op.f('ix_transcripts_call_id'), table_name='transcripts')
    op.drop_table('transcripts')

    op.drop_index(op.f('ix_call_events_timestamp'), table_name='call_events')
    op.drop_index(op.f('ix_call_events_id'), table_name='call_events')
    op.drop_index(op.f('ix_call_events_event_type'), table_name='call_events')
    op.drop_index(op.f('ix_call_events_call_id'), table_name='call_events')
    op.drop_table('call_events')

    op.drop_index(op.f('ix_calls_status'), table_name='calls')
    op.drop_index(op.f('ix_calls_provider_call_id'), table_name='calls')
    op.drop_index(op.f('ix_calls_id'), table_name='calls')
    op.drop_index(op.f('ix_calls_contact_id'), table_name='calls')
    op.drop_index(op.f('ix_calls_campaign_id'), table_name='calls')
    op.drop_index(op.f('ix_calls_campaign_contact_id'), table_name='calls')
    op.drop_table('calls')

    op.drop_index(op.f('ix_campaign_contacts_status'), table_name='campaign_contacts')
    op.drop_index(op.f('ix_campaign_contacts_id'), table_name='campaign_contacts')
    op.drop_index(op.f('ix_campaign_contacts_contact_id'), table_name='campaign_contacts')
    op.drop_index(op.f('ix_campaign_contacts_campaign_id'), table_name='campaign_contacts')
    op.drop_table('campaign_contacts')

    op.drop_index(op.f('ix_campaigns_status'), table_name='campaigns')
    op.drop_index(op.f('ix_campaigns_id'), table_name='campaigns')
    op.drop_table('campaigns')

    op.drop_index(op.f('ix_contact_imports_id'), table_name='contact_imports')
    op.drop_table('contact_imports')

    op.drop_index(op.f('ix_contacts_phone_number_normalized'), table_name='contacts')
    op.drop_index(op.f('ix_contacts_phone_number'), table_name='contacts')
    op.drop_index(op.f('ix_contacts_import_id'), table_name='contacts')
    op.drop_index(op.f('ix_contacts_id'), table_name='contacts')
    op.drop_table('contacts')

    op.drop_index(op.f('ix_users_id'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
