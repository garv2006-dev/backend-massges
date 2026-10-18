"""Initial database schema for WhatsApp Automation and AI Messaging Platform

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
    # 1. Create users table
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

    # 2. Create company_profiles table
    op.create_table('company_profiles',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True, unique=True),
        sa.Column('name', sa.String(255), nullable=False, server_default=''),
        sa.Column('phone_number', sa.String(50), nullable=False, server_default=''),
        sa.Column('email', sa.String(255), nullable=True),
        sa.Column('industry', sa.String(255), server_default='Customer Service & Sales Automation', nullable=True),
        sa.Column('website', sa.String(255), nullable=True),
        sa.Column('default_agent_name', sa.String(100), server_default='Sarah', nullable=True),
        sa.Column('default_voice', sa.String(100), server_default='en-IN-NeerjaNeural', nullable=True),
        sa.Column('default_language', sa.String(100), server_default='English', nullable=True),
        sa.Column('simulated_connected', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('whatsapp_phone', sa.String(50), server_default='', nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE')
    )
    op.create_index(op.f('ix_company_profiles_id'), 'company_profiles', ['id'], unique=False)
    op.create_index(op.f('ix_company_profiles_user_id'), 'company_profiles', ['user_id'], unique=True)

    # 3. Create contact_imports table
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

    # 4. Create contacts table
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
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()')),
        sa.ForeignKeyConstraint(['import_id'], ['contact_imports.id'], ondelete='SET NULL')
    )
    op.create_index(op.f('ix_contacts_id'), 'contacts', ['id'], unique=False)
    op.create_index(op.f('ix_contacts_import_id'), 'contacts', ['import_id'], unique=False)
    op.create_index(op.f('ix_contacts_phone_number'), 'contacts', ['phone_number'], unique=False)
    op.create_index(op.f('ix_contacts_phone_number_normalized'), 'contacts', ['phone_number_normalized'], unique=True)

    # 5. Create campaigns table
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

    # 6. Create campaign_contacts table
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

    # 7. Create whatsapp_conversations table
    op.create_table('whatsapp_conversations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('contact_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('phone_number', sa.String(50), nullable=False),
        sa.Column('contact_name', sa.String(255), nullable=True),
        sa.Column('chat_jid', sa.String(100), nullable=True),
        sa.Column('last_message_text', sa.Text(), nullable=True),
        sa.Column('last_message_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('unread_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('is_pinned', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('is_archived', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ondelete='SET NULL')
    )
    op.create_index(op.f('ix_whatsapp_conversations_id'), 'whatsapp_conversations', ['id'], unique=False)
    op.create_index(op.f('ix_whatsapp_conversations_phone_number'), 'whatsapp_conversations', ['phone_number'], unique=False)
    op.create_index(op.f('ix_whatsapp_conversations_chat_jid'), 'whatsapp_conversations', ['chat_jid'], unique=False)

    # 8. Create whatsapp_messages table
    op.create_table('whatsapp_messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('campaign_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('sender', sa.String(50), server_default='agent', nullable=False),
        sa.Column('direction', sa.String(20), server_default='outbound', nullable=False),
        sa.Column('message_text', sa.Text(), nullable=False),
        sa.Column('status', sa.String(30), server_default='sent', nullable=True),
        sa.Column('openwa_message_id', sa.String(255), nullable=True),
        sa.Column('chat_jid', sa.String(100), nullable=True),
        sa.Column('ai_generated', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['whatsapp_conversations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='SET NULL')
    )
    op.create_index(op.f('ix_whatsapp_messages_id'), 'whatsapp_messages', ['id'], unique=False)
    op.create_index(op.f('ix_whatsapp_messages_conversation_id'), 'whatsapp_messages', ['conversation_id'], unique=False)
    op.create_index(op.f('ix_whatsapp_messages_campaign_id'), 'whatsapp_messages', ['campaign_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_whatsapp_messages_campaign_id'), table_name='whatsapp_messages')
    op.drop_index(op.f('ix_whatsapp_messages_conversation_id'), table_name='whatsapp_messages')
    op.drop_index(op.f('ix_whatsapp_messages_id'), table_name='whatsapp_messages')
    op.drop_table('whatsapp_messages')

    op.drop_index(op.f('ix_whatsapp_conversations_chat_jid'), table_name='whatsapp_conversations')
    op.drop_index(op.f('ix_whatsapp_conversations_phone_number'), table_name='whatsapp_conversations')
    op.drop_index(op.f('ix_whatsapp_conversations_id'), table_name='whatsapp_conversations')
    op.drop_table('whatsapp_conversations')

    op.drop_index(op.f('ix_campaign_contacts_status'), table_name='campaign_contacts')
    op.drop_index(op.f('ix_campaign_contacts_id'), table_name='campaign_contacts')
    op.drop_index(op.f('ix_campaign_contacts_contact_id'), table_name='campaign_contacts')
    op.drop_index(op.f('ix_campaign_contacts_campaign_id'), table_name='campaign_contacts')
    op.drop_table('campaign_contacts')

    op.drop_index(op.f('ix_campaigns_status'), table_name='campaigns')
    op.drop_index(op.f('ix_campaigns_id'), table_name='campaigns')
    op.drop_table('campaigns')

    op.drop_index(op.f('ix_contacts_phone_number_normalized'), table_name='contacts')
    op.drop_index(op.f('ix_contacts_phone_number'), table_name='contacts')
    op.drop_index(op.f('ix_contacts_import_id'), table_name='contacts')
    op.drop_index(op.f('ix_contacts_id'), table_name='contacts')
    op.drop_table('contacts')

    op.drop_index(op.f('ix_contact_imports_id'), table_name='contact_imports')
    op.drop_table('contact_imports')

    op.drop_index(op.f('ix_company_profiles_user_id'), table_name='company_profiles')
    op.drop_index(op.f('ix_company_profiles_id'), table_name='company_profiles')
    op.drop_table('company_profiles')

    op.drop_index(op.f('ix_users_id'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
