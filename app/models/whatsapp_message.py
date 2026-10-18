import uuid
from sqlalchemy import Column, String, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base

class WhatsAppMessage(Base):
    __tablename__ = "whatsapp_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("whatsapp_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True, index=True)
    sender = Column(String(50), nullable=False, default="agent")  # "agent", "customer", "user"
    direction = Column(String(20), nullable=False, default="outbound")  # "inbound", "outbound"
    message_text = Column(Text, nullable=False)
    status = Column(String(30), default="sent")  # "sent", "delivered", "read", "failed"
    openwa_message_id = Column(String(255), nullable=True)
    chat_jid = Column(String(100), nullable=True)
    ai_generated = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # Relationships
    conversation = relationship("WhatsAppConversation", back_populates="messages")
    campaign = relationship("Campaign", backref="whatsapp_messages")
