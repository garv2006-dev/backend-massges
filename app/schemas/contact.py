from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime
import uuid

class ContactBase(BaseModel):
    phone_number: str = Field(..., max_length=20)
    name: Optional[str] = None
    email: Optional[str] = None
    language: str = "en"
    custom_fields: Optional[Dict[str, Any]] = None

class ContactCreate(ContactBase):
    pass

class ContactUpdate(BaseModel):
    phone_number: Optional[str] = Field(None, max_length=20)
    name: Optional[str] = None
    email: Optional[str] = None
    language: Optional[str] = None
    custom_fields: Optional[Dict[str, Any]] = None
    validation_status: Optional[str] = None

class ContactInDB(ContactBase):
    id: uuid.UUID
    import_id: Optional[uuid.UUID] = None
    phone_number_normalized: str
    validation_status: str
    validation_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class Contact(ContactInDB):
    pass

class ContactImportCreate(BaseModel):
    file_name: str
    file_size: int
    row_count: int
    column_mapping: Optional[str] = None

class ContactImportUpdate(BaseModel):
    status: Optional[str] = None
    success_count: Optional[int] = None
    failure_count: Optional[int] = None
    duplicate_count: Optional[int] = None
    error_message: Optional[str] = None

class ContactImportInDB(BaseModel):
    id: uuid.UUID
    file_name: str
    file_size: int
    row_count: int
    success_count: int
    failure_count: int
    duplicate_count: int
    status: str
    error_message: Optional[str] = None
    column_mapping: Optional[str] = None
    created_by: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class ContactImport(ContactImportInDB):
    pass
