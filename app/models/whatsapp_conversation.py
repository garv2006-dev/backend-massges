import uuid
from sqlalchemy import Column, String, Integer, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base

class WhatsAppConversation(Base):
    __tablename__ = "whatsapp_conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True, index=True)
    phone_number = Column(String(50), nullable=False, index=True)
    contact_name = Column(String(255), nullable=True)
    chat_jid = Column(String(100), nullable=True, index=True)
    last_message_text = Column(Text, nullable=True)
    last_message_at = Column(DateTime(timezone=True), nullable=True)
    unread_count = Column(Integer, default=0, nullable=False)
    is_pinned = Column(Boolean, default=False, nullable=False)
    is_archived = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    messages = relationship("WhatsAppMessage", back_populates="conversation", cascade="all, delete-orphan", order_by="WhatsAppMessage.created_at.asc()")
    contact = relationship("Contact", backref="whatsapp_conversations")
