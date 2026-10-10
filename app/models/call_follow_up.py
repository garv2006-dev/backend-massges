import uuid
from sqlalchemy import Column, String, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base

class CallFollowUp(Base):
    """
    Structured schedule of contact follow-up requested during an AI voice call.
    """
    __tablename__ = "call_follow_ups"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    call_id = Column(UUID(as_uuid=True), ForeignKey("calls.id", ondelete="CASCADE"), nullable=False, index=True)
    contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, index=True)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True, index=True)
    organization_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    
    scheduled_time = Column(DateTime(timezone=True), nullable=False, index=True)
    channel = Column(String(50), default="voice", nullable=False)  # voice, whatsapp, email, sms
    status = Column(String(30), default="scheduled", nullable=False, index=True)  # scheduled, completed, cancelled
    notes = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    call = relationship("Call", backref="follow_ups")
    contact = relationship("Contact", backref="follow_ups")
    campaign = relationship("Campaign", backref="follow_ups")
