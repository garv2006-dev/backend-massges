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


def clean_error_response(status_code: int, raw_text: str) -> str:
    """Extract clean, human-readable error description from gateway response (handles HTML 502/503/504)."""
    if not raw_text:
        return f"HTTP {status_code} Error"
    text = str(raw_text).strip()
    if text.startswith("<") or "<html" in text.lower():
        if status_code == 502:
            return "OpenWA Gateway is unavailable (502 Bad Gateway). Service on Render is sleeping, restarting, or unreachable."
        elif status_code == 503:
            return "OpenWA Gateway is temporarily unavailable (503 Service Unavailable). The service may be starting up."
        elif status_code == 504:
            return "OpenWA Gateway request timed out (504 Gateway Timeout)."
        title_match = re.search(r"<title>(.*?)</title>", text, re.IGNORECASE)
        if title_match:
            return f"HTTP {status_code}: {title_match.group(1).strip()}"
        return f"HTTP {status_code} Gateway Error (HTML response received)"
    if status_code == 401:
        return "OpenWA Authentication Failed (401 Unauthorized). Check that OPENWA_API_KEY in the backend matches the API_KEY configured on the OpenWA Render service."
    if len(text) > 300:
        return text[:300] + "..."
    return text


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
        self.base_url = (base_url or getattr(settings, "OPENWA_BASE_URL", "http://localhost:2785")).strip().rstrip("/")
        raw_key = getattr(settings, "OPENWA_API_KEY", None) if api_key is SENTINEL else api_key
        self.api_key = raw_key.strip() if isinstance(raw_key, str) else raw_key
        raw_session = session_id or getattr(settings, "OPENWA_SESSION_ID", "default")
        self.session_id = raw_session.strip() if isinstance(raw_session, str) else raw_session
        self.webhook_secret = webhook_secret or getattr(settings, "OPENWA_WEBHOOK_SECRET", None)
        self._resolved_session_id: Optional[str] = None

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
            headers["X-API-Key"] = str(self.api_key).strip()
        return headers

    async def resolve_session_uuid(self) -> str:
        """
        OpenWA v0.25+ identifies sessions by UUID (e.g. 04defc4a-...).
        This helper resolves self.session_id (which might be 'default')
        to the matching active session UUID, or automatically creates it.
        """
        if self._resolved_session_id:
            return self._resolved_session_id

        # If already formatted as a standard 36-char UUID, use directly
        if len(self.session_id) == 36 and self.session_id.count("-") == 4:
            self._resolved_session_id = self.session_id
            return self.session_id

        url = f"{self.base_url}/api/sessions"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, headers=self.get_auth_headers())
                if res.status_code == 200:
                    sessions = res.json()
                    if isinstance(sessions, list):
                        for s in sessions:
                            if s.get("name") == self.session_id or s.get("id") == self.session_id:
                                self._resolved_session_id = s.get("id")
                                return self._resolved_session_id

                # If session does not exist yet, create it with payload {"name": self.session_id}
                create_res = await client.post(url, json={"name": self.session_id}, headers=self.get_auth_headers())
                if create_res.status_code in [200, 201]:
                    new_session = create_res.json()
                    if new_session.get("id"):
                        self._resolved_session_id = new_session.get("id")
                        return self._resolved_session_id
        except Exception as e:
            logger.debug(f"OpenWA resolve_session_uuid notice: {e}")

        return self.session_id

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

    async def resolve_lid_to_phone(self, contact_id: str) -> Optional[str]:
        """
        Resolve a WhatsApp contact ID (specifically an @lid JID) to real MSISDN phone digits.
        Queries OpenWA endpoint: GET /api/sessions/{session_id}/contacts/{contact_id}/phone
        """
        if not contact_id:
            return None
        c_str = str(contact_id).strip()
        if not c_str.endswith("@lid"):
            clean = re.sub(r"[^\d]", "", c_str)
            return clean if len(clean) >= 10 else None

        sid = await self.resolve_session_uuid()
        url = f"{self.base_url}/api/sessions/{sid}/contacts/{c_str}/phone"
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                res = await client.get(url, headers=self.get_auth_headers())
                if res.status_code == 200:
                    data = res.json()
                    p = data.get("phone")
                    if p:
                        clean_p = re.sub(r"[^\d]", "", str(p))
                        if len(clean_p) >= 10:
                            return clean_p
        except Exception as e:
            logger.debug(f"OpenWA resolvePhone for {contact_id} note: {e}")
        return None

    async def get_session_status(self) -> Dict[str, Any]:
        """Fetch current WhatsApp session status from OpenWA Gateway with automatic sleep wake-up retry."""
        sid = await self.resolve_session_uuid()
        url = f"{self.base_url}/api/sessions/{sid}"
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=25.0) as client:
                    res = await client.get(url, headers=self.get_auth_headers())
                    if res.status_code == 200:
                        try:
                            return res.json()
                        except Exception:
                            return {"status": "ERROR", "message": "Invalid JSON response from OpenWA"}
                    elif res.status_code == 404:
                        return {"status": "DISCONNECTED", "message": f"Session '{self.session_id}' not found"}
                    
                    # If 502/503/504 on first attempt, service is waking up on Render: wait and retry
                    if res.status_code in [502, 503, 504] and attempt == 0:
                        logger.info("OpenWA gateway waking up from idle on Render, retrying status check in 3s...")
                        await asyncio.sleep(3.0)
                        continue

                    clean_msg = clean_error_response(res.status_code, res.text)
                    return {
                        "status": "ERROR",
                        "statusCode": res.status_code,
                        "body": clean_msg,
                        "message": clean_msg,
                        "is_gateway_unavailable": res.status_code in [502, 503, 504]
                    }
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                if attempt == 0:
                    logger.info("Timeout/connection probe on OpenWA (container may be booting from Render sleep), retrying in 3s...")
                    await asyncio.sleep(3.0)
                    continue
                return {
                    "status": "OFFLINE",
                    "message": f"Cannot connect to OpenWA Gateway at {self.base_url}. Service is offline or waking up from Render sleep.",
                    "is_gateway_unavailable": True
                }
            except Exception as e:
                logger.error(f"Error checking OpenWA session status: {e}")
                return {"status": "ERROR", "message": str(e)}

        return {"status": "ERROR", "message": "Failed to reach OpenWA gateway after retries."}

    async def get_session_qr(self) -> Dict[str, Any]:
        """Retrieve QR code data URL from OpenWA for WhatsApp device linking with auto wake-up retry."""
        sid = await self.resolve_session_uuid()
        url = f"{self.base_url}/api/sessions/{sid}/qr"
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=25.0) as client:
                    res = await client.get(url, headers=self.get_auth_headers())
                    if res.status_code == 200:
                        try:
                            data = res.json()
                        except Exception:
                            data = res.text
                        qr_val = (
                            data.get("qrCode") or data.get("qr")
                            if isinstance(data, dict)
                            else (data if isinstance(data, str) and "data:image" in data else "")
                        )
                        if qr_val:
                            return {"success": True, "qr": qr_val}

                    # If session is already authenticated, no QR code is needed
                    if res.status_code == 400 and ("already authenticated" in res.text.lower() or "no qr code needed" in res.text.lower()):
                        return {
                            "success": True,
                            "already_authenticated": True,
                            "is_connected": True,
                            "message": "WhatsApp is already connected and authenticated. No QR code needed.",
                            "qr": None
                        }

                    # If 502/503/504 on attempt 0, container is waking up on Render
                    if res.status_code in [502, 503, 504] and attempt == 0:
                        logger.info("OpenWA gateway waking up from idle on Render, retrying QR fetch in 3s...")
                        await asyncio.sleep(3.0)
                        continue

                    # If session is not started yet, automatically boot session and retry fetching QR
                    if res.status_code in [400, 404]:
                        start_res = await self.create_or_start_session()
                        if start_res.get("success") is not False:
                            # Wait briefly for engine to generate the initial QR code
                            await asyncio.sleep(2.0)
                            retry_res = await client.get(url, headers=self.get_auth_headers())
                            if retry_res.status_code == 200:
                                try:
                                    r_data = retry_res.json()
                                except Exception:
                                    r_data = retry_res.text
                                qr_val = (
                                    r_data.get("qrCode") or r_data.get("qr")
                                    if isinstance(r_data, dict)
                                    else (r_data if isinstance(r_data, str) and "data:image" in r_data else "")
                                )
                                if qr_val:
                                    return {"success": True, "qr": qr_val}

                    clean_msg = clean_error_response(res.status_code, res.text)
                    return {
                        "success": False,
                        "statusCode": res.status_code,
                        "error": clean_msg,
                        "detail": clean_msg,
                        "is_gateway_unavailable": res.status_code in [502, 503, 504]
                    }
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                if attempt == 0:
                    logger.info("OpenWA connection probe timeout, retrying in 3s...")
                    await asyncio.sleep(3.0)
                    continue
                err_msg = f"Timed out waiting for OpenWA Gateway at {self.base_url}. Service may be waking up from Render sleep."
                return {"success": False, "error": err_msg, "statusCode": 504, "is_gateway_unavailable": True}
            except Exception as e:
                logger.error(f"Error fetching OpenWA QR code: {e}")
                return {"success": False, "error": str(e)}

        return {"success": False, "error": "Unable to fetch QR code after retries."}

    async def wake_gateway(self) -> Dict[str, Any]:
        """Send an active wake-up probe to OpenWA with extended timeout (up to 45s) to wake from Render sleep."""
        url = f"{self.base_url}/health"
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=40.0) as client:
                    res = await client.get(url)
                    if res.status_code in [200, 401, 404]:
                        return {
                            "success": True,
                            "is_awake": True,
                            "message": f"OpenWA Gateway at {self.base_url} is active and ready."
                        }
            except Exception as e:
                logger.info(f"Wake-up attempt {attempt + 1} notice: {e}")
                await asyncio.sleep(3.0)

        return {
            "success": False,
            "is_awake": False,
            "message": f"Could not wake OpenWA Gateway at {self.base_url} after multiple attempts."
        }

    async def create_or_start_session(self) -> Dict[str, Any]:
        """Create or initialize WhatsApp session on OpenWA gateway."""
        sid = await self.resolve_session_uuid()
        start_url = f"{self.base_url}/api/sessions/{sid}/start"
        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                res = await client.post(start_url, json={}, headers=self.get_auth_headers())
                if res.status_code in [200, 201]:
                    try:
                        return res.json()
                    except Exception:
                        return {"success": True, "status": "started"}
                # If 404, reset cached id and try again
                if res.status_code == 404:
                    self._resolved_session_id = None
                clean_msg = clean_error_response(res.status_code, res.text)
                return {
                    "success": False,
                    "statusCode": res.status_code,
                    "error": clean_msg,
                    "detail": clean_msg,
                    "is_gateway_unavailable": res.status_code in [502, 503, 504]
                }
        except httpx.ConnectError:
            err_msg = f"Cannot connect to OpenWA Gateway at {self.base_url}. Service is offline or unreachable."
            return {"success": False, "error": err_msg, "statusCode": 503, "is_gateway_unavailable": True}
        except httpx.TimeoutException:
            err_msg = f"Timed out connecting to OpenWA Gateway at {self.base_url}. Service may be starting up on Render."
            return {"success": False, "error": err_msg, "statusCode": 504, "is_gateway_unavailable": True}
        except Exception as e:
            logger.error(f"Error starting OpenWA session: {e}")
            return {"success": False, "error": str(e)}

    async def logout_session(self) -> Dict[str, Any]:
        """Log out / unlink WhatsApp device from OpenWA to allow pairing a new number."""
        sid = await self.resolve_session_uuid()
        url = f"{self.base_url}/api/sessions/{sid}/logout"
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                res = await client.post(url, json={}, headers=self.get_auth_headers())
                self._resolved_session_id = None
                if res.status_code in [200, 201, 204, 404]:
                    return {
                        "success": True,
                        "message": "WhatsApp device unlinked successfully. You can now scan a new QR code."
                    }
                clean_msg = clean_error_response(res.status_code, res.text)
                return {"success": False, "error": clean_msg}
        except Exception as e:
            logger.error(f"Error logging out OpenWA session: {e}")
            self._resolved_session_id = None
            return {"success": False, "error": str(e)}

    async def ensure_webhook_registered(self) -> Dict[str, Any]:
        """Ensure the backend webhook is actively registered on OpenWA for real-time customer replies."""
        webhook_target = getattr(settings, "PUBLIC_WEBHOOK_URL", None)
        if not webhook_target or any(s in webhook_target for s in ["trycloudflare", "ngrok", "your-"]):
            webhook_target = "http://host.docker.internal:8000"
        
        target_url = f"{webhook_target.rstrip('/')}/api/telephony/openwa/webhook"
        sid = await self.resolve_session_uuid()
        list_url = f"{self.base_url}/api/sessions/{sid}/webhooks"
        headers = self.get_auth_headers()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(list_url, headers=headers)
                if res.status_code == 200:
                    try:
                        existing = res.json()
                        if isinstance(existing, list):
                            for hook in existing:
                                if hook.get("url") == target_url and hook.get("active", True):
                                    return {"success": True, "already_registered": True, "webhook": hook}
                    except Exception:
                        pass
                # Register webhook
                create_payload = {
                    "url": target_url,
                    "events": ["*"]
                }
                c_res = await client.post(list_url, json=create_payload, headers=headers)
                if c_res.status_code in [200, 201]:
                    logger.info(f"Successfully registered OpenWA webhook to {target_url}")
                    return {"success": True, "registered": True, "webhook": c_res.json()}
                clean_msg = clean_error_response(c_res.status_code, c_res.text)
                logger.warning(f"Could not register OpenWA webhook: {c_res.status_code} - {clean_msg}")
                return {"success": False, "detail": clean_msg}
        except Exception as e:
            logger.warning(f"Notice on ensuring OpenWA webhook: {e}")
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
        sid = await self.resolve_session_uuid()
        url = f"{self.base_url}/api/sessions/{sid}/messages/send-text"
        payload = {
            "chatId": chat_id,
            "text": text
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(url, json=payload, headers=self.get_auth_headers())
                if res.status_code in [200, 201]:
                    return res.json()
                clean_msg = clean_error_response(res.status_code, res.text)
                logger.error(f"OpenWA send-text error: {res.status_code} - {clean_msg}")
                return {"success": False, "statusCode": res.status_code, "detail": clean_msg, "error": clean_msg}
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
        sid = await self.resolve_session_uuid()
        url = f"{self.base_url}/api/sessions/{sid}/messages/send-audio"
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
                clean_msg = clean_error_response(res.status_code, res.text)
                logger.error(f"OpenWA send-audio error: {res.status_code} - {clean_msg}")
                return {"success": False, "statusCode": res.status_code, "detail": clean_msg, "error": clean_msg}
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
