"""OpenWA WhatsApp Gateway Webhook & Real-Time AI Messaging Orchestration.

Manages:
1. OpenWA WhatsApp Gateway connection, pairing QR code, and session lifecycle.
2. Direct WhatsApp text message broadcasting and test dispatches.
3. Universal Webhook for inbound customer replies with automated, human-like AI responses.
4. Complete persistence in PostgreSQL `whatsapp_conversations` and `whatsapp_messages` tables.
NO voice calls, NO TTS audio, NO STT required.
"""

import uuid
import json
import logging
import re
from datetime import datetime
from typing import Optional, Dict, Any

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, desc

from app.database import AsyncSessionLocal
from app.models.whatsapp_conversation import WhatsAppConversation
from app.models.whatsapp_message import WhatsAppMessage
from app.models.company_profile import CompanyProfile
from app.services.ai_voice_engine import AIVoiceEngine
from app.integrations.telephony.openwa import OpenWATelephonyProvider

logger = logging.getLogger(__name__)
router = APIRouter()

# Global provider instance
openwa_provider = OpenWATelephonyProvider()


class TestCallRequest(BaseModel):
    phone_number: str = Field(..., description="Destination WhatsApp phone number with country code")
    speech_text: Optional[str] = Field(None, description="Custom message prompt")
    voice: Optional[str] = Field(None, description="Voice identifier (legacy parameter)")


class TestTextMessageRequest(BaseModel):
    phone_number: str = Field(..., description="Destination WhatsApp phone number with country code")
    message_text: str = Field(..., description="WhatsApp text content to send")


@router.get("/openwa/status")
async def get_openwa_gateway_status():
    """
    Check the live status of the OpenWA WhatsApp Gateway.
    Returns gateway reachability, session state, and configuration.
    """
    session_status = await openwa_provider.get_session_status()
    is_connected = session_status.get("status") in ["ready", "CONNECTED", "AUTHENTICATED"]

    return {
        "gateway_url": openwa_provider.base_url,
        "session_id": openwa_provider.session_id,
        "is_connected": is_connected,
        "session_details": session_status,
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/openwa/qr")
async def get_openwa_qr_code():
    """
    Retrieve current WhatsApp QR code from OpenWA for phone pairing.
    """
    qr_data = await openwa_provider.get_session_qr()
    return qr_data


@router.post("/openwa/init-session")
async def init_openwa_session():
    """
    Initialize or restart the WhatsApp session on OpenWA gateway.
    """
    res = await openwa_provider.create_or_start_session()
    return res


@router.post("/openwa/test-call")
async def test_whatsapp_outbound_call(payload: TestCallRequest):
    """
    Dispatches a test WhatsApp message to verify OpenWA connectivity.
    """
    clean_phone = payload.phone_number.strip().replace(" ", "").replace("-", "")
    chat_id = openwa_provider.normalize_phone_to_jid(clean_phone)
    msg_text = payload.speech_text or "Hello! This is a test WhatsApp message from your AI Automation platform via OpenWA."

    try:
        res = await openwa_provider.send_text_message(chat_id=chat_id, text=msg_text)
        return {
            "success": True,
            "chat_id": chat_id,
            "message": msg_text,
            "openwa_result": res,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error in test_whatsapp_outbound_call: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/openwa/send-test-text")
async def send_whatsapp_test_text(payload: TestTextMessageRequest):
    """
    Manual test endpoint to dispatch a pure WhatsApp text message
    via the OpenWA Gateway with live confirmation.
    """
    clean_phone = payload.phone_number.strip().replace(" ", "").replace("-", "")
    chat_id = openwa_provider.normalize_phone_to_jid(clean_phone)
    msg_text = payload.message_text.strip()

    logger.info(f"Dispatching test WhatsApp text message to {chat_id}")
    try:
        res = await openwa_provider.send_text_message(
            chat_id=chat_id,
            text=msg_text
        )
        return {
            "success": True,
            "chat_id": chat_id,
            "phone_number": clean_phone,
            "message": msg_text,
            "openwa_result": res,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to send test WhatsApp text message: {e}")
        return {
            "success": False,
            "error": str(e),
            "phone_number": clean_phone
        }


@router.post("/openwa/webhook")
@router.post("/webhook")
async def handle_openwa_webhook(request: Request):
    """
    Universal webhook endpoint for OpenWA WhatsApp Gateway events.
    Listens for customer text replies, logs them into `whatsapp_conversations` and
    `whatsapp_messages`, and automatically triggers a human-like AI agent response.
    """
    body_bytes = await request.body()
    try:
        payload = json.loads(body_bytes.decode("utf-8"))
    except Exception:
        payload = {}

    event = payload.get("event") or payload.get("type", "unknown")
    session_id = payload.get("sessionId")
    data = payload.get("data", payload)

    logger.info(f"OpenWA Webhook received: event='{event}', sessionId='{session_id}'")

    # -------------------------------------------------------------
    # Inbound Customer Message Handling
    # -------------------------------------------------------------
    if event in ["message.received", "message.create", "message.upsert"]:
        # Ignore messages sent by ourselves
        if data.get("fromMe") is True or data.get("key", {}).get("fromMe") is True:
            return {"status": "ignored", "reason": "outbound_message"}

        sender_jid = data.get("from") or data.get("chatId") or data.get("key", {}).get("remoteJid", "")
        if "@g.us" in sender_jid:
            # Skip group messages
            return {"status": "ignored", "reason": "group_message"}

        clean_phone = re.sub(r"[^\d]", "", sender_jid.split("@")[0])
        user_text = (data.get("body") or data.get("text") or "").strip()

        if not user_text:
            return {"status": "ignored", "reason": "empty_content"}

        logger.info(f"Customer [{clean_phone}] replied on WhatsApp: '{user_text}'")

        async with AsyncSessionLocal() as db:
            # Find or create active WhatsApp conversation thread
            conv_stmt = select(WhatsAppConversation).where(
                WhatsAppConversation.phone_number == clean_phone
            ).order_by(desc(WhatsAppConversation.updated_at))
            conv_res = await db.execute(conv_stmt)
            conv = conv_res.scalars().first()

            if not conv:
                conv = WhatsAppConversation(
                    phone_number=clean_phone,
                    contact_name="WhatsApp Customer",
                    chat_jid=sender_jid,
                    last_message_text=user_text,
                    last_message_at=datetime.utcnow()
                )
                db.add(conv)
                await db.commit()
                await db.refresh(conv)

            # Record customer's incoming message
            cust_msg = WhatsAppMessage(
                conversation_id=conv.id,
                sender="customer",
                direction="inbound",
                message_text=user_text,
                status="received",
                chat_jid=sender_jid,
                ai_generated=False
            )
            db.add(cust_msg)
            await db.commit()

            # Retrieve recent conversation history
            hist_stmt = select(WhatsAppMessage).where(
                WhatsAppMessage.conversation_id == conv.id
            ).order_by(WhatsAppMessage.created_at.asc()).limit(20)
            hist_res = await db.execute(hist_stmt)
            messages = hist_res.scalars().all()

            dialogue_history = []
            for m in messages:
                dialogue_history.append({
                    "speaker": "agent" if m.sender == "agent" else "customer",
                    "text": m.message_text
                })

            # Check company profile for context
            comp_stmt = select(CompanyProfile).order_by(desc(CompanyProfile.created_at)).limit(1)
            comp_res = await db.execute(comp_stmt)
            company_profile = comp_res.scalar_one_or_none()

            provider_config = {}
            if company_profile:
                provider_config = {
                    "company_name": company_profile.name,
                    "tone": "helpful, polite, and professional",
                    "language": "English",
                    "description": company_profile.description or ""
                }

            # Generate natural, human-like AI reply
            agent_reply = await AIVoiceEngine.generate_live_turn(
                campaign_name="WhatsApp Assistant",
                agent_prompt=f"Assist the customer regarding {provider_config.get('company_name', 'our company')}.",
                provider_config=provider_config,
                conversation_history=dialogue_history,
                user_message=user_text,
                contact_name=conv.contact_name or "Valued Customer"
            )

            # Save outbound AI response
            ai_msg = WhatsAppMessage(
                conversation_id=conv.id,
                sender="agent",
                direction="outbound",
                message_text=agent_reply,
                status="sent",
                chat_jid=sender_jid,
                ai_generated=True
            )
            db.add(ai_msg)

            # Update conversation summary
            conv.last_message_text = agent_reply
            conv.last_message_at = datetime.utcnow()
            await db.commit()

            # Deliver pure text reply directly via OpenWA
            try:
                await openwa_provider.send_text_message(
                    chat_id=sender_jid,
                    text=f"🤖 {agent_reply}"
                )
            except Exception as se:
                logger.error(f"Failed to deliver WhatsApp reply via OpenWA: {se}")

        return {"status": "success", "processed": True, "reply": agent_reply}

    # Handle incoming call attempts gracefully by redirecting to WhatsApp chat
    elif event in ["call.received", "call.offer", "call.incoming"]:
        caller_jid = data.get("from") or data.get("chatId") or ""
        if caller_jid:
            try:
                await openwa_provider.send_text_message(
                    chat_id=caller_jid,
                    text="Hello! Thank you for reaching out. Our team is available right here on WhatsApp chat. How can we assist you today?"
                )
            except Exception as se:
                logger.warning(f"Could not send call fallback message: {se}")
        return {"status": "success", "event": event}

    return {"status": "received", "event": event}
