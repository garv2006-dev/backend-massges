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
from app.models.call import Call, CallStatus, CallDirection
from app.models.transcript import Transcript
from app.models.extracted_call_result import ExtractedCallResult
from app.integrations.telephony.openwa import OpenWATelephonyProvider
from app.repositories.campaign import CampaignRepository
from app.services.ai_voice_engine import AIVoiceEngine
from app.config import settings

logger = logging.getLogger(__name__)

class CampaignRunnerService:
    @staticmethod
    async def dispatch_campaign(campaign_id: uuid.UUID):
        """
        Background task to process contacts for a campaign one-by-one,
        simulating / executing the AI voice call, generating dialogue transcripts,
        and extracting actionable business insights.
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

            # Initialize OpenWA Telephony Provider (WhatsApp Gateway)
            openwa_provider = None
            try:
                openwa_provider = OpenWATelephonyProvider()
            except Exception as e:
                logger.info(f"OpenWA provider initialization notice: {e}")

            provider_config = campaign.provider_config or {}
            # Check if OpenWA mode is requested (defaults to True if configured or explicitly requested)
            use_openwa = provider_config.get("use_openwa", provider_config.get("use_real_twilio", False))

            for cc, contact in pending_items:
                # Check if campaign was paused or cancelled by employee
                await db.refresh(campaign)
                if campaign.status in [CampaignStatus.PAUSED, CampaignStatus.CANCELLED]:
                    logger.info(f"Campaign {campaign_id} was {campaign.status}, halting one-by-one execution.")
                    break

                target_phone = getattr(contact, 'phone_number_normalized', None) or contact.phone_number
                contact_name = contact.name or "Customer"

                # Step 1: Mark as IN_PROGRESS (Ringing & Calling)
                cc.status = CampaignContactStatus.IN_PROGRESS
                cc.started_at = datetime.utcnow()
                await db.commit()
                await campaign_repo.update_stats(campaign_id)

                call_record = Call(
                    campaign_id=campaign_id,
                    campaign_contact_id=cc.id,
                    contact_id=contact.id,
                    phone_number=target_phone,
                    direction=CallDirection.OUTBOUND,
                    status=CallStatus.IN_PROGRESS,
                    started_at=datetime.utcnow(),
                    provider="openwa" if (use_openwa and openwa_provider) else "ai_voice_engine"
                )
                db.add(call_record)
                await db.commit()
                await db.refresh(call_record)

                try:
                    # If real OpenWA WhatsApp calling mode is active
                    if use_openwa and openwa_provider:
                        opening_line = (
                            provider_config.get("opening_line")
                            or f"Hello {contact_name}! This is {provider_config.get('agent_name', 'AI Assistant')} calling from {provider_config.get('company_name', 'our company')}. How may I help you today?"
                        )

                        try:
                            res = await openwa_provider.create_call(
                                phone_number=target_phone,
                                speech_text=opening_line,
                                voice=provider_config.get("voice", "en-IN-NeerjaNeural"),
                                metadata={
                                    "call_id": str(call_record.id),
                                    "campaign_id": str(campaign_id),
                                    "contact_id": str(contact.id)
                                }
                            )
                            call_record.provider_call_id = res.get("provider_call_id")
                            call_record.status = CallStatus.IN_PROGRESS
                            cc.status = CampaignContactStatus.IN_PROGRESS

                            # Record opening message turn in Transcript
                            timestamp_str = datetime.utcnow().strftime("%M:%S")
                            tr = Transcript(
                                call_id=call_record.id,
                                full_transcript=f"[{timestamp_str}] AI Agent: {opening_line}",
                                word_count=len(opening_line.split()),
                                language_detected=provider_config.get("language", "English")
                            )
                            db.add(tr)
                            logger.info(f"OpenWA WhatsApp call initiated to {target_phone} (Message ID: {res.get('provider_call_id')})")
                        except Exception as oe:
                            logger.error(f"OpenWA call failed to {target_phone}: {oe}")
                            clean_err = f"OpenWA Gateway Error: {str(oe)}. Ensure OpenWA Docker container is running on http://localhost:2785."

                            call_record.status = CallStatus.FAILED
                            call_record.failure_reason = clean_err
                            call_record.ended_at = datetime.utcnow()

                            cc.status = CampaignContactStatus.FAILED
                            cc.last_error = clean_err
                            cc.retry_count = (cc.retry_count or 0) + 1
                            await db.commit()
                            await campaign_repo.update_stats(campaign_id)
                            continue

                    else:
                        # Simulation / Demo Mode (No real telephony)
                        call_result = await AIVoiceEngine.generate_call_dialogue(
                            campaign_name=campaign.name,
                            agent_prompt=campaign.agent_prompt,
                            provider_config=provider_config,
                            contact_name=contact_name,
                            contact_phone=target_phone,
                            custom_fields=contact.custom_fields
                        )

                        dialogue_turns = call_result.get("dialogue", [])
                        formatted_transcript = "\n".join([
                            f"[{turn.get('timestamp', '00:00')}] {'AI Agent' if turn.get('speaker') == 'agent' else contact_name}: {turn.get('text', '')}"
                            for turn in dialogue_turns
                        ])

                        transcript_record = Transcript(
                            call_id=call_record.id,
                            full_transcript=formatted_transcript,
                            word_count=len(formatted_transcript.split()),
                            language_detected=provider_config.get("language", "English")
                        )
                        db.add(transcript_record)

                        extracted_record = ExtractedCallResult(
                            call_id=call_record.id,
                            customer_name=contact_name,
                            customer_intent=call_result.get("customer_intent", "Interested"),
                            customer_rating=call_result.get("customer_rating", 5),
                            complaint=call_result.get("complaint"),
                            follow_up_required=call_result.get("follow_up_required", "yes"),
                            follow_up_notes=call_result.get("follow_up_notes", "Follow-up requested."),
                            call_outcome=call_result.get("call_outcome", "Completed"),
                            raw_extracted_data=call_result,
                            validation_status="validated"
                        )
                        db.add(extracted_record)

                        duration = min(call_result.get("duration_seconds", 40), campaign.max_call_duration or 300)
                        call_record.duration_seconds = duration
                        call_record.status = CallStatus.COMPLETED
                        call_record.ended_at = datetime.utcnow()
                        call_record.ai_interactions = len(dialogue_turns)
                        call_record.ai_confidence_score = 95

                        cc.status = CampaignContactStatus.COMPLETED
                        cc.completed_at = datetime.utcnow()
                        cc.last_error = None

                except Exception as e:
                    logger.error(f"Error executing AI call to {target_phone}: {str(e)}")
                    call_record.status = CallStatus.FAILED
                    call_record.failure_reason = str(e)
                    call_record.ended_at = datetime.utcnow()
                    
                    cc.status = CampaignContactStatus.FAILED
                    cc.last_error = str(e)
                    cc.retry_count = (cc.retry_count or 0) + 1

                await db.commit()
                await campaign_repo.update_stats(campaign_id)

                # Delay between one-by-one calls for realism & rate-limiting
                await asyncio.sleep(1.5)

            # Final status update
            await campaign_repo.update_stats(campaign_id)
            campaign = await campaign_repo.get_by_id(campaign_id)
            if campaign and campaign.status == CampaignStatus.IN_PROGRESS:
                if campaign.queued_calls == 0 and campaign.in_progress_calls == 0:
                    campaign.status = CampaignStatus.COMPLETED
                    campaign.end_time = datetime.utcnow()
                    await db.commit()
