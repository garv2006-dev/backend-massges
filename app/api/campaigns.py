from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app.database import get_db
from app.schemas.campaign import Campaign, CampaignCreate, CampaignUpdate, CampaignContact, CampaignContactCreate, CampaignStatus
from app.schemas.common import MessageResponse
from app.repositories.campaign import CampaignRepository, CampaignContactRepository
from app.services.excel_service import ExcelService
from app.core.deps import get_current_user
from fastapi.responses import Response
import uuid

router = APIRouter()

@router.get("", response_model=List[Campaign])
async def list_campaigns(
    skip: int = 0,
    limit: int = 50,
    status_filter: CampaignStatus = None,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """List campaigns."""
    campaign_repo = CampaignRepository(db)
    campaigns = await campaign_repo.list(
        skip=skip,
        limit=limit,
        created_by=current_user.id,
        status=status_filter.value if status_filter else None
    )
    return campaigns

@router.get("/{campaign_id}", response_model=Campaign)
async def get_campaign(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get campaign by ID."""
    campaign_repo = CampaignRepository(db)
    campaign = await campaign_repo.get_by_id(campaign_id)
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found"
        )
    return campaign

@router.post("", response_model=Campaign, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    campaign_create: CampaignCreate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Create a new campaign."""
    campaign_repo = CampaignRepository(db)
    campaign = await campaign_repo.create(campaign_create, created_by=current_user.id)
    return campaign

@router.put("/{campaign_id}", response_model=Campaign)
async def update_campaign(
    campaign_id: uuid.UUID,
    campaign_update: CampaignUpdate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Update campaign."""
    campaign_repo = CampaignRepository(db)
    campaign = await campaign_repo.update(campaign_id, campaign_update)
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found"
        )
    return campaign

@router.delete("/{campaign_id}", response_model=MessageResponse)
async def delete_campaign(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Delete campaign."""
    campaign_repo = CampaignRepository(db)
    success = await campaign_repo.delete(campaign_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found"
        )
    return MessageResponse(message="Campaign deleted successfully")

@router.post("/{campaign_id}/start", response_model=Campaign)
async def start_campaign(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Start a campaign."""
    campaign_repo = CampaignRepository(db)
    campaign = await campaign_repo.get_by_id(campaign_id)
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found"
        )
    
    if campaign.status != CampaignStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only start draft campaigns"
        )
    
    from datetime import datetime
    from app.schemas.campaign import CampaignUpdate
    updated = await campaign_repo.update(
        campaign_id,
        CampaignUpdate(
            status=CampaignStatus.QUEUED,
            start_time=datetime.utcnow()
        )
    )
    return updated

@router.post("/{campaign_id}/pause", response_model=Campaign)
async def pause_campaign(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Pause a campaign."""
    campaign_repo = CampaignRepository(db)
    campaign = await campaign_repo.get_by_id(campaign_id)
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found"
        )
    
    if campaign.status not in [CampaignStatus.QUEUED, CampaignStatus.IN_PROGRESS]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only pause queued or in-progress campaigns"
        )
    
    from app.schemas.campaign import CampaignUpdate
    updated = await campaign_repo.update(
        campaign_id,
        CampaignUpdate(status=CampaignStatus.PAUSED)
    )
    return updated

@router.post("/{campaign_id}/resume", response_model=Campaign)
async def resume_campaign(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Resume a paused campaign."""
    campaign_repo = CampaignRepository(db)
    campaign = await campaign_repo.get_by_id(campaign_id)
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found"
        )
    
    if campaign.status != CampaignStatus.PAUSED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only resume paused campaigns"
        )
    
    from app.schemas.campaign import CampaignUpdate
    updated = await campaign_repo.update(
        campaign_id,
        CampaignUpdate(status=CampaignStatus.QUEUED)
    )
    return updated

@router.post("/{campaign_id}/cancel", response_model=Campaign)
async def cancel_campaign(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Cancel a campaign."""
    campaign_repo = CampaignRepository(db)
    campaign = await campaign_repo.get_by_id(campaign_id)
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found"
        )
    
    if campaign.status in [CampaignStatus.COMPLETED, CampaignStatus.CANCELLED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot cancel completed or cancelled campaigns"
        )
    
    from datetime import datetime
    from app.schemas.campaign import CampaignUpdate
    updated = await campaign_repo.update(
        campaign_id,
        CampaignUpdate(
            status=CampaignStatus.CANCELLED,
            end_time=datetime.utcnow()
        )
    )
    return updated

@router.post("/{campaign_id}/contacts", response_model=List[CampaignContact])
async def add_contacts_to_campaign(
    campaign_id: uuid.UUID,
    contact_ids: List[uuid.UUID],
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Add contacts to a campaign."""
    campaign_repo = CampaignRepository(db)
    campaign = await campaign_repo.get_by_id(campaign_id)
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found"
        )
    
    cc_repo = CampaignContactRepository(db)
    campaign_contacts = await cc_repo.batch_create(campaign_id, contact_ids)
    
    # Update campaign stats
    await campaign_repo.update_stats(campaign_id)
    
    return campaign_contacts

@router.get("/{campaign_id}/contacts", response_model=List[CampaignContact])
async def list_campaign_contacts(
    campaign_id: uuid.UUID,
    skip: int = 0,
    limit: int = 50,
    status_filter: str = None,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """List campaign contacts."""
    cc_repo = CampaignContactRepository(db)
    contacts = await cc_repo.list(campaign_id, skip=skip, limit=limit, status=status_filter)
    return contacts

@router.get("/{campaign_id}/export")
async def export_campaign(
    campaign_id: uuid.UUID,
    include_transcripts: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Export campaign results to Excel."""
    excel_service = ExcelService(db)
    content = await excel_service.export_campaign_contacts(campaign_id, include_transcripts)
    
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=campaign_{campaign_id}_results.xlsx"}
    )
