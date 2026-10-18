"""High-level Orchestration Service for LangGraph Voice Agent."""

import uuid
import logging
from typing import Dict, Any, Optional, List
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.call import Call, CallStatus
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.transcript import Transcript
from app.models.extracted_call_result import ExtractedCallResult
from app.agent.audio_pipeline import AudioPipelineManager
from app.agent.graph.builder import build_voice_agent_graph
from app.agent.graph.checkpointer import get_stable_thread_id, get_checkpointer

logger = logging.getLogger(__name__)

class VoiceAgentOrchestrator:
    """
    Central API for dispatching voice turns, managing call state,
    and querying conversation state and checkpoints.
    """

    @staticmethod
    async def process_turn(
        call_id: str,
        user_message: str,
        campaign_id: Optional[str] = None,
        contact_id: Optional[str] = None,
        organization_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Process a single turn via LangGraph with concurrency control."""
        return await AudioPipelineManager.process_utterance_turn(
            call_id=call_id,
            user_utterance=user_message,
            campaign_id=campaign_id,
            contact_id=contact_id,
            organization_id=organization_id
        )

    @staticmethod
    async def get_call_state_and_history(call_id: str) -> Dict[str, Any]:
        """Retrieve authoritative business record and active LangGraph checkpoint."""
        thread_id = get_stable_thread_id(call_id)
        checkpointer = await get_checkpointer(use_postgres=False)
        graph = build_voice_agent_graph(checkpointer=checkpointer)

        graph_state = {}
        try:
            snapshot = await graph.aget_state({"configurable": {"thread_id": thread_id}})
            if snapshot and snapshot.values:
                graph_state = dict(snapshot.values)
                # Remove non-serializable objects from output
                graph_state.pop("messages", None)
        except Exception as e:
            logger.info(f"No checkpoint found for call {call_id}: {e}")

        async with AsyncSessionLocal() as db:
            call_uuid = uuid.UUID(call_id)
            c_res = await db.execute(select(Call).where(Call.id == call_uuid))
            call = c_res.scalar_one_or_none()
            if not call:
                return {"error": "Call not found"}

            t_res = await db.execute(select(Transcript).where(Transcript.call_id == call_uuid))
            transcript = t_res.scalar_one_or_none()

            ext_res = await db.execute(select(ExtractedCallResult).where(ExtractedCallResult.call_id == call_uuid))
            extracted = ext_res.scalar_one_or_none()

            return {
                "call_id": str(call.id),
                "status": call.status.value if hasattr(call.status, "value") else str(call.status),
                "duration_seconds": call.duration_seconds or 0,
                "ai_interactions": call.ai_interactions or 0,
                "transcript": transcript.full_transcript if transcript else "",
                "extracted_result": {
                    "outcome": extracted.call_outcome if extracted else None,
                    "intent": extracted.customer_intent if extracted else None,
                    "rating": extracted.customer_rating if extracted else None,
                    "raw_data": extracted.raw_extracted_data if extracted else {}
                } if extracted else None,
                "tool_audit_logs": [],
                "active_graph_state": graph_state
            }
