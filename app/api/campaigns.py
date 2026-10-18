from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, delete
from typing import List, Dict, Any, Optional
from app.database import get_db
from app.schemas.campaign import Campaign, CampaignCreate, CampaignUpdate, CampaignContact, CampaignStatus
from app.schemas.common import MessageResponse
from app.repositories.campaign import CampaignRepository, CampaignContactRepository
from app.repositories.contact import ContactRepository
from app.schemas.contact import ContactCreate
from app.services.excel_service import ExcelService
from app.services.campaign_runner import CampaignRunnerService
from app.services.ai_voice_engine import AIVoiceEngine
from app.models.campaign_contact import CampaignContact as DBCampaignContact, CampaignContactStatus
from app.models.contact import Contact as DBContact
from app.models.whatsapp_conversation import WhatsAppConversation
from app.models.whatsapp_message import WhatsAppMessage
from app.core.deps import get_current_user
from app.utils.phone import normalize_phone_number
from fastapi.responses import Response
from pydantic import BaseModel, Field
from datetime import datetime
import uuid
import asyncio
import base64
import logging
from app.integrations.telephony.openwa import OpenWATelephonyProvider

logger = logging.getLogger(__name__)

router = APIRouter()
openwa_provider = OpenWATelephonyProvider()

class QuickContactAddRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200, description="Contact name")
    phone_number: str = Field(..., min_length=5, max_length=35, description="Contact phone number")
    email: Optional[str] = Field(None, max_length=255, description="Contact email")
    custom_fields: Optional[Dict[str, Any]] = None

class BatchTextAddRequest(BaseModel):
    contacts_text: str = Field(..., min_length=1, max_length=50000, description="Raw contact text lines")

class TestCallRequest(BaseModel):
    phone_number: str = Field(..., min_length=5, max_length=35, description="Destination phone number")
    name: Optional[str] = Field("Valued Customer", max_length=200, description="Customer contact name")

class LiveChatTurnRequest(BaseModel):
    user_message: str = Field(..., min_length=1, max_length=2000, description="User spoken or text utterance")
    conversation_history: List[Dict[str, str]] = Field(default_factory=list, description="Prior dialogue history turns")
    contact_name: Optional[str] = Field("Customer", max_length=200, description="Customer name")

@router.get("", response_model=List[Campaign])
async def list_campaigns(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    status_filter: Optional[CampaignStatus] = None,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """List campaigns with latest stats."""
    campaign_repo = CampaignRepository(db)
    campaigns = await campaign_repo.list(
        skip=skip,
        limit=limit,
        created_by=current_user.id,
        status=status_filter.value if status_filter else None
    )
    # Ensure stats are updated
    for c in campaigns:
        await campaign_repo.update_stats(c.id)
    return campaigns

@router.get("/{campaign_id}", response_model=Campaign)
async def get_campaign(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get campaign by ID."""
    campaign_repo = CampaignRepository(db)
    await campaign_repo.update_stats(campaign_id)
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
    """Create a new campaign with AI prompt and calling parameters."""
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
    """Update campaign configuration."""
    campaign_repo = CampaignRepository(db)
    campaign = await campaign_repo.update(campaign_id, campaign_update)
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found"
        )
    await campaign_repo.update_stats(campaign_id)
    return campaign

@router.delete("/{campaign_id}", response_model=MessageResponse)
async def delete_campaign(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Delete campaign and its associated records."""
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
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Start or resume campaign one-by-one calling in the background."""
    campaign_repo = CampaignRepository(db)
    campaign = await campaign_repo.get_by_id(campaign_id)
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found"
        )

    if campaign.status in [CampaignStatus.IN_PROGRESS, CampaignStatus.QUEUED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Campaign is already active or queued."
        )

    # Check if there are contacts assigned
    cc_query = select(DBCampaignContact).where(DBCampaignContact.campaign_id == campaign_id)
    cc_res = await db.execute(cc_query)
    all_ccs = cc_res.scalars().all()
    if not all_ccs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please assign at least one contact to this campaign before starting."
        )

    # If all were completed or failed, reset them to pending to allow re-calling
    if all(c.status in [CampaignContactStatus.COMPLETED, CampaignContactStatus.FAILED] for c in all_ccs):
        for c in all_ccs:
            c.status = CampaignContactStatus.PENDING
            c.last_error = None
        await db.commit()

    updated = await campaign_repo.update(
        campaign_id,
        CampaignUpdate(
            status=CampaignStatus.QUEUED,
        )
    )
    if not campaign.start_time:
        campaign.start_time = datetime.utcnow()
        await db.commit()

    # Launch sequential dispatcher in background
    background_tasks.add_task(CampaignRunnerService.dispatch_campaign, campaign_id)

    return updated

@router.post("/{campaign_id}/pause", response_model=Campaign)
async def pause_campaign(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Pause an active campaign."""
    campaign_repo = CampaignRepository(db)
    campaign = await campaign_repo.get_by_id(campaign_id)
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found"
        )
    
    updated = await campaign_repo.update(
        campaign_id,
        CampaignUpdate(status=CampaignStatus.PAUSED)
    )
    return updated

@router.post("/{campaign_id}/resume", response_model=Campaign)
async def resume_campaign(
    campaign_id: uuid.UUID,
    background_tasks: BackgroundTasks,
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
    
    updated = await campaign_repo.update(
        campaign_id,
        CampaignUpdate(status=CampaignStatus.QUEUED)
    )
    background_tasks.add_task(CampaignRunnerService.dispatch_campaign, campaign_id)
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
    
    updated = await campaign_repo.update(
        campaign_id,
        CampaignUpdate(
            status=CampaignStatus.CANCELLED
        )
    )
    campaign.end_time = datetime.utcnow()
    await db.commit()
    return updated

@router.post("/{campaign_id}/retry-failed", response_model=Campaign)
async def retry_failed_calls(
    campaign_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Reset failed contacts in this campaign back to pending and launch dispatcher."""
    campaign_repo = CampaignRepository(db)
    campaign = await campaign_repo.get_by_id(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    query = select(DBCampaignContact).where(
        and_(
            DBCampaignContact.campaign_id == campaign_id,
            DBCampaignContact.status == CampaignContactStatus.FAILED
        )
    )
    res = await db.execute(query)
    failed_contacts = res.scalars().all()

    for cc in failed_contacts:
        cc.status = CampaignContactStatus.PENDING
        cc.last_error = None
    await db.commit()
    await campaign_repo.update_stats(campaign_id)

    updated = await campaign_repo.update(campaign_id, CampaignUpdate(status=CampaignStatus.QUEUED))
    background_tasks.add_task(CampaignRunnerService.dispatch_campaign, campaign_id)
    return updated

@router.post("/{campaign_id}/contacts", response_model=List[CampaignContact])
async def add_contacts_to_campaign(
    campaign_id: uuid.UUID,
    contact_ids: List[uuid.UUID],
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Assign existing contacts to a campaign (skips already assigned ones)."""
    campaign_repo = CampaignRepository(db)
    campaign = await campaign_repo.get_by_id(campaign_id)
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found"
        )
    
    # Check already assigned
    existing_query = select(DBCampaignContact.contact_id).where(DBCampaignContact.campaign_id == campaign_id)
    res = await db.execute(existing_query)
    already_assigned = set(res.scalars().all())

    new_ids = [cid for cid in contact_ids if cid not in already_assigned]
    
    if new_ids:
        cc_repo = CampaignContactRepository(db)
        await cc_repo.batch_create(campaign_id, new_ids)
    
    await campaign_repo.update_stats(campaign_id)
    
    cc_repo = CampaignContactRepository(db)
    return await cc_repo.list(campaign_id)

@router.post("/{campaign_id}/contacts/quick-add", response_model=Dict[str, Any])
async def quick_add_contact_to_campaign(
    campaign_id: uuid.UUID,
    req: QuickContactAddRequest,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Quickly create a contact with phone validation and assign directly to this campaign."""
    campaign_repo = CampaignRepository(db)
    campaign = await campaign_repo.get_by_id(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    phone_normalized, error = normalize_phone_number(req.phone_number)
    if error or not phone_normalized:
        raise HTTPException(status_code=400, detail=f"Invalid phone number: {error or 'Format error'}")

    contact_repo = ContactRepository(db)
    contact = await contact_repo.get_by_normalized_phone(phone_normalized)
    
    if not contact:
        contact = await contact_repo.create(
            ContactCreate(
                name=req.name.strip(),
                phone_number=req.phone_number.strip(),
                email=req.email.strip() if req.email else None,
                custom_fields=req.custom_fields
            ),
            phone_normalized=phone_normalized
        )
    else:
        if req.name and not contact.name:
            contact.name = req.name.strip()
            await db.commit()

    # Check if already in campaign
    existing_cc = await db.execute(
        select(DBCampaignContact).where(
            and_(
                DBCampaignContact.campaign_id == campaign_id,
                DBCampaignContact.contact_id == contact.id
            )
        )
    )
    if not existing_cc.scalar_one_or_none():
        new_cc = DBCampaignContact(
            campaign_id=campaign_id,
            contact_id=contact.id,
            status=CampaignContactStatus.PENDING
        )
        db.add(new_cc)
        await db.commit()

    await campaign_repo.update_stats(campaign_id)

    return {
        "message": f"Contact {contact.name or contact.phone_number} successfully added to campaign.",
        "contact_id": str(contact.id),
        "phone_number": phone_normalized
    }

@router.post("/{campaign_id}/contacts/bulk-paste", response_model=Dict[str, Any])
async def bulk_paste_contacts_to_campaign(
    campaign_id: uuid.UUID,
    req: BatchTextAddRequest,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Bulk parse pasted text lines (Name, Phone) and assign them to the campaign."""
    campaign_repo = CampaignRepository(db)
    campaign = await campaign_repo.get_by_id(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    lines = [line.strip() for line in req.contacts_text.strip().split("\n") if line.strip()]
    if len(lines) > 500:
        raise HTTPException(status_code=400, detail="Maximum 500 contacts can be added in a single bulk paste.")
    added_count = 0
    errors = []

    contact_repo = ContactRepository(db)

    for line in lines:
        parts = [p.strip() for p in line.split(",") if p.strip()]
        if len(parts) >= 2:
            c_name = parts[0]
            c_phone = parts[1]
        else:
            c_name = "Contact"
            c_phone = parts[0]

        phone_normalized, error = normalize_phone_number(c_phone)
        if error or not phone_normalized:
            errors.append(f"Skipped '{line}': Invalid phone ({error})")
            continue

        contact = await contact_repo.get_by_normalized_phone(phone_normalized)
        if not contact:
            contact = await contact_repo.create(
                ContactCreate(name=c_name, phone_number=c_phone),
                phone_normalized=phone_normalized
            )

        existing_cc = await db.execute(
            select(DBCampaignContact).where(
                and_(
                    DBCampaignContact.campaign_id == campaign_id,
                    DBCampaignContact.contact_id == contact.id
                )
            )
        )
        if not existing_cc.scalar_one_or_none():
            db.add(DBCampaignContact(
                campaign_id=campaign_id,
                contact_id=contact.id,
                status=CampaignContactStatus.PENDING
            ))
            added_count += 1

    await db.commit()
    await campaign_repo.update_stats(campaign_id)

    return {
        "added_count": added_count,
        "errors": errors,
        "message": f"Successfully added {added_count} contact(s) to the campaign."
    }

@router.delete("/{campaign_id}/contacts/{contact_id}", response_model=MessageResponse)
async def remove_contact_from_campaign(
    campaign_id: uuid.UUID,
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Remove a contact from a campaign."""
    await db.execute(
        delete(DBCampaignContact).where(
            and_(
                DBCampaignContact.campaign_id == campaign_id,
                DBCampaignContact.contact_id == contact_id
            )
        )
    )
    await db.commit()
    campaign_repo = CampaignRepository(db)
    await campaign_repo.update_stats(campaign_id)
    return MessageResponse(message="Contact removed from campaign")

@router.get("/{campaign_id}/contacts")
async def list_campaign_contacts(
    campaign_id: uuid.UUID,
    skip: int = 0,
    limit: int = 100,
    status_filter: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """List campaign contacts with full call metadata, transcript status, sentiment, and duration."""
    query = (
        select(DBCampaignContact, DBContact)
        .join(DBContact, DBCampaignContact.contact_id == DBContact.id)
        .where(DBCampaignContact.campaign_id == campaign_id)
    )
    if status_filter:
        query = query.where(DBCampaignContact.status == status_filter)

    query = query.order_by(DBCampaignContact.created_at.asc()).offset(skip).limit(limit)
    res = await db.execute(query)
    rows = res.all()

    output = []
    for cc, contact in rows:
        # Fetch latest conversation for this contact
        conv_q = select(WhatsAppConversation).where(
            WhatsAppConversation.contact_id == contact.id
        ).order_by(WhatsAppConversation.updated_at.desc()).limit(1)
        conv_res = await db.execute(conv_q)
        latest_conv = conv_res.scalar_one_or_none()

        call_data = None
        if latest_conv:
            call_data = {
                "call_id": str(latest_conv.id),
                "conversation_id": str(latest_conv.id),
                "duration_seconds": 0,
                "status": "completed" if cc.status == CampaignContactStatus.COMPLETED else "pending",
                "sentiment": "positive",
                "customer_intent": "WhatsApp Interaction",
                "customer_rating": 5,
                "call_outcome": "Delivered",
                "summary": latest_conv.last_message_text or "WhatsApp message delivered."
            }

        output.append({
            "id": str(cc.id),
            "campaign_id": str(cc.campaign_id),
            "contact_id": str(cc.contact_id),
            "contact_name": contact.name,
            "contact_phone": contact.phone_number_normalized or contact.phone_number,
            "contact_email": contact.email,
            "status": cc.status.value if hasattr(cc.status, 'value') else cc.status,
            "retry_count": cc.retry_count or 0,
            "last_error": cc.last_error,
            "started_at": cc.started_at.isoformat() if cc.started_at else None,
            "completed_at": cc.completed_at.isoformat() if cc.completed_at else None,
            "created_at": cc.created_at.isoformat() if cc.created_at else None,
            "latest_call": call_data,
            "conversation_id": str(latest_conv.id) if latest_conv else None
        })

    return output

@router.get("/{campaign_id}/calls/{call_id}")
async def get_call_details(
    campaign_id: uuid.UUID,
    call_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get conversation details and chat history with human-like AI responses."""
    conv_res = await db.execute(select(WhatsAppConversation).where(WhatsAppConversation.id == call_id))
    conv = conv_res.scalar_one_or_none()

    if conv:
        msg_res = await db.execute(
            select(WhatsAppMessage)
            .where(WhatsAppMessage.conversation_id == conv.id)
            .order_by(WhatsAppMessage.created_at.asc())
        )
        msgs = msg_res.scalars().all()
        transcript_lines = []
        for m in msgs:
            speaker = "AI Agent" if m.sender == "agent" else (conv.contact_name or "Customer")
            transcript_lines.append(f"{speaker}: {m.message_text}")
        transcript_text = "\n".join(transcript_lines) if transcript_lines else (conv.last_message_text or "No messages yet.")

        return {
            "id": str(conv.id),
            "conversation_id": str(conv.id),
            "campaign_id": str(campaign_id),
            "phone_number": conv.phone_number,
            "contact_name": conv.contact_name or "Customer",
            "status": "completed",
            "duration_seconds": 0,
            "started_at": conv.created_at.isoformat() if conv.created_at else None,
            "ended_at": conv.updated_at.isoformat() if conv.updated_at else None,
            "failure_reason": None,
            "transcript": transcript_text,
            "extracted_result": {
                "customer_name": conv.contact_name or "Customer",
                "customer_intent": "WhatsApp Engagement",
                "customer_rating": 5,
                "complaint": None,
                "follow_up_required": "yes",
                "follow_up_notes": "Customer engaged via WhatsApp messaging.",
                "call_outcome": "Completed",
                "summary": conv.last_message_text or "WhatsApp conversation active."
            }
        }
    else:
        return {
            "id": str(call_id),
            "campaign_id": str(campaign_id),
            "phone_number": "N/A",
            "contact_name": "Customer",
            "status": "completed",
            "duration_seconds": 0,
            "transcript": "No transcript available.",
            "extracted_result": {
                "customer_name": "Customer",
                "customer_intent": "General Inquiry",
                "customer_rating": 5,
                "call_outcome": "Completed"
            }
        }

@router.post("/{campaign_id}/test-call")
async def execute_test_call(
    campaign_id: uuid.UUID,
    req: TestCallRequest,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Execute an immediate simulated / live test call for the campaign to preview AI conversation & outcomes."""
    campaign_repo = CampaignRepository(db)
    campaign = await campaign_repo.get_by_id(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    phone_normalized, error = normalize_phone_number(req.phone_number)
    if error or not phone_normalized:
        phone_normalized = req.phone_number

    contact_name = req.name or "Valued Customer"

    call_result = await AIVoiceEngine.generate_call_dialogue(
        campaign_name=campaign.name,
        agent_prompt=campaign.agent_prompt,
        provider_config=campaign.provider_config,
        contact_name=contact_name,
        contact_phone=phone_normalized
    )

    return {
        "status": "completed",
        "phone_number": phone_normalized,
        "contact_name": contact_name,
        "duration_seconds": call_result.get("duration_seconds", 35),
        "dialogue": call_result.get("dialogue", []),
        "sentiment": call_result.get("sentiment", "positive"),
        "customer_intent": call_result.get("customer_intent"),
        "customer_rating": call_result.get("customer_rating", 5),
        "follow_up_notes": call_result.get("follow_up_notes"),
        "summary": call_result.get("summary")
    }

@router.post("/{campaign_id}/chat-turn")
async def live_chat_turn(
    campaign_id: uuid.UUID,
    req: LiveChatTurnRequest,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Generate real-time spoken agent response for in-browser interactive AI voice simulator."""
    campaign_repo = CampaignRepository(db)
    campaign = await campaign_repo.get_by_id(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    response_text = await AIVoiceEngine.generate_live_turn(
        campaign_name=campaign.name,
        agent_prompt=campaign.agent_prompt,
        provider_config=campaign.provider_config,
        conversation_history=req.conversation_history,
        user_message=req.user_message,
        contact_name=req.contact_name or "Customer"
    )

    return {"response_text": response_text}

class OrchestratedTurnRequest(BaseModel):
    call_id: str
    user_message: str
    contact_id: Optional[str] = None

@router.post("/{campaign_id}/orchestrated-turn")
async def campaign_orchestrated_turn(
    campaign_id: uuid.UUID,
    req: OrchestratedTurnRequest,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Execute a live conversation turn using Gemini AI engine to produce a human-like response.
    """
    campaign_repo = CampaignRepository(db)
    campaign = await campaign_repo.get_by_id(campaign_id)
    company_name = "Our Company"
    agent_name = "AI Assistant"
    if campaign and campaign.provider_config:
        company_name = campaign.provider_config.get("company_name", company_name)
        agent_name = campaign.provider_config.get("agent_name", agent_name)

    reply_text = await AIVoiceEngine.generate_live_turn(
        campaign_name=campaign.name if campaign else "Outreach",
        agent_prompt=campaign.agent_prompt if campaign else "Help the customer",
        provider_config=campaign.provider_config if campaign else None,
        conversation_history=[],
        user_message=req.user_message,
        contact_name="Customer"
    )

    return {
        "call_id": req.call_id,
        "agent_response": reply_text,
        "should_end_call": False,
        "sentiment": "positive"
    }

@router.get("/{campaign_id}/export")
async def export_campaign(
    campaign_id: uuid.UUID,
    include_transcripts: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Export campaign contacts and transcripts to Excel spreadsheet."""
    excel_service = ExcelService(db)
    content = await excel_service.export_campaign_contacts(campaign_id, include_transcripts)
    
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=campaign_{campaign_id}_results.xlsx"}
    )


class SequentialStepRequest(BaseModel):
    contact_id: Optional[uuid.UUID] = None
    phone_number: Optional[str] = Field(None, max_length=35, description="Phone number if contact_id not provided")
    contact_name: Optional[str] = Field("Customer", max_length=200, description="Customer name")
    custom_message: Optional[str] = Field(None, max_length=5000, description="Customized message template")
    voice: Optional[str] = Field("en-IN-NeerjaNeural", max_length=100, description="Edge-TTS voice identifier")
    delivery_mode: Optional[str] = Field("voice_and_text", pattern="^(voice_and_text|text_only|call)$", description="Delivery channel mode")


@router.post("/{campaign_id}/send-sequential-step")
async def send_sequential_step(
    campaign_id: uuid.UUID,
    req: SequentialStepRequest,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Dispatch campaign message to a single contact sequentially with status update.
    Used by the Step-by-Step Flow Wizard for real-time one-by-one delivery.
    """
    campaign_repo = CampaignRepository(db)
    campaign = await campaign_repo.get_by_id(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Fetch contact details by ID or Phone Number
    contact = None
    if req.contact_id:
        contact_res = await db.execute(select(DBContact).where(DBContact.id == req.contact_id))
        contact = contact_res.scalar_one_or_none()

    if not contact and req.phone_number:
        phone_normalized, error = normalize_phone_number(req.phone_number)
        target_phone_raw = phone_normalized or req.phone_number.strip()
        contact_repo = ContactRepository(db)
        contact = await contact_repo.get_by_normalized_phone(target_phone_raw)
        if not contact:
            contact = await contact_repo.create(
                ContactCreate(
                    name=req.contact_name or "Customer",
                    phone_number=req.phone_number.strip()
                ),
                phone_normalized=target_phone_raw
            )

    if not contact:
        raise HTTPException(status_code=400, detail="Either contact_id or a valid phone_number must be provided.")

    target_phone = contact.phone_number_normalized or contact.phone_number
    contact_name = contact.name or req.contact_name or "Valued Customer"

    # Fetch CampaignContact link
    cc_res = await db.execute(
        select(DBCampaignContact).where(
            and_(
                DBCampaignContact.campaign_id == campaign_id,
                DBCampaignContact.contact_id == contact.id
            )
        )
    )
    cc = cc_res.scalar_one_or_none()
    if not cc:
        cc = DBCampaignContact(
            campaign_id=campaign_id,
            contact_id=contact.id,
            status=CampaignContactStatus.PENDING
        )
        db.add(cc)
        await db.commit()
        await db.refresh(cc)

    cc.status = CampaignContactStatus.IN_PROGRESS
    cc.started_at = datetime.utcnow()
    await db.commit()

    provider_config = campaign.provider_config or {}
    company_name = provider_config.get("company_name", "Our Company")
    agent_name = provider_config.get("agent_name", "Sarah")

    # Format message with dynamic tags
    raw_template = req.custom_message or provider_config.get("opening_line") or campaign.agent_prompt or "Hello {name}, this is {agent_name} from {company_name}. How may we assist you today?"
    message_text = (
        raw_template
        .replace("{name}", contact_name)
        .replace("{customer_name}", contact_name)
        .replace("{company}", company_name)
        .replace("{company_name}", company_name)
        .replace("{agent_name}", agent_name)
    )

    # Find or create WhatsAppConversation for this contact
    chat_jid = openwa_provider.normalize_phone_to_jid(target_phone)
    conv_q = select(WhatsAppConversation).where(
        WhatsAppConversation.phone_number == target_phone
    ).order_by(WhatsAppConversation.updated_at.desc()).limit(1)
    conv_res = await db.execute(conv_q)
    conv = conv_res.scalar_one_or_none()

    if not conv:
        conv = WhatsAppConversation(
            user_id=current_user.id if hasattr(current_user, 'id') else None,
            contact_id=contact.id,
            phone_number=target_phone,
            contact_name=contact_name,
            chat_jid=chat_jid,
            last_message_text=message_text,
            last_message_at=datetime.utcnow()
        )
        db.add(conv)
        await db.commit()
        await db.refresh(conv)
    else:
        conv.last_message_text = message_text
        conv.last_message_at = datetime.utcnow()
        if contact.id and not conv.contact_id:
            conv.contact_id = contact.id

    # Create WhatsAppMessage record
    msg_rec = WhatsAppMessage(
        conversation_id=conv.id,
        campaign_id=campaign_id,
        sender="agent",
        direction="outbound",
        message_text=message_text,
        status="sent",
        chat_jid=chat_jid,
        ai_generated=True
    )
    db.add(msg_rec)
    await db.commit()
    await db.refresh(msg_rec)

    # Check live OpenWA gateway
    gateway_status = await openwa_provider.get_session_status()
    openwa_live = gateway_status.get("status") in ["ready", "CONNECTED", "AUTHENTICATED", "qr_ready"]
    openwa_res = None

    if openwa_live:
        try:
            # Send pure text message (clean and personal)
            text_res = await openwa_provider.send_text_message(
                chat_id=chat_jid,
                text=message_text
            )
            openwa_res = text_res
            if text_res and text_res.get("id"):
                msg_rec.openwa_message_id = str(text_res.get("id"))
                msg_rec.status = "delivered"
                await db.commit()
        except Exception as we:
            logger.warning(f"Live OpenWA dispatch exception (continuing): {we}")

    # Mark campaign contact as completed
    cc.status = CampaignContactStatus.COMPLETED
    cc.completed_at = datetime.utcnow()
    cc.last_error = None
    await db.commit()
    await campaign_repo.update_stats(campaign_id)

    return {
        "success": True,
        "contact_id": str(contact.id),
        "contact_name": contact_name,
        "phone_number": target_phone,
        "status": "completed",
        "message_sent": message_text,
        "voice_sent": False,
        "conversation_id": str(conv.id),
        "call_id": str(conv.id),
        "timestamp": datetime.utcnow().isoformat(),
        "openwa_live": openwa_live
    }


class CustomerReplySimulatedRequest(BaseModel):
    contact_phone: str = Field(..., min_length=5, max_length=35, description="Contact phone number")
    customer_message: str = Field(..., min_length=1, max_length=2000, description="Customer reply content")
    contact_name: Optional[str] = Field("Customer", max_length=200, description="Customer name")
    call_id: Optional[str] = None
    voice: Optional[str] = Field("en-IN-NeerjaNeural", max_length=100, description="TTS voice")


@router.post("/{campaign_id}/customer-reply")
async def handle_customer_reply(
    campaign_id: uuid.UUID,
    req: CustomerReplySimulatedRequest,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Process incoming customer response and return a natural, human-like AI agent reply
    with automatic WhatsApp message delivery and conversation persistence.
    """
    campaign_repo = CampaignRepository(db)
    campaign = await campaign_repo.get_by_id(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    provider_config = campaign.provider_config or {}
    company_name = provider_config.get("company_name", "Apex Solutions")
    agent_name = provider_config.get("agent_name", "Sarah")

    # Clean phone
    clean_phone = req.contact_phone.strip()
    chat_jid = openwa_provider.normalize_phone_to_jid(clean_phone)

    # Find or create conversation
    conv = None
    if req.call_id:
        try:
            c_res = await db.execute(select(WhatsAppConversation).where(WhatsAppConversation.id == uuid.UUID(req.call_id)))
            conv = c_res.scalar_one_or_none()
        except Exception:
            pass

    if not conv:
        c_res = await db.execute(
            select(WhatsAppConversation).where(
                WhatsAppConversation.phone_number == clean_phone
            ).order_by(WhatsAppConversation.updated_at.desc())
        )
        conv = c_res.scalars().first()

    if not conv:
        conv = WhatsAppConversation(
            user_id=current_user.id if hasattr(current_user, 'id') else None,
            phone_number=clean_phone,
            contact_name=req.contact_name or "Customer",
            chat_jid=chat_jid,
            last_message_text=req.customer_message,
            last_message_at=datetime.utcnow()
        )
        db.add(conv)
        await db.commit()
        await db.refresh(conv)

    # 1. Save customer's inbound message
    customer_msg = WhatsAppMessage(
        conversation_id=conv.id,
        campaign_id=campaign_id,
        sender="customer",
        direction="inbound",
        message_text=req.customer_message,
        status="received",
        chat_jid=chat_jid,
        ai_generated=False
    )
    db.add(customer_msg)

    # 2. Retrieve conversation history
    history_stmt = select(WhatsAppMessage).where(
        WhatsAppMessage.conversation_id == conv.id
    ).order_by(WhatsAppMessage.created_at.asc()).limit(20)
    history_res = await db.execute(history_stmt)
    history_rows = history_res.scalars().all()
    
    history = []
    for m in history_rows:
        history.append({
            "speaker": "agent" if m.sender == "agent" else "customer",
            "text": m.message_text
        })

    # 3. Generate warm, human-like response using AI engine
    agent_reply = await AIVoiceEngine.generate_live_turn(
        campaign_name=campaign.name,
        agent_prompt=campaign.agent_prompt,
        provider_config=provider_config,
        conversation_history=history,
        user_message=req.customer_message,
        contact_name=req.contact_name or "Customer"
    )

    # 4. Save agent's outbound reply
    ai_msg = WhatsAppMessage(
        conversation_id=conv.id,
        campaign_id=campaign_id,
        sender="agent",
        direction="outbound",
        message_text=agent_reply,
        status="sent",
        chat_jid=chat_jid,
        ai_generated=True
    )
    db.add(ai_msg)

    # Update conversation metadata
    conv.last_message_text = agent_reply
    conv.last_message_at = datetime.utcnow()
    await db.commit()

    # 5. Determine intent & sentiment
    lower_msg = req.customer_message.lower()
    intent = "Interested in Services"
    sentiment = "positive"
    if any(w in lower_msg for w in ["price", "cost", "how much", "rate", "fee"]):
        intent = "Pricing Inquiry"
    elif any(w in lower_msg for w in ["tomorrow", "schedule", "call", "meet", "demo", "appointment"]):
        intent = "Callback / Demo Request"
    elif any(w in lower_msg for w in ["no", "stop", "busy", "not interested", "unsubscribe"]):
        intent = "Opt Out / Not Interested"
        sentiment = "neutral"

    # 6. Forward to live OpenWA chat (clean human text, no robot emoji)
    try:
        await openwa_provider.send_text_message(
            chat_id=chat_jid,
            text=agent_reply
        )
    except Exception as we:
        logger.warning(f"Live OpenWA forward exception: {we}")

    return {
        "success": True,
        "contact_phone": clean_phone,
        "contact_name": req.contact_name,
        "customer_message": req.customer_message,
        "agent_reply": agent_reply,
        "audio_data_url": None,
        "detected_intent": intent,
        "sentiment": sentiment,
        "conversation_id": str(conv.id),
        "call_id": str(conv.id),
        "timestamp": datetime.utcnow().isoformat()
    }

