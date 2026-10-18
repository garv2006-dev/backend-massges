from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import uuid
from enum import Enum

class CallStatus(str, Enum):
    QUEUED = "queued"
    RINGING = "ringing"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    NO_ANSWER = "no_answer"
    BUSY = "busy"
    CANCELLED = "cancelled"
    REJECTED = "rejected"

class CallDirection(str, Enum):
    OUTBOUND = "outbound"
    INBOUND = "inbound"

class CallBase(BaseModel):
    phone_number: str = Field(..., max_length=20)
    direction: CallDirection = CallDirection.OUTBOUND

class CallCreate(CallBase):
    campaign_id: Optional[uuid.UUID] = None
    campaign_contact_id: Optional[uuid.UUID] = None
    contact_id: Optional[uuid.UUID] = None

class CallUpdate(BaseModel):
    status: Optional[CallStatus] = None
    provider_call_id: Optional[str] = None
    provider: Optional[str] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    failure_reason: Optional[str] = None
    hangup_cause: Optional[str] = None
    ai_interactions: Optional[int] = None
    ai_confidence_score: Optional[int] = None

class CallInDB(CallBase):
    id: uuid.UUID
    campaign_id: Optional[uuid.UUID] = None
    campaign_contact_id: Optional[uuid.UUID] = None
    contact_id: Optional[uuid.UUID] = None
    provider_call_id: Optional[str] = None
    provider: Optional[str] = None
    status: CallStatus
    queued_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    failure_reason: Optional[str] = None
    hangup_cause: Optional[str] = None
    ai_interactions: int
    ai_confidence_score: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class Call(CallInDB):
    pass



class TranscriptBase(BaseModel):
    full_transcript: Optional[str] = None
    word_count: int = 0
    language_detected: Optional[str] = None

class TranscriptCreate(TranscriptBase):
    call_id: uuid.UUID

class TranscriptInDB(TranscriptBase):
    id: uuid.UUID
    call_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class Transcript(TranscriptInDB):
    pass

class ExtractedCallResultBase(BaseModel):
    customer_name: Optional[str] = None
    customer_intent: Optional[str] = None
    customer_rating: Optional[int] = Field(None, ge=1, le=5)
    complaint: Optional[str] = None
    follow_up_required: Optional[str] = None
    follow_up_notes: Optional[str] = None
    call_outcome: Optional[str] = None
    raw_extracted_data: Optional[dict] = None

class ExtractedCallResultCreate(ExtractedCallResultBase):
    call_id: uuid.UUID

class ExtractedCallResultInDB(ExtractedCallResultBase):
    id: uuid.UUID
    call_id: uuid.UUID
    validation_status: str
    validation_errors: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class ExtractedCallResult(ExtractedCallResultInDB):
    pass
