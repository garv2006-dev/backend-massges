from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any
from app.database import get_db
from app.schemas.contact import Contact, ContactCreate, ContactUpdate, ContactImport, ContactImportCreate
from app.schemas.common import PaginationParams, PaginatedResponse, MessageResponse
from app.repositories.contact import ContactRepository, ContactImportRepository
from app.services.excel_service import ExcelService
from app.core.deps import get_current_user
import uuid

router = APIRouter()

@router.post("/import", response_model=Dict[str, Any])
async def import_contacts(
    file: UploadFile = File(...),
    column_mapping: str = "{}",  # JSON string of column mapping
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Import contacts from Excel file."""
    import json
    
    # Validate file type
    if not file.filename.endswith(('.xlsx', '.xls', '.csv')):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be .xlsx, .xls, or .csv"
        )
    
    # Parse column mapping
    try:
        mapping = json.loads(column_mapping)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid column mapping JSON"
        )
    
    # Read file content
    content = await file.read()
    
    # Import contacts
    excel_service = ExcelService(db)
    import_id, result = await excel_service.import_contacts(
        content,
        file.filename,
        mapping,
        created_by=current_user.id
    )
    
    return {
        "import_id": str(import_id),
        **result
    }

@router.get("/imports", response_model=list[ContactImport])
async def list_imports(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """List contact imports."""
    import_repo = ContactImportRepository(db)
    imports = await import_repo.list(skip=skip, limit=limit, created_by=current_user.id)
    return imports

@router.get("/imports/{import_id}", response_model=ContactImport)
async def get_import(
    import_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get contact import details."""
    import_repo = ContactImportRepository(db)
    import_record = await import_repo.get_by_id(import_id)
    if not import_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Import not found"
        )
    return import_record

@router.get("", response_model=list[Contact])
async def list_contacts(
    skip: int = 0,
    limit: int = 50,
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
    """Create a new contact."""
    from app.utils.phone import normalize_phone_number
    
    contact_repo = ContactRepository(db)
    
    # Normalize phone number
    phone_normalized, error = normalize_phone_number(contact_create.phone_number)
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error
        )
    
    # Check for duplicates
    is_duplicate = await contact_repo.check_duplicate(phone_normalized)
    if is_duplicate:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contact with this phone number already exists"
        )
    
    contact = await contact_repo.create(contact_create, phone_normalized)
    return contact

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
