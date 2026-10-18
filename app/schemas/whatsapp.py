import uuid
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel

class WhatsAppMessageBase(BaseModel):
    message_text: str
    sender: str = "agent"
    direction: str = "outbound"
    status: str = "sent"
    openwa_message_id: Optional[str] = None
    chat_jid: Optional[str] = None
    ai_generated: bool = False

class WhatsAppMessageCreate(WhatsAppMessageBase):
    conversation_id: uuid.UUID
    campaign_id: Optional[uuid.UUID] = None

class WhatsAppMessageResponse(WhatsAppMessageBase):
    id: uuid.UUID
    conversation_id: uuid.UUID
    campaign_id: Optional[uuid.UUID] = None
    created_at: datetime

    class Config:
        from_attributes = True

class WhatsAppConversationBase(BaseModel):
    phone_number: str
    contact_name: Optional[str] = None
    chat_jid: Optional[str] = None
    last_message_text: Optional[str] = None
    last_message_at: Optional[datetime] = None
    unread_count: int = 0
    is_pinned: bool = False
    is_archived: bool = False

class WhatsAppConversationCreate(WhatsAppConversationBase):
    contact_id: Optional[uuid.UUID] = None
    user_id: Optional[uuid.UUID] = None

class WhatsAppConversationResponse(WhatsAppConversationBase):
    id: uuid.UUID
    contact_id: Optional[uuid.UUID] = None
    user_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    messages: List[WhatsAppMessageResponse] = []

    class Config:
        from_attributes = True
