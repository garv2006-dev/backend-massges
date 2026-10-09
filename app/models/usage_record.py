import uuid
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Numeric
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base

class UsageRecord(Base):
    __tablename__ = "usage_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    call_id = Column(UUID(as_uuid=True), ForeignKey("calls.id", ondelete="SET NULL"), nullable=True, index=True)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True, index=True)
    
    # Usage metrics
    metric_type = Column(String(50), nullable=False, index=True)  # e.g., "telephony_minutes", "stt_seconds", "llm_tokens", "tts_characters"
    provider = Column(String(50), nullable=True)
    quantity = Column(Integer, nullable=False)  # The amount used
    unit = Column(String(20), nullable=False)  # e.g., "minutes", "seconds", "tokens", "characters"
    
    # Cost estimation
    estimated_cost = Column(Numeric(10, 4), nullable=True)  # Estimated cost in USD
    currency = Column(String(3), default="USD")
    
    recorded_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # Relationships
    call = relationship("Call", backref="usage_records")
    campaign = relationship("Campaign", backref="usage_records")
