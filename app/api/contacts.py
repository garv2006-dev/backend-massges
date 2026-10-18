from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from app.database import get_db
from app.schemas.contact import Contact, ContactCreate, ContactUpdate, ContactImport
from app.schemas.common import MessageResponse
from app.repositories.contact import ContactRepository, ContactImportRepository
from app.services.excel_service import ExcelService
from app.core.deps import get_current_user
from app.utils.phone import normalize_phone_number
import uuid

router = APIRouter()
MAX_UPLOAD_SIZE = 25 * 1024 * 1024  # 25 MB limit

class BatchContactsCreate(BaseModel):
    contacts: List[ContactCreate] = Field(..., min_length=1, max_length=1000, description="List of contacts to create")

@router.post("/import", response_model=Dict[str, Any])
async def import_contacts(
    file: UploadFile = File(...),
    column_mapping: str = Form("{}"),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Import contacts from Excel or CSV file."""
    import json
    
    if not file.filename.lower().endswith(('.xlsx', '.xls', '.csv')):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be .xlsx, .xls, or .csv"
        )
    
    try:
        mapping = json.loads(column_mapping) if column_mapping else {}
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid column mapping JSON"
        )
    
    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Uploaded file exceeds maximum allowed limit of {MAX_UPLOAD_SIZE // (1024*1024)}MB."
        )

    excel_service = ExcelService(db)
    try:
        import_id, result = await excel_service.import_contacts(
            content,
            file.filename,
            mapping,
            created_by=current_user.id
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
    return {
        "import_id": str(import_id),
        **result
    }

@router.get("/imports", response_model=list[ContactImport])
async def list_imports(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """List contact imports."""
    import_repo = ContactImportRepository(db)
    imports = await import_repo.list(skip=skip, limit=limit, created_by=current_user.id)
    return imports

@router.get("", response_model=list[Contact])
async def list_contacts(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    import_id: uuid.UUID = None,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """List contacts."""
    contact_repo = ContactRepository(db)
    contacts = await contact_repo.list(skip=skip, limit=limit, import_id=import_id)
    return contacts

@router.get("/{contact_id}", response_model=Contact)
async def get_contact(
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get contact by ID."""
    contact_repo = ContactRepository(db)
    contact = await contact_repo.get_by_id(contact_id)
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found"
        )
    return contact

@router.post("", response_model=Contact, status_code=status.HTTP_201_CREATED)
async def create_contact(
    contact_create: ContactCreate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Create a new contact with phone validation and normalization."""
    contact_repo = ContactRepository(db)
    
    phone_normalized, error = normalize_phone_number(contact_create.phone_number)
    if error or not phone_normalized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid phone number: {error or 'Format error'}"
        )
    
    # Check for duplicates
    existing = await contact_repo.get_by_normalized_phone(phone_normalized)
    if existing:
        return existing
    
    contact = await contact_repo.create(contact_create, phone_normalized)
    return contact

@router.post("/batch", response_model=Dict[str, Any])
async def create_batch_contacts(
    batch: BatchContactsCreate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Batch create contacts with validation."""
    contact_repo = ContactRepository(db)
    created_list = []
    skipped_list = []

    for item in batch.contacts:
        phone_normalized, error = normalize_phone_number(item.phone_number)
        if error or not phone_normalized:
            skipped_list.append({"phone": item.phone_number, "reason": error or "Invalid format"})
            continue

        existing = await contact_repo.get_by_normalized_phone(phone_normalized)
        if existing:
            created_list.append(str(existing.id))
            continue

        c = await contact_repo.create(item, phone_normalized)
        created_list.append(str(c.id))

    return {
        "created_count": len(created_list),
        "skipped_count": len(skipped_list),
        "created_ids": created_list,
        "skipped": skipped_list
    }

@router.put("/{contact_id}", response_model=Contact)
async def update_contact(
    contact_id: uuid.UUID,
    contact_update: ContactUpdate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Update contact."""
    contact_repo = ContactRepository(db)
    contact = await contact_repo.update(contact_id, contact_update)
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found"
        )
    return contact

@router.delete("/{contact_id}", response_model=MessageResponse)
async def delete_contact(
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Delete contact."""
    contact_repo = ContactRepository(db)
    success = await contact_repo.delete(contact_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found"
        )
    return MessageResponse(message="Contact deleted successfully")
