import uuid
from sqlalchemy import Column, String, DateTime, Text, JSON, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    
    # Action details
    action = Column(String(100), nullable=False, index=True)  # e.g., "campaign_created", "campaign_started", "call_initiated"
    entity_type = Column(String(50), nullable=False, index=True)  # e.g., "campaign", "call", "contact"
    entity_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    
    # Details
    description = Column(Text, nullable=True)
    changes = Column(JSON, nullable=True)  # Before/after state
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    
    # Result
    success = Column(String(20), default="true")  # "true" or "false"
    error_message = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # Relationships
    user = relationship("User", backref="audit_logs")
