"""Unit tests for LangGraph agent tools - selection and execution."""

import pytest
import uuid
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.definitions import create_agent_tools
from app.agent.tools.security import ToolSecurityContext, ToolSecurityError
from app.agent.tools.schemas import (
    GetContactDetailsInput,
    GetCampaignContextInput,
    SaveConversationFieldInput,
    SaveCallResultInput,
    ScheduleFollowUpInput,
    TransferToHumanInput,
    EndCallInput,
    GetCallStatusInput
)
from app.models.contact import Contact
from app.models.campaign import Campaign
from app.models.call import Call, CallStatus
from app.models.extracted_call_result import ExtractedCallResult
from app.models.call_follow_up import CallFollowUp


class TestToolSelection:
    """Tests for tool creation and selection."""

    def test_create_agent_tools_returns_all_tools(self):
        """Should return all 8 defined tools."""
        context = ToolSecurityContext(
            call_id=str(uuid.uuid4()),
            campaign_id=str(uuid.uuid4()),
            contact_id=str(uuid.uuid4()),
            organization_id=str(uuid.uuid4())
        )
        tools = create_agent_tools(context)
        tool_names = [t.name for t in tools]

        expected_tools = [
            "get_contact_details",
            "get_campaign_context",
            "save_conversation_field",
            "save_call_result",
            "schedule_follow_up",
            "transfer_to_human",
            "end_call",
            "get_call_status"
        ]

        assert len(tools) == 8
        for expected in expected_tools:
            assert expected in tool_names

    def test_tool_context_binding(self):
        """Tools should be bound with security context."""
        call_id = str(uuid.uuid4())
        context = ToolSecurityContext(
            call_id=call_id,
            campaign_id=str(uuid.uuid4()),
            contact_id=str(uuid.uuid4()),
            organization_id=str(uuid.uuid4())
        )
        tools = create_agent_tools(context)

        # All tools should have the context available
        for tool in tools:
            assert tool is not None
            assert hasattr(tool, 'ainvoke')


class TestGetContactDetails:
    """Tests for get_contact_details tool."""

    @pytest.mark.asyncio
    async def test_get_contact_details_success(self, db_session: AsyncSession, test_contact: Contact):
        """Should successfully retrieve contact details."""
        context = ToolSecurityContext(
            call_id=str(uuid.uuid4()),
            contact_id=str(test_contact.id),
            organization_id=str(uuid.uuid4())
        )
        tools = create_agent_tools(context, db_session=db_session)
        tool = {t.name: t for t in tools}["get_contact_details"]

        result = await tool.ainvoke({"contact_id": str(test_contact.id)})

        assert result["contact_id"] == str(test_contact.id)
        assert result["name"] == test_contact.name
        assert result["phone_number"] == test_contact.phone_number_normalized
        assert result["email"] == test_contact.email

    @pytest.mark.asyncio
    async def test_get_contact_details_unauthorized_mismatch(self, db_session: AsyncSession, test_contact: Contact):
        """Should fail when contact_id does not match security context."""
        context = ToolSecurityContext(
            call_id=str(uuid.uuid4()),
            contact_id=str(uuid.uuid4()),  # Different contact
            organization_id=str(uuid.uuid4())
        )
        tools = create_agent_tools(context, db_session=db_session)
        tool = {t.name: t for t in tools}["get_contact_details"]

        result = await tool.ainvoke({"contact_id": str(test_contact.id)})

        assert "error" in result
        assert "Unauthorized" in result["error"]

    @pytest.mark.asyncio
    async def test_get_contact_details_invalid_uuid(self, db_session: AsyncSession):
        """Should fail with invalid UUID format."""
        context = ToolSecurityContext(
            call_id=str(uuid.uuid4()),
            contact_id=str(uuid.uuid4()),
            organization_id=str(uuid.uuid4())
        )
        tools = create_agent_tools(context, db_session=db_session)
        tool = {t.name: t for t in tools}["get_contact_details"]

        result = await tool.ainvoke({"contact_id": "invalid-uuid"})

        assert "error" in result
        assert "Invalid contact_id" in result["error"]


class TestGetCampaignContext:
    """Tests for get_campaign_context tool."""

    @pytest.mark.asyncio
    async def test_get_campaign_context_success(self, db_session: AsyncSession, test_campaign: Campaign):
        """Should successfully retrieve campaign context."""
        context = ToolSecurityContext(
            call_id=str(uuid.uuid4()),
            campaign_id=str(test_campaign.id),
            organization_id=str(uuid.uuid4())
        )
        tools = create_agent_tools(context, db_session=db_session)
        tool = {t.name: t for t in tools}["get_campaign_context"]

        result = await tool.ainvoke({"campaign_id": str(test_campaign.id)})

        assert result["campaign_id"] == str(test_campaign.id)
        assert result["campaign_name"] == test_campaign.name
        assert result["agent_prompt"] == test_campaign.agent_prompt

    @pytest.mark.asyncio
    async def test_get_campaign_context_unauthorized_mismatch(self, db_session: AsyncSession, test_campaign: Campaign):
        """Should fail when campaign_id does not match security context."""
        context = ToolSecurityContext(
            call_id=str(uuid.uuid4()),
            campaign_id=str(uuid.uuid4()),  # Different campaign
            organization_id=str(uuid.uuid4())
        )
        tools = create_agent_tools(context, db_session=db_session)
        tool = {t.name: t for t in tools}["get_campaign_context"]

        result = await tool.ainvoke({"campaign_id": str(test_campaign.id)})

        assert "error" in result
        assert "Unauthorized" in result["error"]


class TestSaveConversationField:
    """Tests for save_conversation_field tool."""

    @pytest.mark.asyncio
    async def test_save_conversation_field_success(self, db_session: AsyncSession, test_call: Call):
        """Should successfully save extracted field."""
        context = ToolSecurityContext(
            call_id=str(test_call.id),
            campaign_id=str(test_call.campaign_id),
            contact_id=str(test_call.contact_id),
            organization_id=str(uuid.uuid4())
        )
        tools = create_agent_tools(context, db_session=db_session)
        tool = {t.name: t for t in tools}["save_conversation_field"]

        result = await tool.ainvoke({
            "call_id": str(test_call.id),
            "field_name": "budget",
            "field_value": "$5000",
            "confidence_score": 0.9
        })

        assert result["status"] == "saved"
        assert result["field_name"] == "budget"
        assert result["field_value"] == "$5000"

        # Verify in database
        from sqlalchemy import select
        stmt = select(ExtractedCallResult).where(ExtractedCallResult.call_id == test_call.id)
        res = await db_session.execute(stmt)
        extracted = res.scalar_one_or_none()
        assert extracted is not None
        assert "budget" in extracted.raw_extracted_data


class TestSaveCallResult:
    """Tests for save_call_result tool."""

    @pytest.mark.asyncio
    async def test_save_call_result_success(self, db_session: AsyncSession, test_call: Call):
        """Should successfully save final call result."""
        context = ToolSecurityContext(
            call_id=str(test_call.id),
            campaign_id=str(test_call.campaign_id),
            contact_id=str(test_call.contact_id),
            organization_id=str(uuid.uuid4())
        )
        tools = create_agent_tools(context, db_session=db_session)
        tool = {t.name: t for t in tools}["save_call_result"]

        result = await tool.ainvoke({
            "call_id": str(test_call.id),
            "call_outcome": "Interested",
            "customer_intent": "Learn more about services",
            "customer_rating": 5,
            "follow_up_required": "yes",
            "follow_up_notes": "Schedule demo next week"
        })

        assert result["status"] == "persisted"
        assert result["call_outcome"] == "Interested"

        # Verify in database
        from sqlalchemy import select
        stmt = select(ExtractedCallResult).where(ExtractedCallResult.call_id == test_call.id)
        res = await db_session.execute(stmt)
        extracted = res.scalar_one_or_none()
        assert extracted is not None
        assert extracted.call_outcome == "Interested"
        assert extracted.validation_status == "validated"


class TestScheduleFollowUp:
    """Tests for schedule_follow_up tool."""

    @pytest.mark.asyncio
    async def test_schedule_follow_up_success(self, db_session: AsyncSession, test_call: Call, test_contact: Contact):
        """Should successfully schedule follow-up."""
        context = ToolSecurityContext(
            call_id=str(test_call.id),
            campaign_id=str(test_call.campaign_id),
            contact_id=str(test_contact.id),
            organization_id=str(uuid.uuid4())
        )
        tools = create_agent_tools(context, db_session=db_session)
        tool = {t.name: t for t in tools}["schedule_follow_up"]

        scheduled_time = (datetime.utcnow()).replace(hour=10, minute=0, second=0, microsecond=0)
        result = await tool.ainvoke({
            "call_id": str(test_call.id),
            "contact_id": str(test_contact.id),
            "scheduled_iso": scheduled_time.isoformat(),
            "channel": "voice",
            "notes": "Customer requested callback"
        })

        assert result["status"] == "scheduled"
        assert "follow_up_id" in result
        assert result["channel"] == "voice"

        # Verify in database
        from sqlalchemy import select
        stmt = select(CallFollowUp).where(CallFollowUp.call_id == test_call.id)
        res = await db_session.execute(stmt)
        follow_up = res.scalar_one_or_none()
        assert follow_up is not None
        assert follow_up.status == "scheduled"

    @pytest.mark.asyncio
    async def test_schedule_follow_up_invalid_datetime(self, db_session: AsyncSession, test_call: Call, test_contact: Contact):
        """Should fail with invalid datetime format."""
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
            "scheduled_iso": "invalid-datetime",
            "channel": "voice"
        })

        assert "error" in result
        assert "Invalid datetime format" in result["error"]


class TestEndCall:
    """Tests for end_call tool."""

    @pytest.mark.asyncio
    async def test_end_call_success(self, db_session: AsyncSession, test_call: Call):
        """Should successfully end call."""
        context = ToolSecurityContext(
            call_id=str(test_call.id),
            campaign_id=str(test_call.campaign_id),
            contact_id=str(test_call.contact_id),
            organization_id=str(uuid.uuid4())
        )
        tools = create_agent_tools(context, db_session=db_session)
        tool = {t.name: t for t in tools}["end_call"]

        result = await tool.ainvoke({
            "call_id": str(test_call.id),
            "hangup_reason": "Goal Completed",
            "customer_consented_or_opt_out": False
        })

        assert result["status"] == "terminated"
        assert result["should_disconnect"] is True

        # Verify in database
        await db_session.refresh(test_call)
        assert test_call.status == CallStatus.COMPLETED
        assert test_call.hangup_cause == "Goal Completed"


class TestTransferToHuman:
    """Tests for transfer_to_human tool."""

    @pytest.mark.asyncio
    async def test_transfer_unsupported(self, db_session: AsyncSession, test_call: Call):
        """Should return unsupported when provider doesn't support transfer."""
        context = ToolSecurityContext(
            call_id=str(test_call.id),
            campaign_id=str(test_call.campaign_id),
            contact_id=str(test_call.contact_id),
            organization_id=str(uuid.uuid4()),
            supports_transfer=False  # Provider doesn't support transfer
        )
        tools = create_agent_tools(context, db_session=db_session)
        tool = {t.name: t for t in tools}["transfer_to_human"]

        result = await tool.ainvoke({
            "call_id": str(test_call.id),
            "reason": "Customer requested supervisor",
            "department": "support"
        })

        assert result["status"] == "transfer_unsupported"
        assert result["transferred"] is False

    @pytest.mark.asyncio
    async def test_transfer_supported(self, db_session: AsyncSession, test_call: Call):
        """Should successfully request transfer when supported."""
        context = ToolSecurityContext(
            call_id=str(test_call.id),
            campaign_id=str(test_call.campaign_id),
            contact_id=str(test_call.contact_id),
            organization_id=str(uuid.uuid4()),
            supports_transfer=True  # Provider supports transfer
        )
        tools = create_agent_tools(context, db_session=db_session)
        tool = {t.name: t for t in tools}["transfer_to_human"]

        result = await tool.ainvoke({
            "call_id": str(test_call.id),
            "reason": "Customer requested supervisor",
            "department": "support"
        })

        assert result["status"] == "transferred"
        assert result["transferred"] is True
        assert result["department"] == "support"


class TestGetCallStatus:
    """Tests for get_call_status tool."""

    @pytest.mark.asyncio
    async def test_get_call_status_success(self, db_session: AsyncSession, test_call: Call):
        """Should successfully retrieve call status."""
        context = ToolSecurityContext(
            call_id=str(test_call.id),
            campaign_id=str(test_call.campaign_id),
            contact_id=str(test_call.contact_id),
            organization_id=str(uuid.uuid4())
        )
        tools = create_agent_tools(context, db_session=db_session)
        tool = {t.name: t for t in tools}["get_call_status"]

        result = await tool.ainvoke({"call_id": str(test_call.id)})

        assert result["call_id"] == str(test_call.id)
        assert result["status"] == test_call.status.value
        assert result["provider"] == test_call.provider


class TestToolSchemas:
    """Tests for Pydantic validation schemas."""

    def test_get_contact_details_input_valid(self):
        """Should validate correct input."""
        input_data = GetContactDetailsInput(
            contact_id=str(uuid.uuid4()),
            organization_id=str(uuid.uuid4())
        )
        assert input_data.contact_id is not None

    def test_save_conversation_field_input_sanitizes_field_name(self):
        """Should sanitize field name to remove invalid characters."""
        input_data = SaveConversationFieldInput(
            call_id=str(uuid.uuid4()),
            field_name="budget@#$",
            field_value="$5000",
            confidence_score=0.9
        )
        assert "@" not in input_data.field_name
        assert "#" not in input_data.field_name
        assert "$" not in input_data.field_name

    def test_save_conversation_field_input_invalid_field_name(self):
        """Should reject field name with only invalid characters."""
        with pytest.raises(ValueError, match="Invalid field name"):
            SaveConversationFieldInput(
                call_id=str(uuid.uuid4()),
                field_name="@#$",
                field_value="$5000"
            )

    def test_save_call_result_input_rating_bounds(self):
        """Should enforce rating bounds (1-5)."""
        # Valid rating
        SaveCallResultInput(
            call_id=str(uuid.uuid4()),
            call_outcome="Interested",
            customer_rating=5
        )

        # Invalid rating (too high)
        with pytest.raises(ValueError):
            SaveCallResultInput(
                call_id=str(uuid.uuid4()),
                call_outcome="Interested",
                customer_rating=6
            )

        # Invalid rating (too low)
        with pytest.raises(ValueError):
            SaveCallResultInput(
                call_id=str(uuid.uuid4()),
                call_outcome="Interested",
                customer_rating=0
            )

    def test_schedule_follow_up_input_valid_iso_format(self):
        """Should accept valid ISO 8601 datetime."""
        input_data = ScheduleFollowUpInput(
            call_id=str(uuid.uuid4()),
            contact_id=str(uuid.uuid4()),
            scheduled_iso="2026-10-12T10:00:00Z",
            channel="voice"
        )
        assert input_data.scheduled_iso is not None
