"""Pydantic validation schemas for LangGraph Agent Tools."""

from typing import Optional, Any
from pydantic import BaseModel, Field, field_validator
import re

class GetContactDetailsInput(BaseModel):
    contact_id: str = Field(description="UUID of the contact to look up.")
    organization_id: Optional[str] = Field(default=None, description="Organization ID for data isolation enforcement.")

class GetCampaignContextInput(BaseModel):
    campaign_id: str = Field(description="UUID of the campaign.")
    organization_id: Optional[str] = Field(default=None, description="Organization ID for authorization.")

class SaveConversationFieldInput(BaseModel):
    call_id: str = Field(description="Active Call UUID.")
    field_name: str = Field(min_length=1, max_length=100, description="Clean field name, e.g. 'preferred_time', 'budget', 'interest_level'.")
    field_value: Any = Field(description="The extracted response value.")
    confidence_score: Optional[float] = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0.")

    @field_validator("field_name")
    @classmethod
    def sanitize_field_name(cls, v: str) -> str:
        clean = re.sub(r'[^a-zA-Z0-9_\-]', '', v).strip()
        if not clean:
            raise ValueError("Invalid field name characters")
        return clean

class SaveCallResultInput(BaseModel):
    call_id: str = Field(description="Active Call UUID.")
    customer_name: Optional[str] = Field(default=None, description="Name of the customer engaged.")
    customer_intent: Optional[str] = Field(default=None, description="Customer primary intent.")
    customer_rating: Optional[int] = Field(default=5, ge=1, le=5, description="Engagement rating 1 to 5.")
    call_outcome: str = Field(description="Final outcome of the call, e.g. 'Interested', 'Opt-Out', 'Callback Requested'.")
    follow_up_required: Optional[str] = Field(default="no", description="'yes', 'no', or 'maybe'.")
    follow_up_notes: Optional[str] = Field(default=None, description="Specific follow up action or notes.")
    complaint: Optional[str] = Field(default=None, description="Customer complaint or grievance if any.")

class ScheduleFollowUpInput(BaseModel):
    call_id: str = Field(description="Active Call UUID.")
    contact_id: str = Field(description="Contact UUID.")
    scheduled_iso: str = Field(description="ISO 8601 formatted datetime string for when to schedule the callback.")
    channel: Optional[str] = Field(default="voice", description="Callback channel: voice, whatsapp, email, or sms.")
    notes: Optional[str] = Field(default=None, description="Notes or agenda for the follow-up.")

class TransferToHumanInput(BaseModel):
    call_id: str = Field(description="Active Call UUID.")
    reason: str = Field(description="Explanation of why human agent assistance is requested.")
    department: Optional[str] = Field(default="support", description="Department to transfer to: 'sales', 'support', 'escalations'.")

class EndCallInput(BaseModel):
    call_id: str = Field(description="Active Call UUID.")
    hangup_reason: str = Field(description="Reason for ending the call, e.g. 'Goal Completed', 'Customer Requested Stop', 'Customer Busy'.")
    customer_consented_or_opt_out: bool = Field(default=False, description="True if customer explicitly requested opt-out or conclusion.")

class GetCallStatusInput(BaseModel):
    call_id: str = Field(description="Active Call UUID.")
