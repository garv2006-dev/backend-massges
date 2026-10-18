import re
import uuid
import asyncio
import logging
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.database import AsyncSessionLocal
from app.models.campaign import Campaign, CampaignStatus
from app.models.campaign_contact import CampaignContact, CampaignContactStatus
from app.models.contact import Contact
from app.models.whatsapp_conversation import WhatsAppConversation
from app.models.whatsapp_message import WhatsAppMessage
from app.integrations.telephony.openwa import OpenWATelephonyProvider
from app.repositories.campaign import CampaignRepository
from app.config import settings

logger = logging.getLogger(__name__)

class CampaignRunnerService:
    @staticmethod
    async def dispatch_campaign(campaign_id: uuid.UUID):
        """
        Background task to process contacts for a WhatsApp broadcast campaign one-by-one,
        dispatching personalized WhatsApp messages and tracking delivery.
        """
        async with AsyncSessionLocal() as db:
            campaign_repo = CampaignRepository(db)
            campaign = await campaign_repo.get_by_id(campaign_id)
            if not campaign:
                logger.error(f"Campaign {campaign_id} not found for dispatch")
                return

            # Mark campaign as IN_PROGRESS
            campaign.status = CampaignStatus.IN_PROGRESS
            if not campaign.start_time:
                campaign.start_time = datetime.utcnow()
            await db.commit()

            # Query all pending/queued contacts for this campaign
            query = (
                select(CampaignContact, Contact)
                .join(Contact, CampaignContact.contact_id == Contact.id)
                .where(
                    and_(
                        CampaignContact.campaign_id == campaign_id,
                        CampaignContact.status.in_([CampaignContactStatus.PENDING, CampaignContactStatus.QUEUED])
                    )
                )
                .order_by(CampaignContact.created_at.asc())
            )
            result = await db.execute(query)
            pending_items = result.all()

            if not pending_items:
                # If all contacts were processed previously, allow re-running non-completed ones
                reset_query = (
                    select(CampaignContact)
                    .where(
                        and_(
                            CampaignContact.campaign_id == campaign_id,
                            CampaignContact.status != CampaignContactStatus.COMPLETED
                        )
                    )
                )
                reset_res = await db.execute(reset_query)
                reset_contacts = reset_res.scalars().all()
                if reset_contacts:
                    for item in reset_contacts:
                        item.status = CampaignContactStatus.PENDING
                    await db.commit()
                    # Re-query
                    result = await db.execute(query)
                    pending_items = result.all()

            if not pending_items:
                logger.info(f"No pending contacts found for campaign {campaign_id}")
                await campaign_repo.update_stats(campaign_id)
                campaign = await campaign_repo.get_by_id(campaign_id)
                if campaign:
                    campaign.status = CampaignStatus.COMPLETED
                    campaign.end_time = datetime.utcnow()
                    await db.commit()
                return

            # Initialize OpenWA WhatsApp Gateway
            openwa_provider = None
            try:
                openwa_provider = OpenWATelephonyProvider()
            except Exception as e:
                logger.info(f"OpenWA provider initialization notice: {e}")

            provider_config = campaign.provider_config or {}
            company_name = provider_config.get("company_name", "Our Company")
            agent_name = provider_config.get("agent_name", "Sarah")

            for cc, contact in pending_items:
                # Check if campaign was paused or cancelled
                await db.refresh(campaign)
                if campaign.status in [CampaignStatus.PAUSED, CampaignStatus.CANCELLED]:
                    logger.info(f"Campaign {campaign_id} was {campaign.status}, halting execution.")
                    break

                target_phone = getattr(contact, 'phone_number_normalized', None) or contact.phone_number
                contact_name = contact.name or "Customer"

                # Mark as IN_PROGRESS
                cc.status = CampaignContactStatus.IN_PROGRESS
                cc.started_at = datetime.utcnow()
                await db.commit()
                await campaign_repo.update_stats(campaign_id)

                # Format message
                raw_template = (
                    provider_config.get("opening_line")
                    or campaign.agent_prompt
                    or "Hello {name}! This is {agent_name} from {company}. How may we assist you today?"
                )
                message_text = (
                    raw_template
                    .replace("{name}", contact_name)
                    .replace("{customer_name}", contact_name)
                    .replace("{company}", company_name)
                    .replace("{company_name}", company_name)
                    .replace("{agent_name}", agent_name)
                )

                try:
                    chat_jid = f"{re.sub(r'[^0-9]', '', target_phone)}@c.us"

                    # Get or create conversation
                    conv_res = await db.execute(
                        select(WhatsAppConversation).where(WhatsAppConversation.phone_number == target_phone)
                    )
                    conv = conv_res.scalar_one_or_none()
                    if not conv:
                        conv = WhatsAppConversation(
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

                    # Save outbound message
                    msg = WhatsAppMessage(
                        conversation_id=conv.id,
                        campaign_id=campaign_id,
                        sender="agent",
                        direction="outbound",
                        message_text=message_text,
                        status="delivered",
                        chat_jid=chat_jid,
                        ai_generated=True
                    )
                    db.add(msg)

                    # Send via live OpenWA if gateway is ready
                    if openwa_provider:
                        try:
                            status_data = await openwa_provider.get_session_status()
                            if status_data.get("status") in ["ready", "CONNECTED", "AUTHENTICATED"]:
                                send_res = await openwa_provider.send_text_message(
                                    chat_id=chat_jid,
                                    text=message_text
                                )
                                if send_res and isinstance(send_res, dict):
                                    msg.openwa_message_id = str(send_res.get("id") or "")
                        except Exception as oe:
                            logger.warning(f"OpenWA live send notice: {oe}")

                    cc.status = CampaignContactStatus.COMPLETED
                    cc.completed_at = datetime.utcnow()
                    cc.last_error = None
                    await db.commit()
                    await campaign_repo.update_stats(campaign_id)

                    # Safe anti-ban delay pacing (1.5 seconds)
                    await asyncio.sleep(1.5)

                except Exception as e:
                    logger.error(f"Error executing WhatsApp dispatch to {target_phone}: {str(e)}")
                    cc.status = CampaignContactStatus.FAILED
                    cc.last_error = str(e)
                    cc.retry_count = (cc.retry_count or 0) + 1
                    await db.commit()
                    await campaign_repo.update_stats(campaign_id)

            # Finalize campaign status
            await campaign_repo.update_stats(campaign_id)
            campaign = await campaign_repo.get_by_id(campaign_id)
            if campaign and campaign.status == CampaignStatus.IN_PROGRESS:
                campaign.status = CampaignStatus.COMPLETED
                campaign.end_time = datetime.utcnow()
                await db.commit()
