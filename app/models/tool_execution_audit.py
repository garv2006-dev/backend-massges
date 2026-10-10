import uuid
from sqlalchemy import Column, String, Integer, DateTime, JSON, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base

class ToolExecutionAuditLog(Base):
    """
    Privileged tool execution audit log for security, compliance,
    and monitoring of LangGraph tool invocation.
    """
    __tablename__ = "tool_execution_audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    call_id = Column(UUID(as_uuid=True), ForeignKey("calls.id", ondelete="CASCADE"), nullable=True, index=True)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True, index=True)
    organization_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    
    tool_name = Column(String(100), nullable=False, index=True)
    status = Column(String(30), nullable=False, index=True)  # success, error, unauthorized, validation_failed
    execution_duration_ms = Column(Integer, default=0, nullable=False)
    
    # Sanitized arguments and outputs (no passwords, API keys, or raw PII)
    arguments = Column(JSON, nullable=True)
    result_summary = Column(JSON, nullable=True)
    correlation_id = Column(String(100), nullable=True, index=True)
    error_message = Column(String(500), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    call = relationship("Call", backref="tool_audit_logs")
    campaign = relationship("Campaign", backref="tool_audit_logs")
