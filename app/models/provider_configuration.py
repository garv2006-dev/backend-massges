import uuid
from sqlalchemy import Column, String, DateTime, Text, JSON, Enum as SQLEnum
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
import enum
from app.database import Base

class ProviderType(str, enum.Enum):
    TELEPHONY = "telephony"
    STT = "stt"  # Speech-to-Text
    LLM = "llm"  # Language Model
    TTS = "tts"  # Text-to-Speech

class ProviderConfiguration(Base):
    __tablename__ = "provider_configurations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    provider_type = Column(SQLEnum(ProviderType), nullable=False, index=True)
    provider_name = Column(String(50), nullable=False, index=True)  # e.g., "twilio", "deepgram", "gemini"
    is_active = Column(String(20), default="true")  # "true" or "false" as string for encryption compatibility
    configuration = Column(JSON, nullable=True)  # Provider-specific configuration (without secrets)
    display_name = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
