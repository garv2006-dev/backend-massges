import uuid
from sqlalchemy import Column, String, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base

class ContactConsent(Base):
    __tablename__ = "contact_consents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=True, index=True)
    phone_number = Column(String(30), nullable=False, index=True)
    organization_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    consent_status = Column(String(50), default="consented", nullable=False, index=True)  # consented, revoked, pending, opted_out
    channel = Column(String(50), default="voice", nullable=False)
    proof_reference = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    contact = relationship("Contact", backref="consents")


class SuppressionRecord(Base):
    __tablename__ = "suppression_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    phone_number = Column(String(30), nullable=False, index=True)
    organization_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    reason = Column(String(100), default="opt_out", nullable=False, index=True)  # opt_out, dnc, legal_suppression, complaint
    source_call_id = Column(UUID(as_uuid=True), ForeignKey("calls.id", ondelete="SET NULL"), nullable=True, index=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    source_call = relationship("Call", backref="suppressions")
