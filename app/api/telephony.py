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
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple

from fastapi import APIRouter, Request, HTTPException, WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, desc

from app.database import AsyncSessionLocal
from app.models.whatsapp_conversation import WhatsAppConversation
from app.models.whatsapp_message import WhatsAppMessage
from app.models.company_profile import CompanyProfile
from app.services.ai_voice_engine import AIVoiceEngine
from app.integrations.telephony.openwa import OpenWATelephonyProvider
from app.security.jwt import decode_access_token

logger = logging.getLogger(__name__)
router = APIRouter()

# Global provider instance
openwa_provider = OpenWATelephonyProvider()

# In-memory deduplication cache for webhook events (guarantees idempotency if gateway retries)
_PROCESSED_WEBHOOK_MSG_IDS: Dict[str, float] = {}
_MAX_PROCESSED_CACHE_SIZE = 10000

def is_duplicate_webhook_msg(msg_id: str, ttl_seconds: int = 300) -> bool:
    """Check and record webhook message ID to guarantee idempotent delivery without redundant processing."""
    if not msg_id:
        return False
    now = time.time()
    expired = [k for k, ts in list(_PROCESSED_WEBHOOK_MSG_IDS.items()) if now - ts > ttl_seconds]
    for k in expired:
        _PROCESSED_WEBHOOK_MSG_IDS.pop(k, None)
    
    # Memory guard for production under high volume
    if len(_PROCESSED_WEBHOOK_MSG_IDS) > _MAX_PROCESSED_CACHE_SIZE:
        oldest_keys = sorted(_PROCESSED_WEBHOOK_MSG_IDS.keys(), key=lambda k: _PROCESSED_WEBHOOK_MSG_IDS[k])[:1000]
        for k in oldest_keys:
            _PROCESSED_WEBHOOK_MSG_IDS.pop(k, None)

    if msg_id in _PROCESSED_WEBHOOK_MSG_IDS:
        return True
    _PROCESSED_WEBHOOK_MSG_IDS[msg_id] = now
    return False


class ConnectionManager:
    """Production-grade WebSocket connection manager with client isolation and heartbeat support."""
    def __init__(self):
        self.active_connections: List[Tuple[WebSocket, Optional[str]]] = []

    async def connect(self, websocket: WebSocket, user_id: Optional[str] = None):
        await websocket.accept()
        self.active_connections.append((websocket, user_id))
        logger.info(f"WebSocket client connected (user_id={user_id}). Total active: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections = [c for c in self.active_connections if c[0] != websocket]
        logger.info(f"WebSocket client disconnected. Total active: {len(self.active_connections)}")

    async def broadcast(self, message: dict, target_user_id: Optional[str] = None):
        """Broadcast message to connected clients, optionally filtered by user_id for multi-tenant isolation."""
        dead = []
        for ws, uid in list(self.active_connections):
            if target_user_id and uid and uid != target_user_id:
                continue
            try:
                await ws.send_json(message)
            except Exception as e:
                logger.debug(f"Error streaming to WebSocket client: {e}")
                dead.append(ws)
        for d in dead:
            self.disconnect(d)


ws_manager = ConnectionManager()


@router.websocket("/ws/chat")
async def websocket_chat_endpoint(websocket: WebSocket, token: Optional[str] = Query(None)):
    """
    Production-ready real-time WebSocket connection to stream incoming WhatsApp webhook messages
    to the UI with zero polling latency, JWT token authentication, and heartbeat ping/pong support.
    """
    user_id: Optional[str] = None
    if token:
        try:
            user_id = decode_access_token(token)
        except Exception as e:
            logger.debug(f"WebSocket token validation notice: {e}")

    await ws_manager.connect(websocket, user_id=user_id)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.debug(f"WebSocket closed: {e}")
        ws_manager.disconnect(websocket)


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


@router.post("/openwa/logout")
async def logout_openwa_session():
    """
    Disconnect / unlink the active WhatsApp session on OpenWA gateway
    so a new phone number QR code can be generated and scanned.
    """
    res = await openwa_provider.logout_session()
    return res


@router.post("/openwa/wake")
async def wake_openwa_gateway():
    """
    Actively probe and wake up the OpenWA gateway from Render sleep with an extended timeout.
    """
    res = await openwa_provider.wake_gateway()
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

        sender_jid = (
            data.get("from") or 
            data.get("chatId") or 
            data.get("key", {}).get("remoteJid", "")
        )
        if "@g.us" in sender_jid:
            # Skip group messages
            return {"status": "ignored", "reason": "group_message"}

        # Robust multi-format text extraction (Baileys / WPPConnect / OpenWA Gateway)
        user_text = (
            data.get("body") or 
            data.get("text") or 
            data.get("content") or 
            data.get("message", {}).get("conversation") or 
            data.get("message", {}).get("extendedTextMessage", {}).get("text") or 
            ""
        ).strip()

        if not user_text:
            return {"status": "ignored", "reason": "empty_content"}

        # Extract real contact display name if available from WhatsApp
        push_name = (
            data.get("notifyName") or 
            data.get("pushName") or 
            data.get("sender", {}).get("pushname") or 
            data.get("sender", {}).get("name") or 
            (data.get("contact", {}) or {}).get("pushName") or
            (data.get("contact", {}) or {}).get("name") or
            None
        )

        # Production Idempotency Guard: Ignore duplicate webhook deliveries from gateway retries
        raw_msg_id = (
            data.get("id") or 
            data.get("messageId") or 
            data.get("key", {}).get("id") or 
            ""
        )
        if raw_msg_id and is_duplicate_webhook_msg(str(raw_msg_id)):
            logger.info(f"Duplicate webhook message [{raw_msg_id}] ignored (idempotent guard).")
            return {"status": "ignored", "reason": "duplicate_webhook_event", "message_id": str(raw_msg_id)}

        is_lid = str(sender_jid).endswith("@lid")
        resolved_phone: Optional[str] = None

        # 1. Check if OpenWA already provided resolved sender phone in the event payload
        if data.get("senderPhone"):
            resolved_phone = str(data["senderPhone"]).strip()
        elif data.get("sender_phone"):
            resolved_phone = str(data["sender_phone"]).strip()

        # 2. Check author or sender id fields for a real @c.us / MSISDN phone
        if not resolved_phone:
            author = str(data.get("author") or "")
            if author and not author.endswith("@lid") and "@" in author:
                resolved_phone = author.split("@")[0]

        if not resolved_phone:
            sender_id = str((data.get("sender", {}) or {}).get("id") or "")
            if sender_id and not sender_id.endswith("@lid") and "@" in sender_id:
                resolved_phone = sender_id.split("@")[0]

        if not resolved_phone and (data.get("contact", {}) or {}).get("number"):
            resolved_phone = str(data["contact"]["number"]).strip()

        # 3. If still unresolved and sender is an @lid, query OpenWA Gateway directly
        if is_lid and not resolved_phone:
            try:
                openwa_resolved = await openwa_provider.resolve_lid_to_phone(sender_jid)
                if openwa_resolved:
                    resolved_phone = openwa_resolved
                    logger.info(f"Successfully resolved @lid {sender_jid} -> phone {resolved_phone} via OpenWA API")
            except Exception as e:
                logger.debug(f"OpenWA LID resolve attempt notice: {e}")

        logger.info(f"Incoming WhatsApp message from sender_jid='{sender_jid}', resolved_phone='{resolved_phone}', push_name='{push_name}': '{user_text}'")

        async with AsyncSessionLocal() as db:
            try:
                conv: Optional[WhatsAppConversation] = None

                # Step A: Check if this chat_jid (@lid or @c.us) is already linked to an existing conversation
                jid_stmt = select(WhatsAppConversation).where(
                    WhatsAppConversation.chat_jid == sender_jid
                ).order_by(desc(WhatsAppConversation.updated_at))
                jid_res = await db.execute(jid_stmt)
                conv = jid_res.scalars().first()

                # Step B: If resolved_phone is available, find conversation by phone number variants
                if not conv and resolved_phone:
                    r_clean = re.sub(r"[^\d]", "", resolved_phone)
                    r_variants = [resolved_phone, r_clean, f"+{r_clean}"]
                    if len(r_clean) >= 10:
                        r_last10 = r_clean[-10:]
                        r_variants.extend([r_last10, f"+91{r_last10}", f"+1{r_last10}"])
                    r_stmt = select(WhatsAppConversation).where(
                        WhatsAppConversation.phone_number.in_(r_variants)
                    ).order_by(desc(WhatsAppConversation.updated_at))
                    r_res = await db.execute(r_stmt)
                    conv = r_res.scalars().first()

                # Step C: If sender_jid is NOT an LID (e.g. 917069812116@c.us), match directly by phone variants
                if not conv and not is_lid:
                    clean_phone = re.sub(r"[^\d]", "", sender_jid.split("@")[0])
                    phone_variants = [clean_phone, f"+{clean_phone}"]
                    if len(clean_phone) >= 10:
                        last10 = clean_phone[-10:]
                        phone_variants.extend([last10, f"+91{last10}", f"+1{last10}"])

                    conv_stmt = select(WhatsAppConversation).where(
                        WhatsAppConversation.phone_number.in_(phone_variants)
                    ).order_by(desc(WhatsAppConversation.updated_at))
                    conv_res = await db.execute(conv_stmt)
                    conv = conv_res.scalars().first()

                # Step D: If still not matched and sender is an @lid:
                # Correlate with recent broadcast recipients who were sent an outbound message recently
                if not conv and is_lid:
                    recent_cutoff = datetime.utcnow() - timedelta(hours=4)
                    candidate_stmt = (
                        select(WhatsAppConversation)
                        .join(WhatsAppMessage, WhatsAppMessage.conversation_id == WhatsAppConversation.id)
                        .where(
                            WhatsAppMessage.direction == "outbound",
                            WhatsAppMessage.created_at >= recent_cutoff
                        )
                        .order_by(desc(WhatsAppMessage.created_at))
                        .limit(10)
                    )
                    cand_res = await db.execute(candidate_stmt)
                    candidates = cand_res.scalars().all()

                    # Check 1: push_name matches contact name (e.g. "Umang" matches "Umang")
                    if push_name:
                        for c in candidates:
                            c_n = (c.contact_name or "").lower().strip()
                            p_n = push_name.lower().strip()
                            if c_n and p_n and (c_n in p_n or p_n in c_n):
                                conv = c
                                logger.info(f"Matched @lid {sender_jid} by push_name '{push_name}' to existing conversation: {c.contact_name} ({c.phone_number})")
                                break

                    # Check 2: If there's only 1 recent outbound broadcast conversation in the window, link to it
                    if not conv and len(candidates) == 1:
                        conv = candidates[0]
                        logger.info(f"Matched @lid {sender_jid} to the single recent broadcast recipient: {conv.contact_name} ({conv.phone_number})")

                comp_stmt = select(CompanyProfile).order_by(desc(CompanyProfile.created_at)).limit(1)
                comp_res = await db.execute(comp_stmt)
                company_profile = comp_res.scalar_one_or_none()

                if not conv:
                    # Brand new inbound thread
                    phone_to_save = resolved_phone or re.sub(r"[^\d]", "", sender_jid.split("@")[0])
                    formatted_phone = f"+{phone_to_save}" if not phone_to_save.startswith("+") else phone_to_save
                    conv = WhatsAppConversation(
                        user_id=company_profile.user_id if company_profile else None,
                        phone_number=formatted_phone,
                        contact_name=push_name or "WhatsApp Customer",
                        chat_jid=sender_jid,
                        last_message_text=user_text,
                        last_message_at=datetime.utcnow()
                    )
                    db.add(conv)
                    await db.commit()
                    await db.refresh(conv)
                    logger.info(f"Created new conversation thread {conv.id} for phone {conv.phone_number}")
                else:
                    # Link chat_jid so all subsequent incoming/outgoing messages use this JID seamlessly
                    conv.chat_jid = sender_jid
                    if push_name and (conv.contact_name in ["WhatsApp Customer", "Customer", None, ""]):
                        conv.contact_name = push_name
                    conv.last_message_text = user_text
                    conv.last_message_at = datetime.utcnow()
                    await db.commit()
                    logger.info(f"Appended incoming message to existing conversation thread {conv.id} for {conv.contact_name} ({conv.phone_number})")

                # Record customer's incoming message
                cust_msg = WhatsAppMessage(
                    conversation_id=conv.id,
                    sender="customer",
                    direction="inbound",
                    message_text=user_text,
                    status="received",
                    openwa_message_id=str(raw_msg_id) if raw_msg_id else None,
                    chat_jid=sender_jid,
                    ai_generated=False
                )
                db.add(cust_msg)
                await db.commit()

                # Instantly push incoming customer message to connected frontend UI via WebSocket
                try:
                    await ws_manager.broadcast({
                        "type": "new_message",
                        "conversation_id": str(conv.id),
                        "phone_number": conv.phone_number,
                        "contact_name": conv.contact_name or "WhatsApp Customer",
                        "message": {
                            "id": str(cust_msg.id),
                            "sender": "customer",
                            "text": user_text,
                            "time": datetime.utcnow().strftime("%I:%M %p"),
                            "status": "received",
                            "created_at": datetime.utcnow().isoformat()
                        }
                    })
                except Exception as wse:
                    logger.debug(f"WebSocket broadcast notice: {wse}")

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

                provider_config = {
                    "company_name": "Our Company",
                    "agent_name": "Sarah",
                    "tone": "helpful, warm, and professional",
                    "language": "English"
                }
                if company_profile:
                    provider_config = {
                        "company_name": company_profile.name or "Our Company",
                        "agent_name": company_profile.default_agent_name or "Sarah",
                        "tone": "helpful, warm, and professional",
                        "language": company_profile.default_language or "English",
                        "industry": company_profile.industry or "Customer Support & Services"
                    }

                # Generate natural, human-like AI reply with resilient fallback
                try:
                    agent_reply = await AIVoiceEngine.generate_live_turn(
                        campaign_name="WhatsApp Assistant",
                        agent_prompt=f"Assist the customer regarding {provider_config.get('company_name', 'our company')}.",
                        provider_config=provider_config,
                        conversation_history=dialogue_history,
                        user_message=user_text,
                        contact_name=conv.contact_name or "Valued Customer"
                    )
                except Exception as ai_err:
                    logger.error(f"AI response generation error: {ai_err}, using polite fallback", exc_info=True)
                    c_name = provider_config.get("company_name", "our team")
                    agent_reply = f"Hello {conv.contact_name or 'there'}! Thank you for reaching out to {c_name}. We have received your message and our team is reviewing it right now. How else may I assist you?"

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

                # Instantly push AI agent reply to connected frontend UI via WebSocket
                try:
                    await ws_manager.broadcast({
                        "type": "new_message",
                        "conversation_id": str(conv.id),
                        "phone_number": conv.phone_number,
                        "contact_name": conv.contact_name or "WhatsApp Customer",
                        "message": {
                            "id": str(ai_msg.id),
                            "sender": "agent",
                            "text": agent_reply,
                            "time": datetime.utcnow().strftime("%I:%M %p"),
                            "status": "sent",
                            "created_at": datetime.utcnow().isoformat()
                        }
                    })
                except Exception as wse:
                    logger.debug(f"WebSocket broadcast notice: {wse}")

                # Deliver pure human-like text reply directly via OpenWA
                try:
                    await openwa_provider.send_text_message(
                        chat_id=sender_jid,
                        text=agent_reply
                    )
                except Exception as se:
                    logger.error(f"Failed to deliver WhatsApp reply via OpenWA: {se}")

                return {"status": "success", "processed": True, "reply": agent_reply}

            except Exception as dbe:
                await db.rollback()
                logger.error(f"Database error in handle_openwa_webhook: {dbe}", exc_info=True)
                return {"status": "error", "detail": str(dbe)}

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


class ConversationReplyRequest(BaseModel):
    message: str
    contact_name: Optional[str] = "Customer"
    send_live_openwa: Optional[bool] = True


@router.get("/conversations")
async def list_whatsapp_conversations(limit: int = 50):
    """List all active WhatsApp conversation threads."""
    async with AsyncSessionLocal() as db:
        stmt = (
            select(WhatsAppConversation)
            .order_by(desc(WhatsAppConversation.updated_at))
            .limit(limit)
        )
        res = await db.execute(stmt)
        convs = res.scalars().all()
        output = []
        for c in convs:
            output.append({
                "id": str(c.id),
                "phone_number": c.phone_number,
                "contact_name": c.contact_name,
                "last_message_text": c.last_message_text,
                "last_message_at": c.last_message_at.isoformat() if c.last_message_at else None,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None
            })
        return output


@router.get("/conversations/{phone_number}/messages")
async def get_conversation_messages(phone_number: str):
    """Fetch all messages for a specific phone number in chronological order with resilient phone resolution."""
    clean_digits = re.sub(r"[^\d]", "", phone_number)
    async with AsyncSessionLocal() as db:
        search_terms = [phone_number, clean_digits, f"+{clean_digits}"]
        if len(clean_digits) >= 10:
            last10 = clean_digits[-10:]
            search_terms.extend([last10, f"+91{last10}", f"+1{last10}"])

        stmt = select(WhatsAppConversation).where(
            WhatsAppConversation.phone_number.in_(search_terms)
        ).order_by(desc(WhatsAppConversation.updated_at))
        res = await db.execute(stmt)
        conv = res.scalars().first()

        # Fallback suffix search if not found directly
        if not conv and len(clean_digits) >= 10:
            last10 = clean_digits[-10:]
            fallback_stmt = select(WhatsAppConversation).where(
                WhatsAppConversation.phone_number.like(f"%{last10}")
            ).order_by(desc(WhatsAppConversation.updated_at))
            fallback_res = await db.execute(fallback_stmt)
            conv = fallback_res.scalars().first()

        if not conv:
            fallback_jid_stmt = select(WhatsAppConversation).where(
                WhatsAppConversation.chat_jid.in_([phone_number, f"{clean_digits}@c.us", f"{clean_digits}@lid"])
            ).order_by(desc(WhatsAppConversation.updated_at))
            fallback_jid_res = await db.execute(fallback_jid_stmt)
            conv = fallback_jid_res.scalars().first()

        if not conv:
            return {"conversation": None, "messages": []}

        msg_stmt = (
            select(WhatsAppMessage)
            .where(WhatsAppMessage.conversation_id == conv.id)
            .order_by(WhatsAppMessage.created_at.asc())
        )
        msg_res = await db.execute(msg_stmt)
        msgs = msg_res.scalars().all()

        messages_data = []
        for m in msgs:
            time_str = m.created_at.strftime("%I:%M %p") if m.created_at else "Just now"
            messages_data.append({
                "id": str(m.id),
                "sender": m.sender,
                "text": m.message_text,
                "time": time_str,
                "status": m.status,
                "created_at": m.created_at.isoformat() if m.created_at else None
            })

        return {
            "conversation": {
                "id": str(conv.id),
                "phone_number": conv.phone_number,
                "contact_name": conv.contact_name,
                "last_message_text": conv.last_message_text,
                "last_message_at": conv.last_message_at.isoformat() if conv.last_message_at else None
            },
            "messages": messages_data
        }


@router.post("/conversations/{phone_number}/reply")
async def post_conversation_customer_reply(phone_number: str, payload: ConversationReplyRequest):
    """
    Production-ready handler to simulate customer reply, trigger natural AI turn,
    record both to database with transaction rollback safety, broadcast over WebSocket,
    and optionally forward to OpenWA device.
    """
    clean_digits = re.sub(r"[^\d]", "", phone_number)
    user_text = payload.message.strip()
    contact_name = payload.contact_name or "Customer"

    if not user_text:
        raise HTTPException(status_code=400, detail="Message text is required")

    sender_jid = f"{clean_digits}@c.us"
    formatted_phone = f"+{clean_digits}" if not phone_number.startswith("+") else phone_number

    phone_variants = [phone_number, clean_digits, f"+{clean_digits}"]
    if len(clean_digits) >= 10:
        last10 = clean_digits[-10:]
        phone_variants.extend([last10, f"+91{last10}", f"+1{last10}"])

    async with AsyncSessionLocal() as db:
        try:
            stmt = select(WhatsAppConversation).where(
                WhatsAppConversation.phone_number.in_(phone_variants)
            ).order_by(desc(WhatsAppConversation.updated_at))
            res = await db.execute(stmt)
            conv = res.scalars().first()

            if not conv and len(clean_digits) >= 10:
                last10 = clean_digits[-10:]
                fallback_stmt = select(WhatsAppConversation).where(
                    WhatsAppConversation.phone_number.like(f"%{last10}")
                ).order_by(desc(WhatsAppConversation.updated_at))
                fallback_res = await db.execute(fallback_stmt)
                conv = fallback_res.scalars().first()

            if not conv:
                fallback_jid_stmt = select(WhatsAppConversation).where(
                    WhatsAppConversation.chat_jid.in_([phone_number, f"{clean_digits}@c.us", f"{clean_digits}@lid"])
                ).order_by(desc(WhatsAppConversation.updated_at))
                fallback_jid_res = await db.execute(fallback_jid_stmt)
                conv = fallback_jid_res.scalars().first()

            comp_stmt = select(CompanyProfile).order_by(desc(CompanyProfile.created_at)).limit(1)
            comp_res = await db.execute(comp_stmt)
            company_profile = comp_res.scalar_one_or_none()

            if not conv:
                conv = WhatsAppConversation(
                    user_id=company_profile.user_id if company_profile else None,
                    phone_number=formatted_phone,
                    contact_name=contact_name,
                    chat_jid=sender_jid,
                    last_message_text=user_text,
                    last_message_at=datetime.utcnow()
                )
                db.add(conv)
                await db.commit()
                await db.refresh(conv)

            target_chat_id = conv.chat_jid if (conv and conv.chat_jid) else sender_jid

            cust_msg = WhatsAppMessage(
                conversation_id=conv.id,
                sender="customer",
                direction="inbound",
                message_text=user_text,
                status="received",
                chat_jid=target_chat_id,
                ai_generated=False
            )
            db.add(cust_msg)
            await db.commit()

            # Broadcast incoming customer message over WebSocket
            try:
                await ws_manager.broadcast({
                    "type": "new_message",
                    "conversation_id": str(conv.id),
                    "phone_number": conv.phone_number,
                    "contact_name": conv.contact_name or contact_name,
                    "message": {
                        "id": str(cust_msg.id),
                        "sender": "customer",
                        "text": user_text,
                        "time": datetime.utcnow().strftime("%I:%M %p"),
                        "status": "received",
                        "created_at": datetime.utcnow().isoformat()
                    }
                })
            except Exception as wse:
                logger.debug(f"WebSocket broadcast notice: {wse}")

            hist_stmt = (
                select(WhatsAppMessage)
                .where(WhatsAppMessage.conversation_id == conv.id)
                .order_by(WhatsAppMessage.created_at.asc())
                .limit(20)
            )
            hist_res = await db.execute(hist_stmt)
            messages = hist_res.scalars().all()

            dialogue_history = []
            for m in messages:
                dialogue_history.append({
                    "speaker": "agent" if m.sender == "agent" else "customer",
                    "text": m.message_text
                })

            provider_config = {
                "company_name": "Our Company",
                "agent_name": "Sarah",
                "tone": "helpful, warm, and professional",
                "language": "English"
            }
            if company_profile:
                provider_config = {
                    "company_name": company_profile.name or "Our Company",
                    "agent_name": company_profile.default_agent_name or "Sarah",
                    "tone": "helpful, warm, and professional",
                    "language": company_profile.default_language or "English",
                    "industry": company_profile.industry or "Customer Support & Services"
                }

            # Resilient AI generation with polite human fallback
            try:
                agent_reply = await AIVoiceEngine.generate_live_turn(
                    campaign_name="WhatsApp Assistant",
                    agent_prompt=f"Assist the customer regarding {provider_config.get('company_name', 'our company')}.",
                    provider_config=provider_config,
                    conversation_history=dialogue_history,
                    user_message=user_text,
                    contact_name=conv.contact_name or contact_name
                )
            except Exception as ai_err:
                logger.error(f"Simulator AI turn error: {ai_err}, using polite fallback", exc_info=True)
                c_name = provider_config.get("company_name", "our team")
                agent_reply = f"Hello {conv.contact_name or contact_name}! Thank you for reaching out to {c_name}. We have received your message and our team will get in touch shortly."

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

            conv.last_message_text = agent_reply
            conv.last_message_at = datetime.utcnow()
            await db.commit()

            # Broadcast reply to connected frontend WebSocket listeners
            try:
                await ws_manager.broadcast({
                    "type": "new_message",
                    "conversation_id": str(conv.id),
                    "phone_number": conv.phone_number,
                    "contact_name": conv.contact_name or payload.contact_name or "WhatsApp Customer",
                    "message": {
                        "id": str(ai_msg.id),
                        "sender": "agent",
                        "text": agent_reply,
                        "time": datetime.utcnow().strftime("%I:%M %p"),
                        "status": "sent",
                        "created_at": datetime.utcnow().isoformat()
                    }
                })
            except Exception as wse:
                logger.debug(f"WebSocket broadcast notice: {wse}")

            if payload.send_live_openwa:
                try:
                    status_data = await openwa_provider.get_session_status()
                    if status_data.get("status") in ["ready", "CONNECTED", "AUTHENTICATED"]:
                        await openwa_provider.send_text_message(
                            chat_id=target_chat_id,
                            text=agent_reply
                        )
                except Exception as se:
                    logger.warning(f"Could not forward simulator turn via OpenWA: {se}")

            return {
                "success": True,
                "conversation_id": str(conv.id),
                "customer_message": user_text,
                "agent_reply": agent_reply,
                "timestamp": datetime.utcnow().isoformat()
            }
        except Exception as e:
            await db.rollback()
            logger.error(f"Error in post_conversation_customer_reply: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

