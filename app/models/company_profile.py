import uuid
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base

class CompanyProfile(Base):
    __tablename__ = "company_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, unique=True, index=True)
    name = Column(String(255), default="", nullable=False)
    phone_number = Column(String(50), default="", nullable=False)
    email = Column(String(255), nullable=True)
    industry = Column(String(255), default="Customer Service & Sales Automation", nullable=True)
    website = Column(String(255), nullable=True)
    default_agent_name = Column(String(100), default="Sarah", nullable=True)
    default_voice = Column(String(100), default="en-IN-NeerjaNeural", nullable=True)
    default_language = Column(String(100), default="English", nullable=True)
    simulated_connected = Column(Boolean, default=False, nullable=False)
    whatsapp_phone = Column(String(50), default="", nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Optional relationship to user
    user = relationship("User", backref="company_profile")
