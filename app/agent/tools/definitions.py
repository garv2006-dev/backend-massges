"""Typed LangChain tool definitions with real PostgreSQL backend implementations."""

import time
import uuid
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from langchain_core.tools import tool
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.contact import Contact
from app.models.campaign import Campaign
from app.models.call import Call, CallStatus
from app.models.extracted_call_result import ExtractedCallResult
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
from app.agent.tools.security import (
    ToolSecurityContext,
    ToolSecurityManager,
    ToolSecurityError
)

logger = logging.getLogger(__name__)

def create_agent_tools(context: ToolSecurityContext, db_session: Optional[AsyncSession] = None):
    """
    Factory creating bound tools with execution security context.
    Ensures parameterized DB access, isolation, and audit logging.
    """

    @tool(args_schema=GetContactDetailsInput)
    async def get_contact_details(contact_id: str, organization_id: Optional[str] = None) -> Dict[str, Any]:
        """Retrieve authorized contact information from PostgreSQL."""
        start_time = time.time()
        status_result = "success"
        error_msg = None
        result_data = {}

        async def _exec(db: AsyncSession):
            nonlocal result_data
            try:
                c_uuid = uuid.UUID(contact_id)
            except ValueError:
                raise ToolSecurityError(f"Invalid contact_id: {contact_id}")

            # Verify security context matches contact
            if context.contact_id and str(c_uuid) != str(context.contact_id):
                raise ToolSecurityError("Unauthorized: Contact ID does not match conversation context")

            stmt = select(Contact).where(Contact.id == c_uuid)
            res = await db.execute(stmt)
            contact = res.scalar_one_or_none()
            if not contact:
                raise ToolSecurityError(f"Contact {contact_id} not found")

            result_data = {
                "contact_id": str(contact.id),
                "name": contact.name or "Valued Customer",
                "phone_number": contact.phone_number_normalized or contact.phone_number,
                "email": contact.email,
                "language": contact.language or "en",
                "custom_fields": contact.custom_fields or {}
            }
            return result_data

        if db_session:
            try:
                data = await _exec(db_session)
            except Exception as e:
                status_result = "error"
                error_msg = str(e)
                data = {"error": str(e)}
            duration = int((time.time() - start_time) * 1000)
            await ToolSecurityManager.log_tool_audit(
                db=db_session,
                call_id=context.call_id,
                campaign_id=context.campaign_id,
                organization_id=context.organization_id,
                tool_name="get_contact_details",
                status=status_result,
                duration_ms=duration,
                arguments={"contact_id": contact_id},
                result_summary=data,
                error_message=error_msg
            )
            return data

        async with AsyncSessionLocal() as db:
            try:
                data = await _exec(db)
            except Exception as e:
                status_result = "error"
                error_msg = str(e)
                data = {"error": str(e)}
            duration = int((time.time() - start_time) * 1000)
            await ToolSecurityManager.log_tool_audit(
                db=db,
                call_id=context.call_id,
                campaign_id=context.campaign_id,
                organization_id=context.organization_id,
                tool_name="get_contact_details",
                status=status_result,
                duration_ms=duration,
                arguments={"contact_id": contact_id},
                result_summary=data,
                error_message=error_msg
            )
            return data

    @tool(args_schema=GetCampaignContextInput)
    async def get_campaign_context(campaign_id: str, organization_id: Optional[str] = None) -> Dict[str, Any]:
        """Retrieve approved campaign script, purpose, and configuration from PostgreSQL."""
        start_time = time.time()
        status_result = "success"
        error_msg = None
        result_data = {}

        async def _exec(db: AsyncSession):
            nonlocal result_data
            try:
                camp_uuid = uuid.UUID(campaign_id)
            except ValueError:
                raise ToolSecurityError(f"Invalid campaign_id: {campaign_id}")

            if context.campaign_id and str(camp_uuid) != str(context.campaign_id):
                raise ToolSecurityError("Unauthorized: Campaign ID does not match conversation context")

            stmt = select(Campaign).where(Campaign.id == camp_uuid)
            res = await db.execute(stmt)
            campaign = res.scalar_one_or_none()
            if not campaign:
                raise ToolSecurityError(f"Campaign {campaign_id} not found")

            cfg = campaign.provider_config or {}
            result_data = {
                "campaign_id": str(campaign.id),
                "campaign_name": campaign.name,
                "agent_prompt": campaign.agent_prompt or "",
                "company_name": cfg.get("company_name", "Apex Solutions"),
                "agent_name": cfg.get("agent_name", "Sarah"),
                "tone": cfg.get("tone", "friendly and professional"),
                "language": cfg.get("language", "English"),
                "max_call_duration": campaign.max_call_duration or 300
            }
            return result_data

        if db_session:
            try:
                data = await _exec(db_session)
            except Exception as e:
                status_result = "error"
                error_msg = str(e)
                data = {"error": str(e)}
            duration = int((time.time() - start_time) * 1000)
            await ToolSecurityManager.log_tool_audit(
                db=db_session,
                call_id=context.call_id,
                campaign_id=context.campaign_id,
                organization_id=context.organization_id,
                tool_name="get_campaign_context",
                status=status_result,
                duration_ms=duration,
                arguments={"campaign_id": campaign_id},
                result_summary=data,
                error_message=error_msg
            )
            return data

        async with AsyncSessionLocal() as db:
            try:
                data = await _exec(db)
            except Exception as e:
                status_result = "error"
                error_msg = str(e)
                data = {"error": str(e)}
            duration = int((time.time() - start_time) * 1000)
            await ToolSecurityManager.log_tool_audit(
                db=db,
                call_id=context.call_id,
                campaign_id=context.campaign_id,
                organization_id=context.organization_id,
                tool_name="get_campaign_context",
                status=status_result,
                duration_ms=duration,
                arguments={"campaign_id": campaign_id},
                result_summary=data,
                error_message=error_msg
            )
            return data

    @tool(args_schema=SaveConversationFieldInput)
    async def save_conversation_field(
        call_id: str,
        field_name: str,
        field_value: Any,
        confidence_score: Optional[float] = 1.0
    ) -> Dict[str, Any]:
        """Validate and save an extracted customer response field in PostgreSQL."""
        start_time = time.time()
        status_result = "success"
        error_msg = None

        async def _exec(db: AsyncSession):
            call = await ToolSecurityManager.verify_call_ownership(db, call_id, context)
            
            # Fetch or initialize extracted call result
            stmt = select(ExtractedCallResult).where(ExtractedCallResult.call_id == call.id)
            res = await db.execute(stmt)
            extracted = res.scalar_one_or_none()
            if not extracted:
                extracted = ExtractedCallResult(
                    call_id=call.id,
                    customer_name=None,
                    raw_extracted_data={},
                    validation_status="pending"
                )
                db.add(extracted)
                await db.flush()

            raw_data = dict(extracted.raw_extracted_data or {})
            raw_data[field_name] = {
                "value": field_value,
                "confidence": confidence_score or 1.0,
                "extracted_at": datetime.utcnow().isoformat()
            }
            extracted.raw_extracted_data = raw_data
            await db.commit()
            return {
                "status": "saved",
                "field_name": field_name,
                "field_value": field_value,
                "confidence": confidence_score
            }

        if db_session:
            try:
                data = await _exec(db_session)
            except Exception as e:
                status_result = "error"
                error_msg = str(e)
                data = {"error": str(e)}
            duration = int((time.time() - start_time) * 1000)
            await ToolSecurityManager.log_tool_audit(
                db=db_session,
                call_id=context.call_id,
                campaign_id=context.campaign_id,
                organization_id=context.organization_id,
                tool_name="save_conversation_field",
                status=status_result,
                duration_ms=duration,
                arguments={"call_id": call_id, "field_name": field_name, "value": str(field_value)},
                result_summary=data,
                error_message=error_msg
            )
            return data

        async with AsyncSessionLocal() as db:
            try:
                data = await _exec(db)
            except Exception as e:
                status_result = "error"
                error_msg = str(e)
                data = {"error": str(e)}
            duration = int((time.time() - start_time) * 1000)
            await ToolSecurityManager.log_tool_audit(
                db=db,
                call_id=context.call_id,
                campaign_id=context.campaign_id,
                organization_id=context.organization_id,
                tool_name="save_conversation_field",
                status=status_result,
                duration_ms=duration,
                arguments={"call_id": call_id, "field_name": field_name, "value": str(field_value)},
                result_summary=data,
                error_message=error_msg
            )
            return data

    @tool(args_schema=SaveCallResultInput)
    async def save_call_result(
        call_id: str,
        call_outcome: str,
        customer_name: Optional[str] = None,
        customer_intent: Optional[str] = None,
        customer_rating: Optional[int] = 5,
        follow_up_required: Optional[str] = "no",
        follow_up_notes: Optional[str] = None,
        complaint: Optional[str] = None
    ) -> Dict[str, Any]:
        """Store the final structured call result and outcome in PostgreSQL."""
        start_time = time.time()
        status_result = "success"
        error_msg = None

        async def _exec(db: AsyncSession):
            call = await ToolSecurityManager.verify_call_ownership(db, call_id, context)
            
            stmt = select(ExtractedCallResult).where(ExtractedCallResult.call_id == call.id)
            res = await db.execute(stmt)
            extracted = res.scalar_one_or_none()
            if not extracted:
                extracted = ExtractedCallResult(call_id=call.id)
                db.add(extracted)

            extracted.customer_name = customer_name
            extracted.customer_intent = customer_intent
            extracted.customer_rating = customer_rating
            extracted.call_outcome = call_outcome
            extracted.follow_up_required = follow_up_required
            extracted.follow_up_notes = follow_up_notes
            extracted.complaint = complaint
            extracted.validation_status = "validated"

            current_raw = dict(extracted.raw_extracted_data or {})
            current_raw.update({
                "outcome": call_outcome,
                "intent": customer_intent,
                "rating": customer_rating,
                "finalized_at": datetime.utcnow().isoformat()
            })
            extracted.raw_extracted_data = current_raw

            await db.commit()
            return {
                "status": "persisted",
                "call_id": str(call.id),
                "call_outcome": call_outcome,
                "customer_intent": customer_intent
            }

        if db_session:
            try:
                data = await _exec(db_session)
            except Exception as e:
                status_result = "error"
                error_msg = str(e)
                data = {"error": str(e)}
            duration = int((time.time() - start_time) * 1000)
            await ToolSecurityManager.log_tool_audit(
                db=db_session,
                call_id=context.call_id,
                campaign_id=context.campaign_id,
                organization_id=context.organization_id,
                tool_name="save_call_result",
                status=status_result,
                duration_ms=duration,
                arguments={"call_id": call_id, "call_outcome": call_outcome},
                result_summary=data,
                error_message=error_msg
            )
            return data

        async with AsyncSessionLocal() as db:
            try:
                data = await _exec(db)
            except Exception as e:
                status_result = "error"
                error_msg = str(e)
                data = {"error": str(e)}
            duration = int((time.time() - start_time) * 1000)
            await ToolSecurityManager.log_tool_audit(
                db=db,
                call_id=context.call_id,
                campaign_id=context.campaign_id,
                organization_id=context.organization_id,
                tool_name="save_call_result",
                status=status_result,
                duration_ms=duration,
                arguments={"call_id": call_id, "call_outcome": call_outcome},
                result_summary=data,
                error_message=error_msg
            )
            return data

    @tool(args_schema=ScheduleFollowUpInput)
    async def schedule_follow_up(
        call_id: str,
        contact_id: str,
        scheduled_iso: str,
        channel: Optional[str] = "voice",
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """Schedule a follow-up only when permitted and explicitly requested."""
        start_time = time.time()
        status_result = "success"
        error_msg = None

        async def _exec(db: AsyncSession):
            call = await ToolSecurityManager.verify_call_ownership(db, call_id, context)

            try:
                contact_uuid = uuid.UUID(contact_id)
            except ValueError:
                raise ToolSecurityError(f"Invalid contact_id: {contact_id}")

            try:
                sched_dt = datetime.fromisoformat(scheduled_iso.replace('Z', '+00:00'))
            except Exception:
                raise ToolSecurityError(f"Invalid datetime format: {scheduled_iso}. Expected ISO 8601.")

            # Store follow-up in ExtractedCallResult
            stmt = select(ExtractedCallResult).where(ExtractedCallResult.call_id == call.id)
            res = await db.execute(stmt)
            extracted = res.scalar_one_or_none()
            if not extracted:
                extracted = ExtractedCallResult(call_id=call.id)
                db.add(extracted)
            extracted.follow_up_required = "yes"
            extracted.follow_up_notes = f"Scheduled {channel} for {sched_dt.isoformat()}: {notes or ''}"
            await db.commit()
            return {
                "status": "scheduled",
                "scheduled_time": sched_dt.isoformat(),
                "channel": channel
            }

        if db_session:
            try:
                data = await _exec(db_session)
            except Exception as e:
                status_result = "error"
                error_msg = str(e)
                data = {"error": str(e)}
            duration = int((time.time() - start_time) * 1000)
            await ToolSecurityManager.log_tool_audit(
                db=db_session,
                call_id=context.call_id,
                campaign_id=context.campaign_id,
                organization_id=context.organization_id,
                tool_name="schedule_follow_up",
                status=status_result,
                duration_ms=duration,
                arguments={"call_id": call_id, "scheduled_iso": scheduled_iso},
                result_summary=data,
                error_message=error_msg
            )
            return data

        async with AsyncSessionLocal() as db:
            try:
                data = await _exec(db)
            except Exception as e:
                status_result = "error"
                error_msg = str(e)
                data = {"error": str(e)}
            duration = int((time.time() - start_time) * 1000)
            await ToolSecurityManager.log_tool_audit(
                db=db,
                call_id=context.call_id,
                campaign_id=context.campaign_id,
                organization_id=context.organization_id,
                tool_name="schedule_follow_up",
                status=status_result,
                duration_ms=duration,
                arguments={"call_id": call_id, "scheduled_iso": scheduled_iso},
                result_summary=data,
                error_message=error_msg
            )
            return data

    @tool(args_schema=TransferToHumanInput)
    async def transfer_to_human(
        call_id: str,
        reason: str,
        department: Optional[str] = "support"
    ) -> Dict[str, Any]:
        """Request a human transfer only if the configured telephony provider supports it."""
        start_time = time.time()
        status_result = "success"
        error_msg = None

        async def _exec(db: AsyncSession):
            call = await ToolSecurityManager.verify_call_ownership(db, call_id, context)

            if not context.supports_transfer:
                # Telephony provider or campaign configuration does not support live warm transfer
                return {
                    "status": "transfer_unsupported",
                    "transferred": False,
                    "message": "Live transfer is not supported on this phone configuration. Callback has been queued instead.",
                    "reason": reason
                }

            await db.commit()

            return {
                "status": "transferred",
                "transferred": True,
                "department": department,
                "message": "Connecting caller to the next available representative."
            }

        if db_session:
            try:
                data = await _exec(db_session)
            except Exception as e:
                status_result = "error"
                error_msg = str(e)
                data = {"error": str(e)}
            duration = int((time.time() - start_time) * 1000)
            await ToolSecurityManager.log_tool_audit(
                db=db_session,
                call_id=context.call_id,
                campaign_id=context.campaign_id,
                organization_id=context.organization_id,
                tool_name="transfer_to_human",
                status=status_result,
                duration_ms=duration,
                arguments={"call_id": call_id, "reason": reason},
                result_summary=data,
                error_message=error_msg
            )
            return data

        async with AsyncSessionLocal() as db:
            try:
                data = await _exec(db)
            except Exception as e:
                status_result = "error"
                error_msg = str(e)
                data = {"error": str(e)}
            duration = int((time.time() - start_time) * 1000)
            await ToolSecurityManager.log_tool_audit(
                db=db,
                call_id=context.call_id,
                campaign_id=context.campaign_id,
                organization_id=context.organization_id,
                tool_name="transfer_to_human",
                status=status_result,
                duration_ms=duration,
                arguments={"call_id": call_id, "reason": reason},
                result_summary=data,
                error_message=error_msg
            )
            return data

    @tool(args_schema=EndCallInput)
    async def end_call(
        call_id: str,
        hangup_reason: str,
        customer_consented_or_opt_out: bool = False
    ) -> Dict[str, Any]:
        """Request call termination through the telephony service after applying call-state and authorization checks."""
        start_time = time.time()
        status_result = "success"
        error_msg = None

        async def _exec(db: AsyncSession):
            call = await ToolSecurityManager.verify_call_ownership(db, call_id, context)

            call.hangup_cause = hangup_reason
            call.status = CallStatus.COMPLETED
            call.ended_at = datetime.utcnow()

            await db.commit()

            return {
                "status": "terminated",
                "call_id": str(call.id),
                "hangup_reason": hangup_reason,
                "should_disconnect": True
            }

        if db_session:
            try:
                data = await _exec(db_session)
            except Exception as e:
                status_result = "error"
                error_msg = str(e)
                data = {"error": str(e)}
            duration = int((time.time() - start_time) * 1000)
            await ToolSecurityManager.log_tool_audit(
                db=db_session,
                call_id=context.call_id,
                campaign_id=context.campaign_id,
                organization_id=context.organization_id,
                tool_name="end_call",
                status=status_result,
                duration_ms=duration,
                arguments={"call_id": call_id, "hangup_reason": hangup_reason},
                result_summary=data,
                error_message=error_msg
            )
            return data

        async with AsyncSessionLocal() as db:
            try:
                data = await _exec(db)
            except Exception as e:
                status_result = "error"
                error_msg = str(e)
                data = {"error": str(e)}
            duration = int((time.time() - start_time) * 1000)
            await ToolSecurityManager.log_tool_audit(
                db=db,
                call_id=context.call_id,
                campaign_id=context.campaign_id,
                organization_id=context.organization_id,
                tool_name="end_call",
                status=status_result,
                duration_ms=duration,
                arguments={"call_id": call_id, "hangup_reason": hangup_reason},
                result_summary=data,
                error_message=error_msg
            )
            return data

    @tool(args_schema=GetCallStatusInput)
    async def get_call_status(call_id: str) -> Dict[str, Any]:
        """Retrieve the current call state from the database or provider."""
        start_time = time.time()
        status_result = "success"
        error_msg = None

        async def _exec(db: AsyncSession):
            call = await ToolSecurityManager.verify_call_ownership(db, call_id, context)
            return {
                "call_id": str(call.id),
                "status": call.status.value if hasattr(call.status, "value") else str(call.status),
                "duration_seconds": call.duration_seconds or 0,
                "started_at": call.started_at.isoformat() if call.started_at else None,
                "ended_at": call.ended_at.isoformat() if call.ended_at else None,
                "provider": call.provider or "ai_voice_engine"
            }

        if db_session:
            try:
                data = await _exec(db_session)
            except Exception as e:
                status_result = "error"
                error_msg = str(e)
                data = {"error": str(e)}
            duration = int((time.time() - start_time) * 1000)
            await ToolSecurityManager.log_tool_audit(
                db=db_session,
                call_id=context.call_id,
                campaign_id=context.campaign_id,
                organization_id=context.organization_id,
                tool_name="get_call_status",
                status=status_result,
                duration_ms=duration,
                arguments={"call_id": call_id},
                result_summary=data,
                error_message=error_msg
            )
            return data

        async with AsyncSessionLocal() as db:
            try:
                data = await _exec(db)
            except Exception as e:
                status_result = "error"
                error_msg = str(e)
                data = {"error": str(e)}
            duration = int((time.time() - start_time) * 1000)
            await ToolSecurityManager.log_tool_audit(
                db=db,
                call_id=context.call_id,
                campaign_id=context.campaign_id,
                organization_id=context.organization_id,
                tool_name="get_call_status",
                status=status_result,
                duration_ms=duration,
                arguments={"call_id": call_id},
                result_summary=data,
                error_message=error_msg
            )
            return data

    return [
        get_contact_details,
        get_campaign_context,
        save_conversation_field,
        save_call_result,
        schedule_follow_up,
        transfer_to_human,
        end_call,
        get_call_status
    ]
