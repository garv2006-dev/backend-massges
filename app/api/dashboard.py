from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case, literal_column, and_
from app.database import get_db
from app.schemas.common import DashboardStats
from app.core.deps import get_current_user
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.campaign_contact import CampaignContact, CampaignContactStatus
from app.models.whatsapp_message import WhatsAppMessage

router = APIRouter()

@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get dashboard statistics for WhatsApp broadcasts and messages."""
    
    # Total contacts
    contacts_result = await db.execute(select(func.count(Contact.id)))
    total_contacts = contacts_result.scalar() or 0
    
    # Total campaigns belonging to user or global default
    campaigns_result = await db.execute(
        select(func.count(Campaign.id)).where(
            (Campaign.created_by == current_user.id) | (Campaign.created_by.is_(None))
        )
    )
    total_campaigns = campaigns_result.scalar() or 0
    
    # Active campaigns (queued or in_progress)
    active_result = await db.execute(
        select(func.count(Campaign.id)).where(
            and_(
                Campaign.status.in_(["queued", "in_progress"]),
                (Campaign.created_by == current_user.id) | (Campaign.created_by.is_(None))
            )
        )
    )
    active_campaigns = active_result.scalar() or 0
    
    # Message / Broadcast dispatch statistics from CampaignContact
    dispatch_res = await db.execute(
        select(
            func.count(case((CampaignContact.status == CampaignContactStatus.QUEUED, literal_column("1")), else_=None)).label("queued"),
            func.count(case((CampaignContact.status == CampaignContactStatus.IN_PROGRESS, literal_column("1")), else_=None)).label("in_progress"),
            func.count(case((CampaignContact.status == CampaignContactStatus.COMPLETED, literal_column("1")), else_=None)).label("completed"),
            func.count(case((CampaignContact.status == CampaignContactStatus.FAILED, literal_column("1")), else_=None)).label("failed")
        )
    )
    disp = dispatch_res.first()
    
    # Total WhatsApp messages sent & delivered
    msg_res = await db.execute(
        select(
            func.count(case((WhatsAppMessage.direction == "outbound", literal_column("1")), else_=None)).label("outbound"),
            func.count(case((WhatsAppMessage.direction == "inbound", literal_column("1")), else_=None)).label("inbound")
        )
    )
    msg_stats = msg_res.first()
    
    completed_messages = (disp.completed if disp and disp.completed else 0) + (msg_stats.outbound if msg_stats and msg_stats.outbound else 0)
    inbound_replies = msg_stats.inbound if msg_stats and msg_stats.inbound else 0
    
    return DashboardStats(
        total_contacts=total_contacts,
        total_campaigns=total_campaigns,
        active_campaigns=active_campaigns,
        queued_calls=disp.queued if disp and disp.queued else 0,
        in_progress_calls=disp.in_progress if disp and disp.in_progress else 0,
        completed_calls=completed_messages,
        failed_calls=disp.failed if disp and disp.failed else 0,
        no_answer_calls=0,
        answered_calls=inbound_replies,
        average_call_duration=None,
        estimated_cost=None
    )
