from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from datetime import datetime
import uuid

class TelephonyProvider(ABC):
    """Base interface for telephony providers."""
    
    @abstractmethod
    async def create_call(
        self,
        phone_number: str,
        caller_id: str,
        webhook_url: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Initiate an outbound call.
        
        Args:
            phone_number: The destination phone number (E.164 format)
            caller_id: The caller ID to display
            webhook_url: URL for call status webhooks
            metadata: Additional metadata for the call
        
        Returns:
            Dict containing provider_call_id and initial status
        """
        pass
    
    @abstractmethod
    async def get_call_status(self, provider_call_id: str) -> Dict[str, Any]:
        """
        Get the current status of a call.
        
        Args:
            provider_call_id: The provider's call ID
        
        Returns:
            Dict containing status and call details
        """
        pass
    
    @abstractmethod
    async def end_call(self, provider_call_id: str) -> bool:
        """
        End an active call.
        
        Args:
            provider_call_id: The provider's call ID
        
        Returns:
            True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    def validate_webhook(self, headers: Dict[str, str], body: bytes) -> bool:
        """
        Validate webhook signature.
        
        Args:
            headers: HTTP headers from the webhook
            body: Raw webhook body
        
        Returns:
            True if valid, False otherwise
        """
        pass
    
    @abstractmethod
    async def handle_call_event(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a call event from webhook.
        
        Args:
            event_data: Parsed webhook event data
        
        Returns:
            Normalized event data
        """
        pass
    
    @abstractmethod
    async def start_media_stream(self, provider_call_id: str, stream_url: str) -> bool:
        """
        Start streaming media to the call (for AI integration).
        
        Args:
            provider_call_id: The provider's call ID
            stream_url: URL to stream media from
        
        Returns:
            True if successful, False otherwise
        """
        pass
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider name."""
        pass
    
    @property
    @abstractmethod
    def supports_streaming(self) -> bool:
        """Return whether the provider supports media streaming."""
        pass
    
    @property
    @abstractmethod
    def supports_india_domestic(self) -> bool:
        """Return whether the provider supports India domestic calls."""
        pass
