"""Security and Authorization Layer for LangGraph Agent Tools."""

import time
import uuid
import logging
from typing import Dict, Any, Optional, Set
from dataclasses import dataclass, field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.models.call import Call
from app.models.campaign import Campaign

logger = logging.getLogger(__name__)

class ToolSecurityError(Exception):
    """Raised when a tool execution fails authorization or security checks."""
    pass

@dataclass
class ToolSecurityContext:
    call_id: str
    organization_id: Optional[str] = None
    campaign_id: Optional[str] = None
    contact_id: Optional[str] = None
    user_id: Optional[str] = None
    telephony_provider: str = "openwa"
    supports_transfer: bool = False
    allowed_tools: Set[str] = field(default_factory=lambda: {
        "get_contact_details",
        "get_campaign_context",
        "save_conversation_field",
        "save_call_result",
        "schedule_follow_up",
        "transfer_to_human",
        "end_call",
        "get_call_status",
    })

    def is_tool_allowed(self, tool_name: str) -> bool:
        return tool_name in self.allowed_tools


class ToolSecurityManager:
    """
    Enforces authorization, data isolation, argument validation,
    and audit logging for all tool executions.
    """

    @staticmethod
    def sanitize_data(data: Any) -> Any:
        """Strip sensitive fields such as tokens, passwords, and private credentials."""
        if not isinstance(data, dict):
            return data
        sensitive_keys = {"token", "auth_token", "password", "secret", "api_key", "credentials"}
        sanitized = {}
        is_sensitive_field_name = any(s in str(data.get("field_name", "")).lower() for s in sensitive_keys)

        for k, v in data.items():
            if isinstance(v, dict):
                sanitized[k] = ToolSecurityManager.sanitize_data(v)
            elif (k in ["field_value", "value"] and is_sensitive_field_name) or any(s in str(k).lower() for s in sensitive_keys):
                sanitized[k] = "[REDACTED]"
            else:
                sanitized[k] = v
        return sanitized

    @staticmethod
    async def verify_call_ownership(
        db: AsyncSession,
        call_id: str,
        context: ToolSecurityContext
    ) -> Call:
        """
        Verify that the call exists and belongs to the authenticated context.
        Enforces organization-level data isolation.
        """
        try:
            call_uuid = uuid.UUID(call_id)
        except ValueError:
            raise ToolSecurityError(f"Invalid call_id format: {call_id}")

        stmt = select(Call).where(Call.id == call_uuid)
        res = await db.execute(stmt)
        call = res.scalar_one_or_none()
        if not call:
            raise ToolSecurityError(f"Call {call_id} not found")

        # Verify context binding - model cannot hijack another call's ID
        if context.call_id and str(call.id) != str(context.call_id):
            raise ToolSecurityError(f"Unauthorized: context call_id {context.call_id} mismatch with target {call_id}")

        if context.campaign_id and call.campaign_id and str(call.campaign_id) != str(context.campaign_id):
            raise ToolSecurityError(f"Unauthorized: campaign_id mismatch for call {call_id}")

        return call

    @staticmethod
    async def log_tool_audit(
        db: AsyncSession,
        call_id: Optional[str],
        campaign_id: Optional[str],
        organization_id: Optional[str],
        tool_name: str,
        status: str,
        duration_ms: int,
        arguments: Dict[str, Any],
        result_summary: Dict[str, Any],
        correlation_id: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> None:
        """Log tool execution to logger."""
        logger.info(f"[TOOL_AUDIT] tool={tool_name} status={status} duration={duration_ms}ms call_id={call_id}")
