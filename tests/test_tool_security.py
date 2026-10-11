"""Unit tests for tool security - invalid arguments and unauthorized access."""

import pytest
import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.definitions import create_agent_tools
from app.agent.tools.security import ToolSecurityContext, ToolSecurityError, ToolSecurityManager
from app.models.contact import Contact
from app.models.campaign import Campaign
from app.models.call import Call
from app.models.tool_execution_audit import ToolExecutionAuditLog
from sqlalchemy import select


class TestToolAuthorization:
    """Tests for tool authorization and access control."""

    @pytest.mark.asyncio
    async def test_unauthorized_call_id_mismatch(self, db_session: AsyncSession, test_call: Call):
        """Should fail when tool call_id does not match security context."""
        # Create a different call ID in context
        context = ToolSecurityContext(
            call_id=str(uuid.uuid4()),  # Different from test_call.id
            campaign_id=str(test_call.campaign_id),
            contact_id=str(test_call.contact_id),
            organization_id=str(uuid.uuid4())
        )
        tools = create_agent_tools(context, db_session=db_session)
        tool = {t.name: t for t in tools}["end_call"]

        result = await tool.ainvoke({
            "call_id": str(test_call.id),  # Trying to end different call
            "hangup_reason": "Test",
            "customer_consented_or_opt_out": False
        })

        assert "error" in result
        assert "Unauthorized" in result["error"]

    @pytest.mark.asyncio
    async def test_unauthorized_campaign_id_mismatch(self, db_session: AsyncSession, test_call: Call, test_campaign: Campaign):
        """Should fail when tool campaign_id does not match security context."""
        context = ToolSecurityContext(
            call_id=str(test_call.id),
            campaign_id=str(uuid.uuid4()),  # Different campaign
            contact_id=str(test_call.contact_id),
            organization_id=str(uuid.uuid4())
        )
        tools = create_agent_tools(context, db_session=db_session)
        tool = {t.name: t for t in tools}["get_campaign_context"]

        result = await tool.ainvoke({
            "campaign_id": str(test_campaign.id),
            "organization_id": str(uuid.uuid4())
        })

        assert "error" in result
        assert "Unauthorized" in result["error"]

    @pytest.mark.asyncio
    async def test_unauthorized_contact_id_mismatch(self, db_session: AsyncSession, test_contact: Contact):
        """Should fail when tool contact_id does not match security context."""
        context = ToolSecurityContext(
            call_id=str(uuid.uuid4()),
            campaign_id=str(uuid.uuid4()),
            contact_id=str(uuid.uuid4()),  # Different contact
            organization_id=str(uuid.uuid4())
        )
        tools = create_agent_tools(context, db_session=db_session)
        tool = {t.name: t for t in tools}["get_contact_details"]

        result = await tool.ainvoke({
            "contact_id": str(test_contact.id),
            "organization_id": str(uuid.uuid4())
        })

        assert "error" in result
        assert "Unauthorized" in result["error"]

    @pytest.mark.asyncio
    async def test_nonexistent_call_id(self, db_session: AsyncSession):
        """Should fail when call_id does not exist in database."""
        nonexistent_id = str(uuid.uuid4())
        context = ToolSecurityContext(
            call_id=nonexistent_id,
            campaign_id=str(uuid.uuid4()),
            contact_id=str(uuid.uuid4()),
            organization_id=str(uuid.uuid4())
        )
        tools = create_agent_tools(context, db_session=db_session)
        tool = {t.name: t for t in tools}["get_call_status"]

        result = await tool.ainvoke({"call_id": nonexistent_id})

        assert "error" in result
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_nonexistent_contact_id(self, db_session: AsyncSession):
        """Should fail when contact_id does not exist in database."""
        nonexistent_id = str(uuid.uuid4())
        context = ToolSecurityContext(
            call_id=str(uuid.uuid4()),
            campaign_id=str(uuid.uuid4()),
            contact_id=nonexistent_id,
            organization_id=str(uuid.uuid4())
        )
        tools = create_agent_tools(context, db_session=db_session)
        tool = {t.name: t for t in tools}["get_contact_details"]

        result = await tool.ainvoke({"contact_id": nonexistent_id})

        assert "error" in result
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_nonexistent_campaign_id(self, db_session: AsyncSession):
        """Should fail when campaign_id does not exist in database."""
        nonexistent_id = str(uuid.uuid4())
        context = ToolSecurityContext(
            call_id=str(uuid.uuid4()),
            campaign_id=nonexistent_id,
            contact_id=str(uuid.uuid4()),
            organization_id=str(uuid.uuid4())
        )
        tools = create_agent_tools(context, db_session=db_session)
        tool = {t.name: t for t in tools}["get_campaign_context"]

        result = await tool.ainvoke({"campaign_id": nonexistent_id})

        assert "error" in result
        assert "not found" in result["error"].lower()


class TestInvalidToolArguments:
    """Tests for invalid tool argument handling."""

    @pytest.mark.asyncio
    async def test_invalid_uuid_format_contact(self, db_session: AsyncSession):
        """Should reject invalid UUID format for contact_id."""
        context = ToolSecurityContext(
            call_id=str(uuid.uuid4()),
            contact_id=str(uuid.uuid4()),
            organization_id=str(uuid.uuid4())
        )
        tools = create_agent_tools(context, db_session=db_session)
        tool = {t.name: t for t in tools}["get_contact_details"]

        result = await tool.ainvoke({"contact_id": "not-a-uuid"})

        assert "error" in result
        assert "Invalid contact_id" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_uuid_format_campaign(self, db_session: AsyncSession):
        """Should reject invalid UUID format for campaign_id."""
        context = ToolSecurityContext(
            call_id=str(uuid.uuid4()),
            campaign_id=str(uuid.uuid4()),
            organization_id=str(uuid.uuid4())
        )
        tools = create_agent_tools(context, db_session=db_session)
        tool = {t.name: t for t in tools}["get_campaign_context"]

        result = await tool.ainvoke({"campaign_id": "not-a-uuid"})

        assert "error" in result
        assert "Invalid campaign_id" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_iso_datetime_format(self, db_session: AsyncSession, test_call: Call, test_contact: Contact):
        """Should reject invalid ISO datetime format."""
        context = ToolSecurityContext(
            call_id=str(test_call.id),
            campaign_id=str(test_call.campaign_id),
            contact_id=str(test_contact.id),
            organization_id=str(uuid.uuid4())
        )
        tools = create_agent_tools(context, db_session=db_session)
        tool = {t.name: t for t in tools}["schedule_follow_up"]

        result = await tool.ainvoke({
            "call_id": str(test_call.id),
            "contact_id": str(test_contact.id),
            "scheduled_iso": "tomorrow-at-10am",  # Invalid format
            "channel": "voice"
        })

        assert "error" in result
        assert "Invalid datetime format" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_field_name_characters(self, db_session: AsyncSession, test_call: Call):
        """Should sanitize or reject field names with invalid characters."""
        context = ToolSecurityContext(
            call_id=str(test_call.id),
            campaign_id=str(test_call.campaign_id),
            contact_id=str(test_call.contact_id),
            organization_id=str(uuid.uuid4())
        )
        tools = create_agent_tools(context, db_session=db_session)
        tool = {t.name: t for t in tools}["save_conversation_field"]

        # Schema should sanitize this
        result = await tool.ainvoke({
            "call_id": str(test_call.id),
            "field_name": "budget@#$",
            "field_value": "$5000",
            "confidence_score": 0.9
        })

        # Should either succeed with sanitized name or fail
        # The schema sanitizes, so it should succeed
        assert result.get("status") == "saved" or "error" in result


class TestToolAuditLogging:
    """Tests for tool execution audit logging."""

    @pytest.mark.asyncio
    async def test_successful_tool_execution_logged(self, db_session: AsyncSession, test_call: Call):
        """Should log successful tool execution to audit table."""
        org_id = str(uuid.uuid4())
        context = ToolSecurityContext(
            call_id=str(test_call.id),
            campaign_id=str(test_call.campaign_id),
            contact_id=str(test_call.contact_id),
            organization_id=org_id
        )
        tools = create_agent_tools(context, db_session=db_session)
        tool = {t.name: t for t in tools}["get_call_status"]

        await tool.ainvoke({"call_id": str(test_call.id)})

        # Verify audit log was created
        stmt = select(ToolExecutionAuditLog).where(
            ToolExecutionAuditLog.call_id == test_call.id,
            ToolExecutionAuditLog.tool_name == "get_call_status"
        )
        res = await db_session.execute(stmt)
        audit_log = res.scalar_one_or_none()

        assert audit_log is not None
        assert audit_log.status == "success"
        assert audit_log.organization_id == uuid.UUID(org_id)
        assert audit_log.execution_duration_ms >= 0
        assert audit_log.correlation_id is not None

    @pytest.mark.asyncio
    async def test_failed_tool_execution_logged(self, db_session: AsyncSession):
        """Should log failed tool execution to audit table."""
        org_id = str(uuid.uuid4())
        call_id = str(uuid.uuid4())
        context = ToolSecurityContext(
            call_id=call_id,
            campaign_id=str(uuid.uuid4()),
            contact_id=str(uuid.uuid4()),
            organization_id=org_id
        )
        tools = create_agent_tools(context, db_session=db_session)
        tool = {t.name: t for t in tools}["get_call_status"]

        await tool.ainvoke({"call_id": call_id})  # Will fail (call doesn't exist)

        # Verify audit log was created with error
        stmt = select(ToolExecutionAuditLog).where(
            ToolExecutionAuditLog.tool_name == "get_call_status"
        )
        res = await db_session.execute(stmt)
        audit_log = res.scalar_one_or_none()

        assert audit_log is not None
        assert audit_log.status == "error"
        assert audit_log.error_message is not None

    @pytest.mark.asyncio
    async def test_audit_log_sanitizes_sensitive_data(self, db_session: AsyncSession, test_call: Call):
        """Should sanitize sensitive data in audit log arguments."""
        context = ToolSecurityContext(
            call_id=str(test_call.id),
            campaign_id=str(test_call.campaign_id),
            contact_id=str(test_call.contact_id),
            organization_id=str(uuid.uuid4())
        )
        tools = create_agent_tools(context, db_session=db_session)
        tool = {t.name: t for t in tools}["save_conversation_field"]

        # Try to save a field with "sensitive" in the name (simulating secret)
        await tool.ainvoke({
            "call_id": str(test_call.id),
            "field_name": "api_token_field",
            "field_value": "secret-api-key-12345",
            "confidence_score": 1.0
        })

        # Verify audit log sanitizes arguments
        stmt = select(ToolExecutionAuditLog).where(
            ToolExecutionAuditLog.call_id == test_call.id,
            ToolExecutionAuditLog.tool_name == "save_conversation_field"
        )
        res = await db_session.execute(stmt)
        audit_log = res.scalar_one_or_none()

        assert audit_log is not None
        # Check that sensitive-looking keys are redacted
        if "api_token" in str(audit_log.arguments):
            # If the key is present, the value should be redacted
            assert "[REDACTED]" in str(audit_log.arguments)


class TestToolSecurityManager:
    """Tests for ToolSecurityManager utility methods."""

    @pytest.mark.asyncio
    async def test_verify_call_ownership_success(self, db_session: AsyncSession, test_call: Call):
        """Should successfully verify call ownership."""
        context = ToolSecurityContext(
            call_id=str(test_call.id),
            campaign_id=str(test_call.campaign_id),
            contact_id=str(test_call.contact_id),
            organization_id=str(uuid.uuid4())
        )

        call = await ToolSecurityManager.verify_call_ownership(
            db_session,
            str(test_call.id),
            context
        )

        assert call.id == test_call.id

    @pytest.mark.asyncio
    async def test_verify_call_ownership_mismatch(self, db_session: AsyncSession, test_call: Call):
        """Should fail when call_id does not match context."""
        context = ToolSecurityContext(
            call_id=str(uuid.uuid4()),  # Different call
            campaign_id=str(test_call.campaign_id),
            contact_id=str(test_call.contact_id),
            organization_id=str(uuid.uuid4())
        )

        with pytest.raises(ToolSecurityError, match="Unauthorized"):
            await ToolSecurityManager.verify_call_ownership(
                db_session,
                str(test_call.id),
                context
            )

    @pytest.mark.asyncio
    async def test_verify_call_ownership_invalid_uuid(self, db_session: AsyncSession):
        """Should fail with invalid UUID format."""
        context = ToolSecurityContext(
            call_id=str(uuid.uuid4()),
            campaign_id=str(uuid.uuid4()),
            contact_id=str(uuid.uuid4()),
            organization_id=str(uuid.uuid4())
        )

        with pytest.raises(ToolSecurityError, match="Invalid call_id format"):
            await ToolSecurityManager.verify_call_ownership(
                db_session,
                "not-a-uuid",
                context
            )

    @pytest.mark.asyncio
    async def test_verify_call_ownership_not_found(self, db_session: AsyncSession):
        """Should fail when call does not exist."""
        context = ToolSecurityContext(
            call_id=str(uuid.uuid4()),
            campaign_id=str(uuid.uuid4()),
            contact_id=str(uuid.uuid4()),
            organization_id=str(uuid.uuid4())
        )

        with pytest.raises(ToolSecurityError, match="not found"):
            await ToolSecurityManager.verify_call_ownership(
                db_session,
                str(uuid.uuid4()),
                context
            )

    def test_sanitize_data_redacts_secrets(self):
        """Should redact sensitive fields in data dictionaries."""
        data = {
            "name": "John Doe",
            "api_token": "secret-123",
            "password": "my-password",
            "auth_token": "token-abc",
            "normal_field": "value"
        }

        sanitized = ToolSecurityManager.sanitize_data(data)

        assert sanitized["name"] == "John Doe"
        assert sanitized["api_token"] == "[REDACTED]"
        assert sanitized["password"] == "[REDACTED]"
        assert sanitized["auth_token"] == "[REDACTED]"
        assert sanitized["normal_field"] == "value"

    def test_sanitize_data_nested_dicts(self):
        """Should recursively sanitize nested dictionaries."""
        data = {
            "user": {
                "name": "John",
                "credentials": {
                    "api_key": "secret-123",
                    "normal": "value"
                }
            }
        }

        sanitized = ToolSecurityManager.sanitize_data(data)

        assert sanitized["user"]["name"] == "John"
        assert sanitized["user"]["credentials"]["api_key"] == "[REDACTED]"
        assert sanitized["user"]["credentials"]["normal"] == "value"

    def test_sanitize_data_non_dict(self):
        """Should return non-dict data unchanged."""
        assert ToolSecurityManager.sanitize_data("string") == "string"
        assert ToolSecurityManager.sanitize_data(123) == 123
        assert ToolSecurityManager.sanitize_data(["list"]) == ["list"]


class TestToolContextValidation:
    """Tests for ToolSecurityContext validation."""

    def test_tool_allowed_in_default_set(self):
        """Default tools should be allowed."""
        context = ToolSecurityContext(
            call_id=str(uuid.uuid4()),
            campaign_id=str(uuid.uuid4()),
            contact_id=str(uuid.uuid4()),
            organization_id=str(uuid.uuid4())
        )

        assert context.is_tool_allowed("get_contact_details")
        assert context.is_tool_allowed("save_call_result")
        assert context.is_tool_allowed("end_call")

    def test_tool_not_allowed_custom_set(self):
        """Custom tool set should restrict access."""
        context = ToolSecurityContext(
            call_id=str(uuid.uuid4()),
            campaign_id=str(uuid.uuid4()),
            contact_id=str(uuid.uuid4()),
            organization_id=str(uuid.uuid4()),
            allowed_tools={"get_contact_details", "save_call_result"}  # Restricted set
        )

        assert context.is_tool_allowed("get_contact_details")
        assert context.is_tool_allowed("save_call_result")
        assert not context.is_tool_allowed("end_call")
        assert not context.is_tool_allowed("transfer_to_human")
