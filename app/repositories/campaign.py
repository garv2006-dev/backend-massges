from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from app.models.campaign import Campaign
from app.models.campaign_contact import CampaignContact
from app.schemas.campaign import CampaignCreate, CampaignUpdate, CampaignContactCreate
import uuid

class CampaignRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, campaign_id: uuid.UUID) -> Optional[Campaign]:
        result = await self.db.execute(select(Campaign).where(Campaign.id == campaign_id))
        return result.scalar_one_or_none()

    async def create(self, campaign_create: CampaignCreate, created_by: Optional[uuid.UUID] = None) -> Campaign:
        db_campaign = Campaign(
            name=campaign_create.name,
            description=campaign_create.description,
            agent_prompt=campaign_create.agent_prompt,
            max_call_duration=campaign_create.max_call_duration,
            max_retries=campaign_create.max_retries,
            concurrency_limit=campaign_create.concurrency_limit,
            provider_config=campaign_create.provider_config,
            created_by=created_by,
            status="draft"
        )
        self.db.add(db_campaign)
        await self.db.commit()
        await self.db.refresh(db_campaign)
        return db_campaign

    async def update(self, campaign_id: uuid.UUID, campaign_update: CampaignUpdate) -> Optional[Campaign]:
        db_campaign = await self.get_by_id(campaign_id)
        if not db_campaign:
            return None
        
        update_data = campaign_update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_campaign, field, value)
        
        await self.db.commit()
        await self.db.refresh(db_campaign)
        return db_campaign

    async def delete(self, campaign_id: uuid.UUID) -> bool:
        db_campaign = await self.get_by_id(campaign_id)
        if not db_campaign:
            return False
        
        await self.db.delete(db_campaign)
        await self.db.commit()
        return True

    async def list(self, skip: int = 0, limit: int = 100, created_by: Optional[uuid.UUID] = None, status: Optional[str] = None) -> List[Campaign]:
        query = select(Campaign)
        if created_by:
            query = query.where(Campaign.created_by == created_by)
        if status:
            query = query.where(Campaign.status == status)
        result = await self.db.execute(query.order_by(Campaign.created_at.desc()).offset(skip).limit(limit))
        return result.scalars().all()

    async def update_stats(self, campaign_id: uuid.UUID) -> Optional[Campaign]:
        db_campaign = await self.get_by_id(campaign_id)
        if not db_campaign:
            return None
        
        # Update stats from campaign_contacts
        result = await self.db.execute(
            select(CampaignContact.status, func.count(CampaignContact.id))
            .where(CampaignContact.campaign_id == campaign_id)
            .group_by(CampaignContact.status)
        )
        status_counts = {row[0]: row[1] for row in result.all()}
        
        db_campaign.total_contacts = sum(status_counts.values())
        db_campaign.queued_calls = status_counts.get("queued", 0)
        db_campaign.in_progress_calls = status_counts.get("in_progress", 0)
        db_campaign.completed_calls = status_counts.get("completed", 0)
        db_campaign.failed_calls = status_counts.get("failed", 0)
        
        await self.db.commit()
        await self.db.refresh(db_campaign)
        return db_campaign

class CampaignContactRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, campaign_contact_id: uuid.UUID) -> Optional[CampaignContact]:
        result = await self.db.execute(select(CampaignContact).where(CampaignContact.id == campaign_contact_id))
        return result.scalar_one_or_none()

    async def create(self, campaign_contact_create: CampaignContactCreate) -> CampaignContact:
        db_campaign_contact = CampaignContact(
            campaign_id=campaign_contact_create.campaign_id,
            contact_id=campaign_contact_create.contact_id,
            status="pending"
        )
        self.db.add(db_campaign_contact)
        await self.db.commit()
        await self.db.refresh(db_campaign_contact)
        return db_campaign_contact

    async def batch_create(self, campaign_id: uuid.UUID, contact_ids: List[uuid.UUID]) -> List[CampaignContact]:
        campaign_contacts = [
            CampaignContact(campaign_id=campaign_id, contact_id=contact_id, status="pending")
            for contact_id in contact_ids
        ]
        self.db.add_all(campaign_contacts)
        await self.db.commit()
        for cc in campaign_contacts:
            await self.db.refresh(cc)
        return campaign_contacts

    async def update(self, campaign_contact_id: uuid.UUID, status: str, last_error: Optional[str] = None) -> Optional[CampaignContact]:
        db_cc = await self.get_by_id(campaign_contact_id)
        if not db_cc:
            return None
        
        db_cc.status = status
        if last_error:
            db_cc.last_error = last_error
        
        await self.db.commit()
        await self.db.refresh(db_cc)
        return db_cc

    async def list(self, campaign_id: uuid.UUID, skip: int = 0, limit: int = 100, status: Optional[str] = None) -> List[CampaignContact]:
        query = select(CampaignContact).where(CampaignContact.campaign_id == campaign_id)
        if status:
            query = query.where(CampaignContact.status == status)
        result = await self.db.execute(query.offset(skip).limit(limit))
        return result.scalars().all()

    async def get_next_pending(self, campaign_id: uuid.UUID, limit: int = 5) -> List[CampaignContact]:
        result = await self.db.execute(
            select(CampaignContact)
            .where(and_(
                CampaignContact.campaign_id == campaign_id,
                CampaignContact.status == "pending"
            ))
            .limit(limit)
        )
        return result.scalars().all()
