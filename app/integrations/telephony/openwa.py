"""OpenWA (Open Source WhatsApp API Gateway) Telephony Provider.

Connects to self-hosted OpenWA gateway (running on http://localhost:2785 or OPENWA_BASE_URL)
to handle outbound and inbound WhatsApp calls, dynamic AI voice notes (PTT),
and real-time customer conversations.
"""

import os
import re
import uuid
import base64
import logging
import asyncio
import hmac
import hashlib
from typing import Dict, Any, Optional, List
import httpx
import edge_tts

from app.integrations.telephony.base import TelephonyProvider
from app.config import settings

logger = logging.getLogger(__name__)


SENTINEL = object()

class OpenWATelephonyProvider(TelephonyProvider):
    """
    OpenWA WhatsApp Telephony Gateway Integration.
    Enables company-to-user and user-to-company WhatsApp calls and voice interactions.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Any = SENTINEL,
        session_id: Optional[str] = None,
        webhook_secret: Optional[str] = None
    ):
        self.base_url = (base_url or getattr(settings, "OPENWA_BASE_URL", "http://localhost:2785")).rstrip("/")
        self.api_key = getattr(settings, "OPENWA_API_KEY", None) if api_key is SENTINEL else api_key
        self.session_id = session_id or getattr(settings, "OPENWA_SESSION_ID", "default")
        self.webhook_secret = webhook_secret or getattr(settings, "OPENWA_WEBHOOK_SECRET", None)

    @property
    def provider_name(self) -> str:
        return "openwa"

    @property
    def supports_streaming(self) -> bool:
        return True

    @property
    def supports_india_domestic(self) -> bool:
        return True

    def get_auth_headers(self) -> Dict[str, str]:
        """Headers required by OpenWA API."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    def normalize_phone_to_jid(self, phone: str) -> str:
        """
        Normalize E.164 phone number to WhatsApp JID.
        e.g., '+91 98765-43210' -> '919876543210@c.us'
        """
        clean_num = re.sub(r"[^\d]", "", str(phone))
        # Remove leading zeroes if country code follows
        clean_num = clean_num.lstrip("0")
        if "@" in phone:
            return phone.strip()
        return f"{clean_num}@c.us"

    async def get_session_status(self) -> Dict[str, Any]:
        """Fetch current WhatsApp session status from OpenWA Gateway."""
        url = f"{self.base_url}/api/sessions/{self.session_id}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, headers=self.get_auth_headers())
                if res.status_code == 200:
                    return res.json()
                elif res.status_code == 404:
                    return {"status": "DISCONNECTED", "message": f"Session '{self.session_id}' not found"}
                return {"status": "ERROR", "statusCode": res.status_code, "body": res.text}
        except httpx.ConnectError:
            return {
                "status": "OFFLINE",
                "message": f"Cannot connect to OpenWA Gateway at {self.base_url}. Ensure OpenWA is running via Docker."
            }
        except Exception as e:
            logger.error(f"Error checking OpenWA session status: {e}")
            return {"status": "ERROR", "message": str(e)}

    async def get_session_qr(self) -> Dict[str, Any]:
        """Retrieve QR code data URL from OpenWA for WhatsApp device linking."""
        url = f"{self.base_url}/api/sessions/{self.session_id}/qr"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, headers=self.get_auth_headers())
                if res.status_code == 200:
                    data = res.json()
                    # OpenWA returns { qrCode: "data:image/png;base64,..." } or { qr: "..." }
                    qr_val = data.get("qrCode") or data.get("qr") or (data if isinstance(data, str) else "")
                    return {"success": True, "qr": qr_val}
                return {"success": False, "statusCode": res.status_code, "detail": res.text}
        except Exception as e:
            logger.error(f"Error fetching OpenWA QR code: {e}")
            return {"success": False, "error": str(e)}

    async def create_or_start_session(self) -> Dict[str, Any]:
        """Create or initialize WhatsApp session on OpenWA gateway."""
        url = f"{self.base_url}/api/sessions"
        payload = {"sessionId": self.session_id}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(url, json=payload, headers=self.get_auth_headers())
                if res.status_code in [200, 201]:
                    return res.json()
                return {"success": False, "statusCode": res.status_code, "detail": res.text}
        except Exception as e:
            logger.error(f"Error creating OpenWA session: {e}")
            return {"success": False, "error": str(e)}

    async def synthesize_speech_bytes(
        self,
        text: str,
        voice: str = "en-IN-NeerjaNeural"
    ) -> Optional[bytes]:
        """Synthesize text into speech audio bytes using Edge-TTS."""
        try:
            communicate = edge_tts.Communicate(text, voice)
            audio_data = bytearray()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data.extend(chunk["data"])
            if audio_data:
                return bytes(audio_data)
        except Exception as e:
            logger.warning(f"EdgeTTS primary synthesis failed with voice {voice}: {e}. Retrying with en-US-JennyNeural...")

        try:
            communicate = edge_tts.Communicate(text, "en-US-JennyNeural")
            audio_data = bytearray()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data.extend(chunk["data"])
            if audio_data:
                return bytes(audio_data)
        except Exception as e2:
            logger.error(f"EdgeTTS fallback synthesis also failed: {e2}")

        return None

    async def send_text_message(self, chat_id: str, text: str) -> Dict[str, Any]:
        """Send a WhatsApp text message through OpenWA."""
        url = f"{self.base_url}/api/sessions/{self.session_id}/messages/send-text"
        payload = {
            "chatId": chat_id,
            "text": text
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(url, json=payload, headers=self.get_auth_headers())
                if res.status_code in [200, 201]:
                    return res.json()
                logger.error(f"OpenWA send-text error: {res.status_code} - {res.text}")
                return {"success": False, "statusCode": res.status_code, "detail": res.text}
        except Exception as e:
            logger.error(f"Failed to send text message via OpenWA: {e}")
            return {"success": False, "error": str(e)}

    async def send_voice_audio(
        self,
        chat_id: str,
        audio_bytes: bytes,
        mimetype: str = "audio/ogg; codecs=opus",
        ptt: bool = True
    ) -> Dict[str, Any]:
        """
        Send audio as real WhatsApp Voice Note (PTT) with waveform.
        """
        url = f"{self.base_url}/api/sessions/{self.session_id}/messages/send-audio"
        b64_audio = base64.b64encode(audio_bytes).decode("utf-8")
        payload = {
            "chatId": chat_id,
            "base64": b64_audio,
            "mimetype": mimetype,
            "ptt": ptt
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.post(url, json=payload, headers=self.get_auth_headers())
                if res.status_code in [200, 201]:
                    return res.json()
                logger.error(f"OpenWA send-audio error: {res.status_code} - {res.text}")
                return {"success": False, "statusCode": res.status_code, "detail": res.text}
        except Exception as e:
            logger.error(f"Failed to send voice audio via OpenWA: {e}")
            return {"success": False, "error": str(e)}

    async def create_call(
        self,
        phone_number: str,
        caller_id: Optional[str] = None,
        speech_text: Optional[str] = None,
        voice: str = "en-IN-NeerjaNeural",
        webhook_url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Initiate an outbound WhatsApp voice call / interactive voice message to customer.
        Company calls User workflow.
        """
        chat_id = self.normalize_phone_to_jid(phone_number)
        logger.info(f"Initiating OpenWA WhatsApp Voice Call to {chat_id} (Phone: {phone_number})")

        prompt_text = speech_text or "Hello! This is your AI assistant calling from our company. How may I assist you today?"

        voice_result = {}
        # Step 1: Synthesize AI Voice
        audio_bytes = await self.synthesize_speech_bytes(prompt_text, voice=voice)

        if audio_bytes:
            # Step 2: Send WhatsApp Voice Note (PTT)
            voice_result = await self.send_voice_audio(
                chat_id=chat_id,
                audio_bytes=audio_bytes,
                ptt=True
            )
        else:
            logger.warning("Voice synthesis not available; proceeding with WhatsApp conversational text dispatch.")

        msg_id = (
            voice_result.get("id")
            or voice_result.get("messageId")
            or voice_result.get("data", {}).get("id")
            or f"openwa_{uuid.uuid4().hex[:12]}"
        )

        # Step 3: Conversational greeting text
        text_result = await self.send_text_message(
            chat_id=chat_id,
            text=f"📞 Incoming AI Voice Call from {getattr(settings, 'PROJECT_NAME', 'Our Company')}:\n\n\"{prompt_text}\"\n\n💬 You can reply with a voice note or message to talk with our AI assistant!"
        )

        return {
            "provider_call_id": str(msg_id),
            "status": "in_progress",
            "to": phone_number,
            "chat_id": chat_id,
            "provider": "openwa",
            "has_voice": bool(audio_bytes),
            "voice_response": voice_result,
            "text_response": text_result
        }

    async def get_call_status(self, provider_call_id: str) -> Dict[str, Any]:
        """Get status of an OpenWA call or message."""
        return {
            "provider_call_id": provider_call_id,
            "status": "in_progress",
            "provider": "openwa"
        }

    async def end_call(self, provider_call_id: str) -> bool:
        """End or mark call finished."""
        logger.info(f"Ending OpenWA call {provider_call_id}")
        return True

    def validate_webhook(self, headers: Dict[str, str], body: bytes) -> bool:
        """Validate HMAC signature if OPENWA_WEBHOOK_SECRET is configured."""
        if not self.webhook_secret:
            return True

        signature = headers.get("x-openwa-signature") or headers.get("X-Hub-Signature-256")
        if not signature:
            return False

        computed = "sha256=" + hmac.new(
            self.webhook_secret.encode("utf-8"),
            body,
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(signature, computed)

    async def handle_call_event(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize inbound call events (call.received, call.accepted, call.rejected).
        User calls Company workflow.
        """
        event_type = event_data.get("event")
        data = event_data.get("data", event_data)

        caller_jid = data.get("from") or data.get("chatId") or ""
        clean_phone = re.sub(r"[^\d]", "", caller_jid.split("@")[0])

        return {
            "event": event_type,
            "call_id": data.get("id"),
            "from": clean_phone,
            "chat_id": caller_jid,
            "is_video": data.get("isVideo", False),
            "timestamp": event_data.get("timestamp")
        }

    async def start_media_stream(self, provider_call_id: str, stream_url: str) -> bool:
        """Stream media (implemented via audio pipeline in OpenWA)."""
        return True
