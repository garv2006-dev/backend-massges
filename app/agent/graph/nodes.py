"""Graph Nodes for LangGraph Voice Agent Orchestration."""

import json
import uuid
import re
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from sqlalchemy import select, and_

from app.database import AsyncSessionLocal
from app.models.contact import Contact
from app.models.campaign import Campaign
from app.models.call import Call, CallStatus
from app.models.transcript import Transcript
from app.models.call_event import CallEvent
from app.models.consent_record import ContactConsent, SuppressionRecord
from app.agent.state import ConversationState
from app.agent.tools.security import ToolSecurityContext, ToolSecurityManager
from app.agent.tools.definitions import create_agent_tools
from app.agent.gemini import get_gemini_voice_model, VOICE_AGENT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

async def load_context(state: ConversationState) -> Dict[str, Any]:
    """
    Load authoritative context from PostgreSQL:
    - Contact identity and profile
    - Campaign script and parameters
    - Policy-enforced consent and suppression verification
    """
    call_id = state.get("call_id")
    contact_id = state.get("contact_id")
    campaign_id = state.get("campaign_id")
    org_id = state.get("organization_id")

    updates: Dict[str, Any] = {
        "turn_count": state.get("turn_count", 0),
        "max_turns": state.get("max_turns", 10),
        "tool_call_count": 0,
        "max_tool_iterations": 4,
        "retry_count": state.get("retry_count", 0),
        "extracted_fields": state.get("extracted_fields", {}),
        "tool_results": state.get("tool_results", []),
        "should_end_call": state.get("should_end_call", False),
        "handoff_requested": state.get("handoff_requested", False),
    }

    async with AsyncSessionLocal() as db:
        # 1. Check Call
        if call_id:
            try:
                call_res = await db.execute(select(Call).where(Call.id == uuid.UUID(call_id)))
                call = call_res.scalar_one_or_none()
                if call:
                    updates["call_status"] = call.status.value if hasattr(call.status, "value") else str(call.status)
                    if not contact_id and call.contact_id:
                        contact_id = str(call.contact_id)
                        updates["contact_id"] = contact_id
                    if not campaign_id and call.campaign_id:
                        campaign_id = str(call.campaign_id)
                        updates["campaign_id"] = campaign_id
            except Exception as e:
                logger.warning(f"Error loading call context: {e}")

        # 2. Check Contact
        if contact_id:
            try:
                c_res = await db.execute(select(Contact).where(Contact.id == uuid.UUID(contact_id)))
                contact = c_res.scalar_one_or_none()
                if contact:
                    updates["customer_name"] = contact.name or "Valued Customer"
                    updates["contact_phone"] = contact.phone_number_normalized or contact.phone_number
                    updates["conversation_language"] = contact.language or "English"
            except Exception as e:
                logger.warning(f"Error loading contact context: {e}")

        # 3. Check Campaign
        if campaign_id:
            try:
                camp_res = await db.execute(select(Campaign).where(Campaign.id == uuid.UUID(campaign_id)))
                campaign = camp_res.scalar_one_or_none()
                if campaign:
                    updates["campaign_name"] = campaign.name
                    updates["campaign_prompt"] = campaign.agent_prompt or "Inquire about interest in our services."
                    updates["max_duration_seconds"] = campaign.max_call_duration or 300
                    cfg = campaign.provider_config or {}
                    if not updates.get("conversation_language"):
                        updates["conversation_language"] = cfg.get("language", "English")
            except Exception as e:
                logger.warning(f"Error loading campaign context: {e}")

        # 4. Enforce Verified Consent & Suppression check
        phone = updates.get("contact_phone")
        if phone:
            supp_res = await db.execute(
                select(SuppressionRecord).where(SuppressionRecord.phone_number == phone)
            )
            if supp_res.scalar_one_or_none():
                # Customer is suppressed under policy
                updates["consent_status"] = "opted_out"
                updates["should_end_call"] = True
                updates["agent_response_text"] = "This phone number is on our suppression list. Ending call."
                return updates

            # Check explicit consent record
            if contact_id:
                consent_res = await db.execute(
                    select(ContactConsent).where(ContactConsent.contact_id == uuid.UUID(contact_id))
                )
                consent = consent_res.scalar_one_or_none()
                if consent:
                    updates["consent_status"] = consent.consent_status
                    if consent.consent_status in ["opted_out", "revoked"]:
                        updates["should_end_call"] = True
                        updates["agent_response_text"] = "Call permission has been revoked. Ending call."
                        return updates
                else:
                    updates["consent_status"] = "consented"
            else:
                updates["consent_status"] = "consented"

    return updates


async def process_customer_input(state: ConversationState) -> Dict[str, Any]:
    """
    Processes customer utterance:
    - Increments turn count
    - Enforces duration and turn bounds
    - Detects explicit opt-out phrases and creates suppression record
    - Adds HumanMessage to conversation messages
    """
    user_utterance = state.get("last_user_utterance", "").strip()
    turn_count = state.get("turn_count", 0) + 1
    max_turns = state.get("max_turns", 10)
    elapsed = state.get("elapsed_duration_seconds", 0) + 10  # approximate turn duration
    max_duration = state.get("max_duration_seconds", 300)

    updates: Dict[str, Any] = {
        "turn_count": turn_count,
        "elapsed_duration_seconds": elapsed,
    }

    # Turn limit check
    if turn_count > max_turns or elapsed >= max_duration:
        updates["should_end_call"] = True
        updates["agent_response_text"] = "Thank you so much for your time today. Have a wonderful rest of your day."
        return updates

    # Opt-out detection
    opt_out_keywords = ["stop calling", "do not call", "don't call", "unsubscribe", "remove my number", "opt out"]
    if any(kw in user_utterance.lower() for kw in opt_out_keywords):
        updates["consent_status"] = "opted_out"
        updates["should_end_call"] = True
        updates["call_outcome"] = "Customer Opt-Out"

        # Record suppression in PostgreSQL
        phone = state.get("contact_phone")
        org_id = state.get("organization_id")
        call_id = state.get("call_id")
        if phone:
            async with AsyncSessionLocal() as db:
                try:
                    supp = SuppressionRecord(
                        phone_number=phone,
                        organization_id=uuid.UUID(org_id) if org_id else None,
                        reason="opt_out",
                        source_call_id=uuid.UUID(call_id) if call_id else None,
                        notes=f"Opt-out detected in utterance: '{user_utterance}'"
                    )
                    db.add(supp)
                    await db.commit()
                except Exception as e:
                    logger.warning(f"Failed to record suppression: {e}")

        updates["agent_response_text"] = "I understand completely. We have noted your request and will not call this number again. Goodbye."
        return updates

    # Add message
    messages = list(state.get("messages", []))
    if user_utterance:
        messages.append(HumanMessage(content=user_utterance))
        updates["messages"] = messages

    return updates


async def call_model(state: ConversationState) -> Dict[str, Any]:
    """
    Invokes the Gemini model with bound tools and campaign prompt.
    """
    # Context for tool bindings
    context = ToolSecurityContext(
        call_id=state.get("call_id", ""),
        campaign_id=state.get("campaign_id", ""),
        contact_id=state.get("contact_id", ""),
        organization_id=state.get("organization_id", ""),
        supports_transfer=False
    )
    tools = create_agent_tools(context)
    model = get_gemini_voice_model(tools=tools)

    # Format system prompt
    system_text = VOICE_AGENT_SYSTEM_PROMPT.format(
        company_name=state.get("campaign_name", "Apex Solutions"),
        agent_name="Sarah",
        language=state.get("conversation_language", "English"),
        tone="friendly and professional",
        campaign_prompt=state.get("campaign_prompt", "Help customer and explain services."),
        customer_name=state.get("customer_name", "Valued Customer")
    )

    history = [SystemMessage(content=system_text)]
    history.extend(state.get("messages", []))

    try:
        response = await model.ainvoke(history)
        messages = list(state.get("messages", []))
        messages.append(response)
        return {
            "messages": messages,
            "error_state": None
        }
    except Exception as e:
        logger.error(f"Error invoking Gemini model: {e}")
        return {
            "error_state": str(e)
        }


async def execute_tools(state: ConversationState) -> Dict[str, Any]:
    """
    Executes approved tool calls generated by the model.
    Enforces authorization, input validation, and bounded iterations.
    """
    messages = list(state.get("messages", []))
    last_msg = messages[-1] if messages else None

    if not isinstance(last_msg, AIMessage) or not getattr(last_msg, "tool_calls", None):
        return {}

    tool_call_count = state.get("tool_call_count", 0) + 1
    max_tool_iter = state.get("max_tool_iterations", 4)
    if tool_call_count > max_tool_iter:
        logger.warning("Max tool iterations exceeded; breaking tool loop.")
        return {
            "should_end_call": True,
            "tool_call_count": tool_call_count
        }

    context = ToolSecurityContext(
        call_id=state.get("call_id", ""),
        campaign_id=state.get("campaign_id", ""),
        contact_id=state.get("contact_id", ""),
        organization_id=state.get("organization_id", ""),
        supports_transfer=False
    )
    tools = {t.name: t for t in create_agent_tools(context)}

    tool_results = list(state.get("tool_results", []))
    should_end = state.get("should_end_call", False)
    handoff = state.get("handoff_requested", False)

    for tc in last_msg.tool_calls:
        tool_name = tc.get("name")
        tool_args = tc.get("args", {})
        tool_id = tc.get("id") or str(uuid.uuid4())

        # Authorize tool
        if tool_name not in tools:
            res_content = {"error": f"Tool {tool_name} is not authorized or available."}
        else:
            # Enforce parameters from security context if omitted by model
            if "call_id" in tool_args and not tool_args["call_id"]:
                tool_args["call_id"] = context.call_id
            if "contact_id" in tool_args and not tool_args["contact_id"]:
                tool_args["contact_id"] = context.contact_id
            if "campaign_id" in tool_args and not tool_args["campaign_id"]:
                tool_args["campaign_id"] = context.campaign_id

            try:
                target_tool = tools[tool_name]
                res_content = await target_tool.ainvoke(tool_args)
            except Exception as e:
                logger.error(f"Tool execution exception for {tool_name}: {e}")
                res_content = {"error": str(e)}

        tool_results.append({
            "tool_name": tool_name,
            "args": tool_args,
            "result": res_content,
            "timestamp": datetime.utcnow().isoformat()
        })

        if tool_name == "end_call":
            should_end = True
        elif tool_name == "transfer_to_human":
            if res_content.get("transferred"):
                handoff = True

        messages.append(ToolMessage(
            content=json.dumps(res_content),
            tool_call_id=tool_id
        ))

    return {
        "messages": messages,
        "tool_results": tool_results,
        "tool_call_count": tool_call_count,
        "should_end_call": should_end,
        "handoff_requested": handoff
    }


async def validate_tool_results(state: ConversationState) -> Dict[str, Any]:
    """
    Validates tool execution outputs before responding to caller.
    """
    tool_results = state.get("tool_results", [])
    if not tool_results:
        return {}

    latest = tool_results[-1]
    if "error" in latest.get("result", {}):
        logger.warning(f"Tool execution warning: {latest['tool_name']} returned error.")

    return {}


async def generate_voice_response(state: ConversationState) -> Dict[str, Any]:
    """
    Formats the textual agent response to be crisp, conversational,
    and optimized for text-to-speech output.
    """
    # If a canned/direct text was already formulated (e.g. opt-out or limits)
    direct_text = state.get("agent_response_text")
    if direct_text:
        clean = re.sub(r'[*_#~`\[\]]', '', direct_text).strip()
        return {"agent_response_text": clean}

    # Extract text from latest AIMessage
    messages = state.get("messages", [])
    response_text = ""
    for m in reversed(messages):
        if isinstance(m, AIMessage):
            response_text = m.content
            break

    if not response_text:
        response_text = "Thank you. Is there anything else I can help you with today?"

    # Clean text of markdown, XML, asterisks, brackets
    clean_text = re.sub(r'[*_#~`\[\]<>]', '', response_text)
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()

    return {
        "agent_response_text": clean_text
    }


async def persist_turn(state: ConversationState) -> Dict[str, Any]:
    """
    Persist conversation turn and transcripts to PostgreSQL.
    """
    call_id = state.get("call_id")
    user_utterance = state.get("last_user_utterance")
    agent_response = state.get("agent_response_text")

    if not call_id:
        return {}

    async with AsyncSessionLocal() as db:
        try:
            call_uuid = uuid.UUID(call_id)
            call_res = await db.execute(select(Call).where(Call.id == call_uuid))
            call = call_res.scalar_one_or_none()
            if not call:
                return {}

            # Update call turn count
            call.ai_interactions = state.get("turn_count", 0)

            # Record turn event
            turn_event = CallEvent(
                call_id=call_uuid,
                event_type="dialogue_turn",
                event_data={
                    "turn": state.get("turn_count", 0),
                    "user": user_utterance,
                    "agent": agent_response
                },
                description=f"Turn {state.get('turn_count', 0)} completed"
            )
            db.add(turn_event)

            # Append to transcript
            t_res = await db.execute(select(Transcript).where(Transcript.call_id == call_uuid))
            transcript = t_res.scalar_one_or_none()
            timestamp_str = datetime.utcnow().strftime("%M:%S")
            new_lines = []
            if user_utterance:
                new_lines.append(f"[{timestamp_str}] Customer: {user_utterance}")
            if agent_response:
                new_lines.append(f"[{timestamp_str}] AI Agent: {agent_response}")

            if transcript:
                existing = transcript.full_transcript or ""
                transcript.full_transcript = (existing + "\n" + "\n".join(new_lines)).strip()
                transcript.word_count = len(transcript.full_transcript.split())
            else:
                full_text = "\n".join(new_lines)
                transcript = Transcript(
                    call_id=call_uuid,
                    full_transcript=full_text,
                    word_count=len(full_text.split()),
                    language_detected=state.get("conversation_language", "English")
                )
                db.add(transcript)

            await db.commit()
        except Exception as e:
            logger.error(f"Error persisting turn to DB: {e}")
            await db.rollback()

    return {}


async def finalize_call(state: ConversationState) -> Dict[str, Any]:
    """
    Marks the call record as completed or transferred, updates final stats,
    and sets hangup cause.
    """
    call_id = state.get("call_id")
    if not call_id:
        return {}

    async with AsyncSessionLocal() as db:
        try:
            call_uuid = uuid.UUID(call_id)
            call_res = await db.execute(select(Call).where(Call.id == call_uuid))
            call = call_res.scalar_one_or_none()
            if call:
                if state.get("handoff_requested"):
                    call.status = CallStatus.COMPLETED
                    call.hangup_cause = "Transferred to human agent"
                elif state.get("should_end_call"):
                    call.status = CallStatus.COMPLETED
                    call.hangup_cause = state.get("call_outcome", "Call completed normally")

                call.ended_at = datetime.utcnow()
                call.duration_seconds = state.get("elapsed_duration_seconds", 30)
                await db.commit()
        except Exception as e:
            logger.error(f"Error finalizing call in DB: {e}")

    return {
        "call_status": "completed"
    }


async def handle_error(state: ConversationState) -> Dict[str, Any]:
    """
    Bounded error recovery path.
    Increments retry count, provides polite retry response,
    or terminates if retry bound is reached.
    """
    retry_count = state.get("retry_count", 0) + 1
    max_retries = 3

    if retry_count >= max_retries:
        return {
            "retry_count": retry_count,
            "should_end_call": True,
            "agent_response_text": "I am experiencing technical difficulties at the moment. We will reconnect with you shortly. Thank you."
        }

    return {
        "retry_count": retry_count,
        "agent_response_text": "I apologize, could you please repeat that?"
    }
