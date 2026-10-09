import uuid
from sqlalchemy import Column, String, DateTime, JSON, Text
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base

class Contact(Base):
    __tablename__ = "contacts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    import_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    phone_number = Column(String(20), nullable=False, index=True)
    phone_number_normalized = Column(String(20), nullable=False, index=True, unique=True)
    name = Column(String(255))
    email = Column(String(255))
    language = Column(String(10), default="en")
    custom_fields = Column(JSON, nullable=True)
    validation_status = Column(String(20), default="valid")  # valid, invalid, duplicate
    validation_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
