from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime
import uuid

class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None
    is_active: bool = True
    is_superuser: bool = False
    onboarding_completed: bool = False

class UserCreate(UserBase):
    password: str = Field(..., min_length=8)

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None
    onboarding_completed: Optional[bool] = None

class UserInDB(UserBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class User(UserInDB):
    pass

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: Optional[int] = 604800  # 7 days in seconds
    onboarding_completed: Optional[bool] = False
    user: Optional[User] = None

class TokenData(BaseModel):
    user_id: Optional[uuid.UUID] = None
