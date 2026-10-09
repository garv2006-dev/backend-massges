import uuid
from sqlalchemy import Column, String, Integer, DateTime, Text, JSON, Enum as SQLEnum
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
import enum
from app.database import Base

class CampaignStatus(str, enum.Enum):
    DRAFT = "draft"
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"

class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(SQLEnum(CampaignStatus), default=CampaignStatus.DRAFT, nullable=False, index=True)
    agent_prompt = Column(Text, nullable=True)
    max_call_duration = Column(Integer, default=300)  # seconds
    max_retries = Column(Integer, default=3)
    concurrency_limit = Column(Integer, default=5)
    start_time = Column(DateTime(timezone=True), nullable=True)
    end_time = Column(DateTime(timezone=True), nullable=True)
    provider_config = Column(JSON, nullable=True)  # Provider-specific configuration
    total_contacts = Column(Integer, default=0)
    queued_calls = Column(Integer, default=0)
    in_progress_calls = Column(Integer, default=0)
    completed_calls = Column(Integer, default=0)
    failed_calls = Column(Integer, default=0)
    no_answer_calls = Column(Integer, default=0)
    answered_calls = Column(Integer, default=0)
    created_by = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
