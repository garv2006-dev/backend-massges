"""OpenWA WhatsApp Telephony Webhook & Real-Time Conversation Orchestration.

Replaces legacy Twilio telephony with OpenWA (Open Source WhatsApp API Gateway).
Handles:
1. Company calls User (Outbound AI Voice Campaigns, WhatsApp Voice Notes, and Calls)
2. User calls Company (Inbound WhatsApp Calls, Live Voice Notes, Multi-Turn AI Dialogues)
3. Direct Gateway Status & QR Code authentication for WhatsApp Web linking.
"""

import uuid
import json
import base64
import asyncio
import logging
import re
from datetime import datetime
from typing import Optional, Dict, Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Response, Request, HTTPException, Body
from pydantic import BaseModel, Field
from sqlalchemy import select, desc

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.call import Call, CallStatus, CallDirection
from app.models.transcript import Transcript
from app.models.campaign_contact import CampaignContact, CampaignContactStatus
from app.agent.service import VoiceAgentOrchestrator
from app.agent.audio_pipeline import AudioPipelineManager
from app.integrations.telephony.openwa import OpenWATelephonyProvider

logger = logging.getLogger(__name__)
router = APIRouter()

# Global provider instance
openwa_provider = OpenWATelephonyProvider()


class TestCallRequest(BaseModel):
    phone_number: str = Field(..., description="Destination phone number with country code, e.g. +919876543210")
    speech_text: Optional[str] = Field(None, description="Custom voice greeting / prompt")
    voice: Optional[str] = Field("en-IN-NeerjaNeural", description="TTS voice identifier")


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
    Manual test endpoint to dispatch an outbound WhatsApp AI voice note / call
    to verify OpenWA integration.
    """
    try:
        async with AsyncSessionLocal() as db:
            # Create a test call record
            call_rec = Call(
                phone_number=payload.phone_number,
                direction=CallDirection.OUTBOUND,
                status=CallStatus.IN_PROGRESS,
                started_at=datetime.utcnow(),
                provider="openwa"
            )
            db.add(call_rec)
            await db.commit()
            await db.refresh(call_rec)

            speech = payload.speech_text or "Hello! This is a test AI voice call from your Antigravity VoiceAI platform via OpenWA."
            
            res = await openwa_provider.create_call(
                phone_number=payload.phone_number,
                speech_text=speech,
                voice=payload.voice or "en-IN-NeerjaNeural",
                metadata={"call_id": str(call_rec.id)}
            )

            call_rec.provider_call_id = res.get("provider_call_id")
            
            # Save initial transcript
            tr = Transcript(
                call_id=call_rec.id,
                full_transcript=f"[00:00] AI Agent: {speech}",
                word_count=len(speech.split()),
                language_detected="en-IN"
            )
            db.add(tr)
            await db.commit()

            return {
                "success": True,
                "call_id": str(call_rec.id),
                "openwa_response": res
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
    Handles:
    - Inbound WhatsApp Calls (User calls company) -> triggers AI voice greeting
    - Inbound WhatsApp Voice Notes & Messages -> executes LangGraph conversation turn & replies with AI voice note
    - Call status changes (call.accepted, call.rejected, call.ended)
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
    # CASE 1: Inbound Call Event (User calls Company)
    # -------------------------------------------------------------
    if event in ["call.received", "call.offer", "call.incoming"]:
        caller_jid = data.get("from") or data.get("chatId") or ""
        clean_phone = re.sub(r"[^\d]", "", caller_jid.split("@")[0])
        call_id_remote = data.get("id") or str(uuid.uuid4())
        
        logger.info(f"Inbound WhatsApp Call detected from {clean_phone} (JID: {caller_jid})")

        async with AsyncSessionLocal() as db:
            call_rec = Call(
                phone_number=clean_phone or "WhatsApp Caller",
                direction=CallDirection.INBOUND,
                status=CallStatus.IN_PROGRESS,
                started_at=datetime.utcnow(),
                provider="openwa",
                provider_call_id=str(call_id_remote)
            )
            db.add(call_rec)
            await db.commit()
            await db.refresh(call_rec)

            greeting = "Hello! Thank you for calling our company on WhatsApp. I am your AI voice assistant. How may I assist you today?"

            # Record greeting in Transcript
            timestamp_str = datetime.utcnow().strftime("%M:%S")
            tr = Transcript(
                call_id=call_rec.id,
                full_transcript=f"[{timestamp_str}] AI Agent: {greeting}",
                word_count=len(greeting.split()),
                language_detected="en-IN"
            )
            db.add(tr)
            await db.commit()

            # Respond with WhatsApp Voice Note (PTT)
            try:
                audio_bytes = await openwa_provider.synthesize_speech_bytes(greeting)
                await openwa_provider.send_voice_audio(
                    chat_id=caller_jid,
                    audio_bytes=audio_bytes,
                    ptt=True
                )
                await openwa_provider.send_text_message(
                    chat_id=caller_jid,
                    text=f"📞 AI Voice Assistant Connected!\n\n\"{greeting}\"\n\n💬 Please send a voice note or message to speak with me."
                )
            except Exception as se:
                logger.error(f"Failed to send inbound call greeting via OpenWA: {se}")

        return {"status": "success", "event": event, "call_id": str(call_rec.id)}

    # -------------------------------------------------------------
    # CASE 2: Call Ended / Rejected / Accepted Status Updates
    # -------------------------------------------------------------
    elif event in ["call.ended", "call.rejected", "call.missed", "call.accepted"]:
        call_id_remote = data.get("id")
        duration = data.get("duration", 0)
        logger.info(f"Call status event: {event} for remote call {call_id_remote}")

        if call_id_remote:
            async with AsyncSessionLocal() as db:
                stmt = select(Call).where(Call.provider_call_id == str(call_id_remote)).order_by(desc(Call.started_at))
                res = await db.execute(stmt)
                call_rec = res.scalars().first()
                if call_rec:
                    if event in ["call.ended", "call.accepted"]:
                        call_rec.status = CallStatus.COMPLETED
                    elif event == "call.rejected":
                        call_rec.status = CallStatus.REJECTED
                    elif event == "call.missed":
                        call_rec.status = CallStatus.NO_ANSWER
                    
                    call_rec.ended_at = datetime.utcnow()
                    if duration:
                        call_rec.duration_seconds = int(duration)
                    await db.commit()

        return {"status": "success", "event": event}

    # -------------------------------------------------------------
    # CASE 3: Inbound Customer Message / Voice Note
    # -------------------------------------------------------------
    elif event in ["message.received", "message.create", "message.upsert"]:
        # Ignore messages sent by ourselves
        if data.get("fromMe") is True or data.get("key", {}).get("fromMe") is True:
            return {"status": "ignored", "reason": "outbound_message"}

        sender_jid = data.get("from") or data.get("chatId") or data.get("key", {}).get("remoteJid", "")
        if "@g.us" in sender_jid:
            # Skip group messages for 1-on-1 telephony
            return {"status": "ignored", "reason": "group_message"}

        clean_phone = re.sub(r"[^\d]", "", sender_jid.split("@")[0])
        msg_type = data.get("type", "chat")
        user_text = (data.get("body") or data.get("text") or "").strip()

        # If user sent a voice note or audio without text body
        if msg_type in ["audio", "voice", "ptt"] and not user_text:
            user_text = "I received your voice message. How can I help you?"

        if not user_text:
            return {"status": "ignored", "reason": "empty_content"}

        logger.info(f"Customer [{clean_phone}] spoke/messaged: '{user_text}'")

        # Find or create active call session for this customer
        async with AsyncSessionLocal() as db:
            stmt = select(Call).where(
                Call.phone_number == clean_phone,
                Call.status == CallStatus.IN_PROGRESS
            ).order_by(desc(Call.started_at))
            res = await db.execute(stmt)
            call_rec = res.scalars().first()

            if not call_rec:
                # Create a new inbound call session
                call_rec = Call(
                    phone_number=clean_phone,
                    direction=CallDirection.INBOUND,
                    status=CallStatus.IN_PROGRESS,
                    started_at=datetime.utcnow(),
                    provider="openwa"
                )
                db.add(call_rec)
                await db.commit()
                await db.refresh(call_rec)

            call_id_str = str(call_rec.id)

            # Process AI Turn via LangGraph Orchestrator
            try:
                agent_result = await VoiceAgentOrchestrator.process_turn(
                    call_id=call_id_str,
                    user_message=user_text
                )
                agent_reply = agent_result.get("agent_response") or "Thank you for letting me know. How else may I assist you?"
                should_end = agent_result.get("should_end_call", False)
            except Exception as ae:
                logger.error(f"Error in VoiceAgentOrchestrator turn: {ae}")
                agent_reply = "I understand. Is there anything else you would like to know?"
                should_end = False

            # Update PostgreSQL Transcript
            c_uuid = call_rec.id
            t_stmt = select(Transcript).where(Transcript.call_id == c_uuid)
            t_res = await db.execute(t_stmt)
            tr = t_res.scalar_one_or_none()
            timestamp_str = datetime.utcnow().strftime("%M:%S")
            new_lines = f"[{timestamp_str}] Customer: {user_text}\n[{timestamp_str}] AI Agent: {agent_reply}"

            if tr:
                tr.full_transcript = (tr.full_transcript or "") + "\n" + new_lines
                tr.word_count = len(tr.full_transcript.split())
            else:
                tr = Transcript(
                    call_id=c_uuid,
                    full_transcript=new_lines,
                    word_count=len(new_lines.split()),
                    language_detected="en-IN"
                )
                db.add(tr)

            call_rec.ai_interactions = (call_rec.ai_interactions or 0) + 1

            if should_end or "goodbye" in user_text.lower() or "bye" in user_text.lower():
                call_rec.status = CallStatus.COMPLETED
                call_rec.ended_at = datetime.utcnow()

            await db.commit()

            # Synthesize and send AI Voice Note response back to WhatsApp
            try:
                audio_bytes = await openwa_provider.synthesize_speech_bytes(agent_reply)
                await openwa_provider.send_voice_audio(
                    chat_id=sender_jid,
                    audio_bytes=audio_bytes,
                    ptt=True
                )
                # Also send text reply for complete accessibility
                await openwa_provider.send_text_message(
                    chat_id=sender_jid,
                    text=f"🤖 AI Voice Assistant:\n{agent_reply}"
                )
            except Exception as se:
                logger.error(f"Error sending WhatsApp voice reply: {se}")

        return {"status": "success", "processed_turn": True, "reply": agent_reply}

    return {"status": "received", "event": event}
