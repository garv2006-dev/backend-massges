from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from app.models.contact import Contact
from app.models.contact_import import ContactImport
from app.schemas.contact import ContactCreate, ContactUpdate, ContactImportCreate, ContactImportUpdate
import uuid

class ContactRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, contact_id: uuid.UUID) -> Optional[Contact]:
        result = await self.db.execute(select(Contact).where(Contact.id == contact_id))
        return result.scalar_one_or_none()

    async def get_by_normalized_phone(self, phone_normalized: str) -> Optional[Contact]:
        result = await self.db.execute(
            select(Contact).where(Contact.phone_number_normalized == phone_normalized)
        )
        return result.scalar_one_or_none()

    async def create(self, contact_create: ContactCreate, phone_normalized: str, import_id: Optional[uuid.UUID] = None) -> Contact:
        db_contact = Contact(
            phone_number=contact_create.phone_number,
            phone_number_normalized=phone_normalized,
            name=contact_create.name,
            email=contact_create.email,
            language=contact_create.language,
            custom_fields=contact_create.custom_fields,
            import_id=import_id,
            validation_status="valid"
        )
        self.db.add(db_contact)
        await self.db.commit()
        await self.db.refresh(db_contact)
        return db_contact

    async def update(self, contact_id: uuid.UUID, contact_update: ContactUpdate) -> Optional[Contact]:
        db_contact = await self.get_by_id(contact_id)
        if not db_contact:
            return None
        
        update_data = contact_update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_contact, field, value)
        
        await self.db.commit()
        await self.db.refresh(db_contact)
        return db_contact

    async def delete(self, contact_id: uuid.UUID) -> bool:
        db_contact = await self.get_by_id(contact_id)
        if not db_contact:
            return False
        
        await self.db.delete(db_contact)
        await self.db.commit()
        return True

    async def list(self, skip: int = 0, limit: int = 100, import_id: Optional[uuid.UUID] = None) -> List[Contact]:
        query = select(Contact)
        if import_id:
            query = query.where(Contact.import_id == import_id)
        result = await self.db.execute(query.offset(skip).limit(limit))
        return result.scalars().all()

    async def check_duplicate(self, phone_normalized: str, exclude_id: Optional[uuid.UUID] = None) -> bool:
        query = select(Contact).where(Contact.phone_number_normalized == phone_normalized)
        if exclude_id:
            query = query.where(Contact.id != exclude_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none() is not None

class ContactImportRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, import_id: uuid.UUID) -> Optional[ContactImport]:
        result = await self.db.execute(select(ContactImport).where(ContactImport.id == import_id))
        return result.scalar_one_or_none()

    async def create(self, import_create: ContactImportCreate, created_by: Optional[uuid.UUID] = None) -> ContactImport:
        db_import = ContactImport(
            file_name=import_create.file_name,
            file_size=import_create.file_size,
            row_count=import_create.row_count,
            column_mapping=import_create.column_mapping,
            created_by=created_by,
            status="processing"
        )
        self.db.add(db_import)
        await self.db.commit()
        await self.db.refresh(db_import)
        return db_import

    async def update(self, import_id: uuid.UUID, import_update: ContactImportUpdate) -> Optional[ContactImport]:
        db_import = await self.get_by_id(import_id)
        if not db_import:
            return None
        
        update_data = import_update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_import, field, value)
        
        await self.db.commit()
        await self.db.refresh(db_import)
        return db_import

    async def list(self, skip: int = 0, limit: int = 100, created_by: Optional[uuid.UUID] = None) -> List[ContactImport]:
        query = select(ContactImport)
        if created_by:
            query = query.where(ContactImport.created_by == created_by)
        result = await self.db.execute(query.order_by(ContactImport.created_at.desc()).offset(skip).limit(limit))
        return result.scalars().all()
