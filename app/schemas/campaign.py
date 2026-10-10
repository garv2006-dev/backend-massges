from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime
import uuid
from enum import Enum

class CampaignStatus(str, Enum):
    DRAFT = "draft"
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"

class CampaignBase(BaseModel):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    agent_prompt: Optional[str] = None
    max_call_duration: int = Field(default=300, gt=0)
    max_retries: int = Field(default=3, ge=0, le=10)
    concurrency_limit: int = Field(default=5, gt=0, le=50)
    provider_config: Optional[Dict[str, Any]] = None

class CampaignCreate(CampaignBase):
    pass

class CampaignUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    status: Optional[CampaignStatus] = None
    agent_prompt: Optional[str] = None
    max_call_duration: Optional[int] = Field(None, gt=0)
    max_retries: Optional[int] = Field(None, ge=0, le=10)
    concurrency_limit: Optional[int] = Field(None, gt=0, le=50)
    provider_config: Optional[Dict[str, Any]] = None

class CampaignInDB(CampaignBase):
    id: uuid.UUID
    status: CampaignStatus
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    total_contacts: int
    queued_calls: int
    in_progress_calls: int
    completed_calls: int
    failed_calls: int
    no_answer_calls: int
    answered_calls: int
    created_by: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class Campaign(CampaignInDB):
    pass

class CampaignContactBase(BaseModel):
    campaign_id: uuid.UUID
    contact_id: uuid.UUID

class CampaignContactCreate(CampaignContactBase):
    pass

class CampaignContactInDB(BaseModel):
    id: uuid.UUID
    campaign_id: uuid.UUID
    contact_id: uuid.UUID
    status: str
    retry_count: int
    last_error: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None

    class Config:
        from_attributes = True

class CampaignContact(CampaignContactInDB):
    pass
