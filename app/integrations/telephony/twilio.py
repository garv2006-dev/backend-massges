"""Twilio Telephony Provider.

Twilio only maintains the telecom phone connection.
All audio processing (Deepgram STT, LangGraph/Gemini LLM, Text-to-Speech)
is completely managed in real time by our AI Agent.
"""

import os
import urllib.parse
import logging
from typing import Dict, Any, Optional
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from app.integrations.telephony.base import TelephonyProvider
from app.config import settings

logger = logging.getLogger(__name__)

class TwilioTelephonyProvider(TelephonyProvider):
    """
    Streamlined Twilio Telephony Integration.
    Twilio handles telephony dialing and media transport.
    The AI Agent handles live speech recognition, intelligence, and speech synthesis.
    """

    def __init__(
        self,
        account_sid: Optional[str] = None,
        auth_token: Optional[str] = None,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        from_number: Optional[str] = None
    ):
        self.account_sid = account_sid or settings.TWILIO_ACCOUNT_SID
        self.auth_token = auth_token or settings.TWILIO_AUTH_TOKEN
        self.api_key = api_key or settings.TWILIO_API_KEY
        self.api_secret = api_secret or settings.TWILIO_API_SECRET
        self.from_number = from_number or settings.TWILIO_PHONE_NUMBER

        # Initialize Twilio Client via API Key/Secret or Account SID/Auth Token
        if self.api_key and self.api_secret and self.account_sid:
            logger.info("Initializing Twilio client with API Key and Secret")
            self.client = Client(self.api_key, self.api_secret, self.account_sid)
        elif self.account_sid and self.auth_token:
            logger.info("Initializing Twilio client with Account SID and Auth Token")
            self.client = Client(self.account_sid, self.auth_token)
        else:
            logger.warning("Twilio credentials not fully configured")
            self.client = None

    async def create_call(
        self,
        to_number: str,
        from_number: Optional[str] = None,
        speech_text: Optional[str] = None,
        voice: str = "Polly.Aditi",
        language: str = "en-IN",
        webhook_url: Optional[str] = None,
        status_callback_url: Optional[str] = None,
        twiml_url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Initiate an outbound call and connect it to the Agent.
        Uses clean URL parameter fully compatible with Twilio trial and upgraded accounts.
        """
        if not self.client:
            raise ValueError("Twilio client is not configured with valid credentials")

        caller_id = from_number or self.from_number
        if not caller_id:
            raise ValueError("Twilio 'from_number' is required to make outbound calls")

        call_args: Dict[str, Any] = {
            "to": to_number,
            "from_": caller_id,
        }

        # Determine target webhook / TwiML URL
        target_call_id = (metadata or {}).get("call_id")
        resolved_url = webhook_url or twiml_url

        if not resolved_url and settings.PUBLIC_WEBHOOK_URL:
            base_url = settings.PUBLIC_WEBHOOK_URL.rstrip('/')
            if target_call_id:
                resolved_url = f"{base_url}/api/telephony/twiml/{target_call_id}"
            else:
                resolved_url = f"{base_url}/api/telephony/twiml/default"

        if not resolved_url:
            raise ValueError(
                "Twilio requires a public webhook URL to connect live phone audio to your AI Agent on localhost. "
                "Please configure PUBLIC_WEBHOOK_URL in backend/.env (e.g. your ngrok or cloudflare tunnel URL like https://xxxx.trycloudflare.com)"
            )

        call_args["url"] = resolved_url

        if status_callback_url:
            call_args["status_callback"] = status_callback_url

        try:
            logger.info(f"Initiating Twilio call to {to_number} from {caller_id} using url {resolved_url}")
            call = self.client.calls.create(**call_args)
            return {
                "provider_call_id": call.sid,
                "status": call.status,
                "to": call.to,
                "from": call.from_formatted or caller_id,
                "direction": call.direction,
            }
        except TwilioRestException as e:
            logger.error(f"Twilio API error making call to {to_number}: {e.msg} (code: {e.code})")
            raise e
        except Exception as e:
            logger.error(f"Unexpected error making Twilio call to {to_number}: {str(e)}")
            raise e

    async def create_streaming_call(
        self,
        to_number: str,
        stream_url: str,
        from_number: Optional[str] = None,
        status_callback_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Initiate a call that connects directly to our Agent's live WebSocket.
        Twilio acts purely as the telecom audio pipe.
        """
        if not self.client:
            raise ValueError("Twilio client is not configured")

        caller_id = from_number or self.from_number
        if not caller_id:
            raise ValueError("Twilio from_number is required")

        if not settings.PUBLIC_WEBHOOK_URL:
            raise ValueError(
                "PUBLIC_WEBHOOK_URL must be configured in backend/.env to establish a live media stream with Twilio."
            )

        base_url = settings.PUBLIC_WEBHOOK_URL.rstrip('/')
        target_url = f"{base_url}/api/telephony/twiml/stream"

        call_args: Dict[str, Any] = {
            "to": to_number,
            "from_": caller_id,
            "url": target_url,
        }
        if status_callback_url:
            call_args["status_callback"] = status_callback_url

        try:
            logger.info(f"Initiating Media Stream call to {to_number} connecting to {stream_url}")
            call = self.client.calls.create(**call_args)
            return {
                "provider_call_id": call.sid,
                "status": call.status,
                "to": call.to,
                "from": call.from_formatted or caller_id,
                "stream_url": stream_url
            }
        except Exception as e:
            logger.error(f"Failed to create streaming call to {to_number}: {e}")
            raise e

    async def get_call_status(self, provider_call_id: str) -> Dict[str, Any]:
        """Fetch current status of a Twilio call."""
        if not self.client:
            raise ValueError("Twilio client is not configured")
        try:
            call = self.client.calls(provider_call_id).fetch()
            return {
                "provider_call_id": call.sid,
                "status": call.status,
                "duration": int(call.duration) if call.duration else 0,
                "start_time": call.start_time.isoformat() if call.start_time else None,
                "end_time": call.end_time.isoformat() if call.end_time else None,
            }
        except Exception as e:
            logger.error(f"Failed to fetch Twilio call status {provider_call_id}: {str(e)}")
            raise e

    async def end_call(self, provider_call_id: str) -> bool:
        """Hang up an active Twilio call."""
        if not self.client:
            return False
        try:
            call = self.client.calls(provider_call_id).update(status="completed")
            return call.status == "completed"
        except Exception as e:
            logger.error(f"Failed to end Twilio call {provider_call_id}: {str(e)}")
            return False

    def validate_webhook(self, headers: Dict[str, str], body: bytes) -> bool:
        return True

    async def handle_call_event(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "provider_call_id": event_data.get("CallSid"),
            "status": event_data.get("CallStatus"),
            "duration": event_data.get("CallDuration"),
            "answered_by": event_data.get("AnsweredBy"),
        }

    async def start_media_stream(self, provider_call_id: str, stream_url: str) -> bool:
        return True

    @property
    def provider_name(self) -> str:
        return "twilio"

    async def list_messages(self, limit: int = 20) -> list:
        """List recent SMS messages using official Twilio Client."""
        if not self.client:
            raise ValueError("Twilio client is not configured")
        try:
            messages = self.client.messages.list(limit=limit)
            return [
                {
                    "sid": m.sid,
                    "from": m.from_,
                    "to": m.to,
                    "body": m.body,
                    "status": m.status,
                    "date_sent": m.date_sent.isoformat() if m.date_sent else None,
                    "direction": m.direction,
                }
                for m in messages
            ]
        except Exception as e:
            logger.error(f"Failed to list Twilio messages: {e}")
            raise e

    async def get_message(self, message_sid: str) -> Dict[str, Any]:
        """Fetch details of a single message by SID."""
        if not self.client:
            raise ValueError("Twilio client is not configured")
        try:
            m = self.client.messages(message_sid).fetch()
            return {
                "sid": m.sid,
                "from": m.from_,
                "to": m.to,
                "body": m.body,
                "status": m.status,
                "date_sent": m.date_sent.isoformat() if m.date_sent else None,
            }
        except Exception as e:
            logger.error(f"Failed to fetch Twilio message {message_sid}: {e}")
            raise e

    async def send_sms(self, to_number: str, body: str, from_number: Optional[str] = None) -> Dict[str, Any]:
        """Send an SMS text message using Twilio."""
        if not self.client:
            raise ValueError("Twilio client is not configured")
        caller_id = from_number or self.from_number
        try:
            msg = self.client.messages.create(
                to=to_number,
                from_=caller_id,
                body=body
            )
            return {
                "sid": msg.sid,
                "status": msg.status,
                "to": msg.to,
                "from": msg.from_,
                "body": msg.body
            }
        except Exception as e:
            logger.error(f"Failed to send Twilio SMS to {to_number}: {e}")
            raise e

    @property
    def supports_streaming(self) -> bool:
        return True

    @property
    def supports_india_domestic(self) -> bool:
        return True
