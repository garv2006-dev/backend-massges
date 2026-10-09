from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case, literal_column
from app.database import get_db
from app.schemas.common import DashboardStats
from app.core.deps import get_current_user
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.call import Call

router = APIRouter()

@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get dashboard statistics."""
    
    # Total contacts
    contacts_result = await db.execute(select(func.count(Contact.id)))
    total_contacts = contacts_result.scalar() or 0
    
    # Total campaigns
    campaigns_result = await db.execute(select(func.count(Campaign.id)))
    total_campaigns = campaigns_result.scalar() or 0
    
    # Active campaigns (queued or in_progress)
    active_result = await db.execute(
        select(func.count(Campaign.id)).where(
            Campaign.status.in_(["queued", "in_progress"])
        )
    )
    active_campaigns = active_result.scalar() or 0
    
    # Call statistics
    calls_result = await db.execute(
        select(
            func.count(case((Call.status == "queued", literal_column("1")), else_=None)).label("queued"),
            func.count(case((Call.status == "in_progress", literal_column("1")), else_=None)).label("in_progress"),
            func.count(case((Call.status == "completed", literal_column("1")), else_=None)).label("completed"),
            func.count(case((Call.status == "failed", literal_column("1")), else_=None)).label("failed"),
            func.count(case((Call.status == "no_answer", literal_column("1")), else_=None)).label("no_answer"),
            func.count(case((Call.status == "completed", literal_column("1")), else_=None)).label("answered"),
            func.avg(Call.duration_seconds).label("avg_duration")
        )
    )
    call_stats = calls_result.first()
    
    return DashboardStats(
        total_contacts=total_contacts,
        total_campaigns=total_campaigns,
        active_campaigns=active_campaigns,
        queued_calls=call_stats.queued or 0,
        in_progress_calls=call_stats.in_progress or 0,
        completed_calls=call_stats.completed or 0,
        failed_calls=call_stats.failed or 0,
        no_answer_calls=call_stats.no_answer or 0,
        answered_calls=call_stats.answered or 0,
        average_call_duration=float(call_stats.avg_duration) if call_stats.avg_duration else None,
        estimated_cost=None  # Will be calculated from usage records
    )
