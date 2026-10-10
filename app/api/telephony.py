"""Telephony Webhook & Real-Time Conversation Orchestration.

Twilio handles the telecom voice carrier connection and speech capture.
The AI Agent (LangGraph + Gemini + PostgreSQL) processes all intelligence,
tool calling, conversation state, and generates dynamic voice responses.
"""

import uuid
import json
import base64
import asyncio
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Response, Request
from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.call import Call, CallStatus
from app.models.transcript import Transcript
from app.models.campaign_contact import CampaignContact, CampaignContactStatus
from app.agent.service import VoiceAgentOrchestrator
from app.agent.audio_pipeline import AudioPipelineManager

logger = logging.getLogger(__name__)
router = APIRouter()

@router.api_route("/twiml/{call_id}", methods=["GET", "POST"])
async def get_streaming_twiml(call_id: str, request: Request):
    """
    Initial TwiML instruction when a call connects.
    Greets the customer and immediately activates speech listening (<Gather>),
    allowing the user and AI to converse back and forth naturally.
    """
    host = settings.PUBLIC_WEBHOOK_URL or str(request.base_url).rstrip('/')
    host = host.strip().rstrip('/')
    action_url = f"{host}/api/telephony/respond/{call_id}"

    twiml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Pause length="1"/>
    <Gather input="speech" action="{action_url}" method="POST" speechTimeout="auto" language="en-IN" timeout="5">
        <Say voice="Polly.Aditi" language="en-IN">Hello! This is your AI voice assistant calling. How may I help you today?</Say>
    </Gather>
    <Redirect method="POST">{action_url}?timeout=true</Redirect>
</Response>"""
    return Response(content=twiml_content, media_type="application/xml")


@router.api_route("/respond/{call_id}", methods=["GET", "POST"])
async def handle_caller_speech(call_id: str, request: Request):
    """
    Processes real spoken words from the caller.
    Executes LangGraph + Gemini conversation turn, saves transcript,
    and speaks back to the user on the phone.
    """
    form_data = await request.form()
    speech_result = form_data.get("SpeechResult")
    is_timeout = request.query_params.get("timeout") == "true" or not speech_result

    host = settings.PUBLIC_WEBHOOK_URL or str(request.base_url).rstrip('/')
    host = host.strip().rstrip('/')
    action_url = f"{host}/api/telephony/respond/{call_id}"

    # If caller was silent or timeout occurred
    if is_timeout and not speech_result:
        twiml_prompt = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech" action="{action_url}" method="POST" speechTimeout="auto" language="en-IN" timeout="5">
        <Say voice="Polly.Aditi" language="en-IN">I am listening. Please go ahead and tell me how I can help you.</Say>
    </Gather>
    <Say voice="Polly.Aditi" language="en-IN">Thank you for your time. Have a wonderful day. Goodbye!</Say>
    <Hangup/>
</Response>"""
        return Response(content=twiml_prompt, media_type="application/xml")

    user_utterance = str(speech_result).strip()
    logger.info(f"Caller [{call_id}] spoke: '{user_utterance}'")

    # Run AI LangGraph + Gemini Conversation Turn
    try:
        agent_result = await VoiceAgentOrchestrator.process_turn(
            call_id=call_id,
            user_message=user_utterance
        )
        agent_reply = agent_result.get("agent_response") or "Thank you for sharing that. How else can I assist you?"
        should_end = agent_result.get("should_end_call", False)
    except Exception as e:
        logger.error(f"Error in VoiceAgentOrchestrator turn for call {call_id}: {e}")
        agent_reply = "I understand. Is there anything else you would like to know?"
        should_end = False

    # Clean response text for Polly voice synthesis
    clean_reply = agent_reply.replace('"', '').replace("'", "").replace("<", "").replace(">", "").strip()
    if len(clean_reply) > 400:
        clean_reply = clean_reply[:397] + "..."

    # Save real conversation turn to PostgreSQL Transcript
    async with AsyncSessionLocal() as db:
        try:
            c_uuid = uuid.UUID(call_id)
            t_stmt = select(Transcript).where(Transcript.call_id == c_uuid)
            t_res = await db.execute(t_stmt)
            tr = t_res.scalar_one_or_none()
            timestamp_str = datetime.utcnow().strftime("%M:%S")
            new_lines = f"[{timestamp_str}] Customer: {user_utterance}\n[{timestamp_str}] AI Agent: {clean_reply}"

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
            await db.commit()
        except Exception as te:
            logger.warning(f"Could not persist live transcript for call {call_id}: {te}")

    # Check if conversation should end or continue
    if should_end or "goodbye" in user_utterance.lower() or "bye" in user_utterance.lower():
        twiml_next = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Aditi" language="en-IN">{clean_reply}</Say>
    <Pause length="1"/>
    <Hangup/>
</Response>"""
    else:
        twiml_next = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech" action="{action_url}" method="POST" speechTimeout="auto" language="en-IN" timeout="5">
        <Say voice="Polly.Aditi" language="en-IN">{clean_reply}</Say>
    </Gather>
    <Redirect method="POST">{action_url}?timeout=true</Redirect>
</Response>"""

    return Response(content=twiml_next, media_type="application/xml")


@router.websocket("/stream/{call_id}")
async def twilio_audio_media_stream(websocket: WebSocket, call_id: str):
    """
    Bidirectional WebSocket connection with Twilio Media Streams
    for continuous background audio stream monitoring.
    """
    await websocket.accept()
    logger.info(f"Twilio Media Stream WebSocket connected for call {call_id}")
    
    stream_sid: Optional[str] = None
    session = AudioPipelineManager.get_session(call_id)

    try:
        while True:
            message_text = await websocket.receive_text()
            data = json.loads(message_text)
            event_type = data.get("event")

            if event_type == "start":
                stream_sid = data.get("start", {}).get("streamSid")
                logger.info(f"Twilio stream started: streamSid={stream_sid} for call {call_id}")

            elif event_type == "stop":
                logger.info(f"Twilio stream stopped for call {call_id}")
                break

    except WebSocketDisconnect:
        logger.info(f"Twilio Media Stream disconnected for call {call_id}")
    except Exception as e:
        logger.error(f"Error on Twilio Media Stream for call {call_id}: {e}")
    finally:
        AudioPipelineManager.release_session(call_id)


@router.post("/status-callback")
async def twilio_status_callback(request: Request):
    """Handle status updates from Twilio (initiated, ringing, answered, completed)."""
    form_data = await request.form()
    call_sid = form_data.get("CallSid")
    call_status = form_data.get("CallStatus")
    duration = form_data.get("CallDuration")
    
    logger.info(f"Twilio Status Callback: CallSid={call_sid}, Status={call_status}, Duration={duration}")

    if call_status == "completed" and call_sid:
        async with AsyncSessionLocal() as db:
            try:
                stmt = select(Call).where(Call.provider_call_id == call_sid)
                res = await db.execute(stmt)
                call_rec = res.scalar_one_or_none()
                if call_rec:
                    call_rec.status = CallStatus.COMPLETED
                    call_rec.ended_at = datetime.utcnow()
                    if duration:
                        call_rec.duration_seconds = int(duration)
                    if call_rec.campaign_contact_id:
                        cc_stmt = select(CampaignContact).where(CampaignContact.id == call_rec.campaign_contact_id)
                        cc_res = await db.execute(cc_stmt)
                        cc_rec = cc_res.scalar_one_or_none()
                        if cc_rec:
                            cc_rec.status = CampaignContactStatus.COMPLETED
                            cc_rec.completed_at = datetime.utcnow()
                    await db.commit()
            except Exception as e:
                logger.warning(f"Error updating status callback in DB: {e}")

    return {"status": "received"}
