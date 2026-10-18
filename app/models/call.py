import uuid
from sqlalchemy import Column, String, Integer, DateTime, Text, JSON, Enum as SQLEnum, ForeignKey, Numeric
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum
from app.database import Base

class CallStatus(str, enum.Enum):
    QUEUED = "queued"
    RINGING = "ringing"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    NO_ANSWER = "no_answer"
    BUSY = "busy"
    CANCELLED = "cancelled"
    REJECTED = "rejected"

class CallDirection(str, enum.Enum):
    OUTBOUND = "outbound"
    INBOUND = "inbound"

class Call(Base):
    __tablename__ = "calls"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True, index=True)
    campaign_contact_id = Column(UUID(as_uuid=True), ForeignKey("campaign_contacts.id", ondelete="SET NULL"), nullable=True, index=True)
    contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True, index=True)
    
    # Provider information
    provider_call_id = Column(String(255), nullable=True, index=True)  # External provider's call ID
    provider = Column(String(50), nullable=True)  # e.g., "openwa"
    
    # Call details
    phone_number = Column(String(20), nullable=False)
    direction = Column(SQLEnum(CallDirection), default=CallDirection.OUTBOUND, nullable=False)
    status = Column(SQLEnum(CallStatus), default=CallStatus.QUEUED, nullable=False, index=True)
    
    # Timing
    queued_at = Column(DateTime(timezone=True), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    
    # Results
    failure_reason = Column(Text, nullable=True)
    hangup_cause = Column(String(100), nullable=True)
    
    # AI-specific
    ai_interactions = Column(Integer, default=0)
    ai_confidence_score = Column(Integer, nullable=True)  # 0-100
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    campaign = relationship("Campaign", backref="calls")
    campaign_contact = relationship("CampaignContact", backref="calls")
    contact = relationship("Contact", backref="calls")
