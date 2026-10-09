from pydantic import BaseModel, Field
from typing import Optional, Generic, TypeVar, List
from datetime import datetime

T = TypeVar('T')

class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=100)

class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    page_size: int
    total_pages: int

class DashboardStats(BaseModel):
    total_contacts: int
    total_campaigns: int
    active_campaigns: int
    queued_calls: int
    in_progress_calls: int
    completed_calls: int
    failed_calls: int
    no_answer_calls: int
    answered_calls: int
    average_call_duration: Optional[float] = None
    estimated_cost: Optional[float] = None

class MessageResponse(BaseModel):
    message: str
    success: bool = True
