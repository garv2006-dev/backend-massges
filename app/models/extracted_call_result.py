import uuid
from sqlalchemy import Column, String, Integer, DateTime, Text, JSON, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base

class ExtractedCallResult(Base):
    __tablename__ = "extracted_call_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    call_id = Column(UUID(as_uuid=True), ForeignKey("calls.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    
    # Extracted fields
    customer_name = Column(String(255), nullable=True)
    customer_intent = Column(String(255), nullable=True)
    customer_rating = Column(Integer, nullable=True)  # 1-5 scale
    complaint = Column(Text, nullable=True)
    follow_up_required = Column(String(20), nullable=True)  # yes, no, maybe
    follow_up_notes = Column(Text, nullable=True)
    call_outcome = Column(String(100), nullable=True)
    
    # Raw structured data
    raw_extracted_data = Column(JSON, nullable=True)
    
    # Validation
    validation_status = Column(String(20), default="pending")  # pending, validated, failed
    validation_errors = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    call = relationship("Call", backref="extracted_result")
