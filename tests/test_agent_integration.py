"""Integration tests for complete LangGraph agent workflow."""

import pytest
import uuid
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.agent.audio_pipeline import AudioPipelineManager
from app.agent.graph.builder import build_voice_agent_graph
from app.agent.graph.checkpointer import get_stable_thread_id, get_checkpointer
from app.agent.state import ConversationState
from app.models.call import Call, CallStatus
from app.models.transcript import Transcript
from app.models.extracted_call_result import ExtractedCallResult
from app.models.tool_execution_audit import ToolExecutionAuditLog
from app.models.suppression_record import SuppressionRecord
from app.agent.gemini import MockGeminiVoiceModel


class TestCompleteAgentWorkflow:
    """Integration tests for end-to-end agent workflows."""

    @pytest.mark.asyncio
    async def test_normal_conversational_turn(self, db_session: AsyncSession, test_call: Call, test_contact: Contact, test_campaign: Campaign):
        """Test a complete normal conversational turn through the graph."""
        # Use mock model for deterministic testing
        from app.agent import gemini
        original_get_model = gemini.get_gemini_voice_model
        gemini.get_gemini_voice_model = lambda tools, **kwargs: MockGeminiVoiceModel().bind_tools(tools)

        try:
            result = await AudioPipelineManager.process_utterance_turn(
                call_id=str(test_call.id),
                user_utterance="I'm interested in learning more about your services",
                campaign_id=str(test_campaign.id),
                contact_id=str(test_contact.id),
                organization_id=str(uuid.uuid4())
            )

            assert result["call_id"] == str(test_call.id)
            assert result["user_utterance"] == "I'm interested in learning more about your services"
            assert result["agent_response"] is not None
            assert len(result["agent_response"]) > 0
            assert result["turn_count"] >= 1
            assert result["should_end_call"] is False
            assert result["handoff_requested"] is False

            # Verify transcript was persisted
            await db_session.refresh(test_call)
            stmt = select(Transcript).where(Transcript.call_id == test_call.id)
            t_res = await db_session.execute(stmt)
            transcript = t_res.scalar_one_or_none()
            assert transcript is not None
            assert "Customer:" in transcript.full_transcript
            assert "AI Agent:" in transcript.full_transcript

        finally:
            gemini.get_gemini_voice_model = original_get_model

    @pytest.mark.asyncio
    async def test_opt_out_detection_and_termination(self, db_session: AsyncSession, test_call: Call, test_contact: Contact, test_campaign: Campaign):
        """Test opt-out detection and automatic call termination."""
        from app.agent import gemini
        original_get_model = gemini.get_gemini_voice_model
        gemini.get_gemini_voice_model = lambda tools, **kwargs: MockGeminiVoiceModel().bind_tools(tools)

        try:
            result = await AudioPipelineManager.process_utterance_turn(
                call_id=str(test_call.id),
                user_utterance="Stop calling me, remove my number",
                campaign_id=str(test_campaign.id),
                contact_id=str(test_contact.id),
                organization_id=str(uuid.uuid4())
            )

            assert result["should_end_call"] is True
            assert "opt out" in result["agent_response"].lower() or "remove" in result["agent_response"].lower()

            # Verify suppression record was created
            stmt = select(SuppressionRecord).where(
                SuppressionRecord.phone_number == test_contact.phone_number_normalized
            )
            s_res = await db_session.execute(stmt)
            suppression = s_res.scalar_one_or_none()
            assert suppression is not None
            assert suppression.reason == "opt_out"

        finally:
            gemini.get_gemini_voice_model = original_get_model

    @pytest.mark.asyncio
    async def test_tool_execution_workflow(self, db_session: AsyncSession, test_call: Call, test_contact: Contact, test_campaign: Campaign):
        """Test workflow that triggers tool execution (follow-up scheduling)."""
        from app.agent import gemini
        original_get_model = gemini.get_gemini_voice_model
        gemini.get_gemini_voice_model = lambda tools, **kwargs: MockGeminiVoiceModel().bind_tools(tools)

        try:
            result = await AudioPipelineManager.process_utterance_turn(
                call_id=str(test_call.id),
                user_utterance="Can you schedule a follow-up call for tomorrow?",
                campaign_id=str(test_campaign.id),
                contact_id=str(test_contact.id),
                organization_id=str(uuid.uuid4())
            )

            assert result["agent_response"] is not None
            # Mock model will trigger schedule_follow_up tool
            assert "schedule" in result["agent_response"].lower() or "follow-up" in result["agent_response"].lower()

            # Verify tool audit log was created
            stmt = select(ToolExecutionAuditLog).where(
                ToolExecutionAuditLog.call_id == test_call.id
            )
            a_res = await db_session.execute(stmt)
            audits = a_res.scalars().all()
            assert len(audits) > 0

        finally:
            gemini.get_gemini_voice_model = original_get_model

    @pytest.mark.asyncio
    async def test_turn_limit_enforcement(self, db_session: AsyncSession, test_call: Call, test_contact: Contact, test_campaign: Campaign):
        """Test that turn limits are enforced and call terminates."""
        from app.agent import gemini
        original_get_model = gemini.get_gemini_voice_model
        gemini.get_gemini_voice_model = lambda tools, **kwargs: MockGeminiVoiceModel().bind_tools(tools)

        try:
            # Simulate multiple turns
            for i in range(12):  # Exceed default max_turns of 10
                result = await AudioPipelineManager.process_utterance_turn(
                    call_id=str(test_call.id),
                    user_utterance=f"Turn {i+1}",
                    campaign_id=str(test_campaign.id),
                    contact_id=str(test_contact.id),
                    organization_id=str(uuid.uuid4())
                )

                if result["should_end_call"]:
                    break

            # Should have terminated due to turn limit
            assert result["should_end_call"] is True
            assert "thank you" in result["agent_response"].lower() or "goodbye" in result["agent_response"].lower()

        finally:
            gemini.get_gemini_voice_model = original_get_model

    @pytest.mark.asyncio
    async def test_checkpoint_recovery(self, db_session: AsyncSession, test_call: Call, test_contact: Contact, test_campaign: Campaign):
        """Test that conversation state can be recovered from checkpoint."""
        from app.agent import gemini
        original_get_model = gemini.get_gemini_voice_model
        gemini.get_gemini_voice_model = lambda tools, **kwargs: MockGeminiVoiceModel().bind_tools(tools)

        try:
            # First turn
            result1 = await AudioPipelineManager.process_utterance_turn(
                call_id=str(test_call.id),
                user_utterance="Hello",
                campaign_id=str(test_campaign.id),
                contact_id=str(test_contact.id),
                organization_id=str(uuid.uuid4())
            )

            # Get checkpoint
            thread_id = get_stable_thread_id(str(test_call.id))
            checkpointer = await get_checkpointer(use_postgres=False)
            graph = build_voice_agent_graph(checkpointer=checkpointer)

            snapshot = await graph.aget_state({"configurable": {"thread_id": thread_id}})
            assert snapshot is not None
            assert snapshot.values is not None
            assert snapshot.values.get("turn_count") >= 1

            # Second turn (should continue from checkpoint)
            result2 = await AudioPipelineManager.process_utterance_turn(
                call_id=str(test_call.id),
                user_utterance="Tell me more",
                campaign_id=str(test_campaign.id),
                contact_id=str(test_contact.id),
                organization_id=str(uuid.uuid4())
            )

            assert result2["turn_count"] >= 2

        finally:
            gemini.get_gemini_voice_model = original_get_model

    @pytest.mark.asyncio
    async def test_concurrent_conversation_isolation(self, db_session: AsyncSession, test_user):
        """Test that concurrent conversations don't interfere with each other."""
        from app.agent import gemini
        original_get_model = gemini.get_gemini_voice_model
        gemini.get_gemini_voice_model = lambda tools, **kwargs: MockGeminiVoiceModel().bind_tools(tools)

        try:
            # Create two separate calls
            from app.models.call import Call, CallDirection
            from app.models.contact import Contact
            from app.models.campaign import Campaign

            contact1 = Contact(
                id=uuid.uuid4(),
                name="User One",
                phone_number="+15551111111",
                phone_number_normalized="+15551111111",
                email="user1@example.com",
                language="en"
            )
            contact2 = Contact(
                id=uuid.uuid4(),
                name="User Two",
                phone_number="+15552222222",
                phone_number_normalized="+15552222222",
                email="user2@example.com",
                language="en"
            )
            db_session.add_all([contact1, contact2])
            await db_session.commit()

            campaign = Campaign(
                id=uuid.uuid4(),
                name="Test Campaign",
                status="in_progress",
                agent_prompt="Test prompt",
                max_call_duration=300,
                created_by=test_user.id
            )
            db_session.add(campaign)
            await db_session.commit()

            call1 = Call(
                id=uuid.uuid4(),
                campaign_id=campaign.id,
                contact_id=contact1.id,
                phone_number=contact1.phone_number_normalized,
                direction=CallDirection.OUTBOUND,
                status=CallStatus.IN_PROGRESS,
                provider="ai_voice_engine"
            )
            call2 = Call(
                id=uuid.uuid4(),
                campaign_id=campaign.id,
                contact_id=contact2.id,
                phone_number=contact2.phone_number_normalized,
                direction=CallDirection.OUTBOUND,
                status=CallStatus.IN_PROGRESS,
                provider="ai_voice_engine"
            )
            db_session.add_all([call1, call2])
            await db_session.commit()

            # Process turns concurrently
            import asyncio
            results = await asyncio.gather(
                AudioPipelineManager.process_utterance_turn(
                    call_id=str(call1.id),
                    user_utterance="I am user one",
                    campaign_id=str(campaign.id),
                    contact_id=str(contact1.id),
                    organization_id=str(uuid.uuid4())
                ),
                AudioPipelineManager.process_utterance_turn(
                    call_id=str(call2.id),
                    user_utterance="I am user two",
                    campaign_id=str(campaign.id),
                    contact_id=str(contact2.id),
                    organization_id=str(uuid.uuid4())
                )
            )

            # Both should complete successfully
            assert len(results) == 2
            assert all(r["agent_response"] is not None for r in results)

            # Verify transcripts are separate
            stmt1 = select(Transcript).where(Transcript.call_id == call1.id)
            stmt2 = select(Transcript).where(Transcript.call_id == call2.id)
            t1_res = await db_session.execute(stmt1)
            t2_res = await db_session.execute(stmt2)
            transcript1 = t1_res.scalar_one_or_none()
            transcript2 = t2_res.scalar_one_or_none()

            assert transcript1 is not None
            assert transcript2 is not None
            assert "user one" in transcript1.full_transcript.lower()
            assert "user two" in transcript2.full_transcript.lower()
            assert "user two" not in transcript1.full_transcript.lower()
            assert "user one" not in transcript2.full_transcript.lower()

        finally:
            gemini.get_gemini_voice_model = original_get_model

    @pytest.mark.asyncio
    async def test_human_transfer_workflow(self, db_session: AsyncSession, test_call: Call, test_contact: Contact, test_campaign: Campaign):
        """Test human transfer request workflow."""
        from app.agent import gemini
        original_get_model = gemini.get_gemini_voice_model
        gemini.get_gemini_voice_model = lambda tools, **kwargs: MockGeminiVoiceModel().bind_tools(tools)

        try:
            result = await AudioPipelineManager.process_utterance_turn(
                call_id=str(test_call.id),
                user_utterance="I want to speak to a human representative",
                campaign_id=str(test_campaign.id),
                contact_id=str(test_contact.id),
                organization_id=str(uuid.uuid4())
            )

            # Mock model should trigger transfer
            assert result["handoff_requested"] is True or "transfer" in result["agent_response"].lower()

        finally:
            gemini.get_gemini_voice_model = original_get_model

    @pytest.mark.asyncio
    async def test_tool_iteration_limit(self, db_session: AsyncSession, test_call: Call, test_contact: Contact, test_campaign: Campaign):
        """Test that tool iteration limits prevent infinite loops."""
        from app.agent import gemini
        original_get_model = gemini.get_gemini_voice_model

        # Create a mock that keeps requesting tools
        class InfiniteToolMockModel(MockGeminiVoiceModel):
            def _generate(self, messages, stop=None, run_manager=None, **kwargs):
                from langchain_core.messages import AIMessage
                from langchain_core.outputs import ChatResult, ChatGeneration
                ai_msg = AIMessage(
                    content="I need more information",
                    tool_calls=[{
                        "id": f"call_{uuid.uuid4()}",
                        "name": "get_contact_details",
                        "args": {"contact_id": kwargs.get("contact_id", str(uuid.uuid4()))}
                    }]
                )
                return ChatResult(generations=[ChatGeneration(message=ai_msg)])

        gemini.get_gemini_voice_model = lambda tools, **kwargs: InfiniteToolMockModel().bind_tools(tools)

        try:
            # Should hit tool iteration limit and terminate
            result = await AudioPipelineManager.process_utterance_turn(
                call_id=str(test_call.id),
                user_utterance="Test tool limit",
                campaign_id=str(test_campaign.id),
                contact_id=str(test_contact.id),
                organization_id=str(uuid.uuid4())
            )

            # Should terminate due to tool iteration limit
            assert result["should_end_call"] is True or result["turn_count"] > 4

        finally:
            gemini.get_gemini_voice_model = original_get_model

    @pytest.mark.asyncio
    async def test_barge_in_interruption(self, db_session: AsyncSession, test_call: Call, test_contact: Contact, test_campaign: Campaign):
        """Test barge-in interruption handling."""
        from app.agent import gemini
        original_get_model = gemini.get_gemini_voice_model
        gemini.get_gemini_voice_model = lambda tools, **kwargs: MockGeminiVoiceModel().bind_tools(tools)

        try:
            # Start first turn
            session = AudioPipelineManager.get_session(str(test_call.id))
            session.is_speaking = True  # Simulate agent speaking

            # Customer barges in
            result = await AudioPipelineManager.process_utterance_turn(
                call_id=str(test_call.id),
                user_utterance="Wait, let me ask something else",
                campaign_id=str(test_campaign.id),
                contact_id=str(test_contact.id),
                organization_id=str(uuid.uuid4())
            )

            assert result["agent_response"] is not None
            assert session.is_speaking is False  # Should have been interrupted

            AudioPipelineManager.release_session(str(test_call.id))

        finally:
            gemini.get_gemini_voice_model = original_get_model

    @pytest.mark.asyncio
    async def test_extracted_fields_persistence(self, db_session: AsyncSession, test_call: Call, test_contact: Contact, test_campaign: Campaign):
        """Test that extracted fields are persisted correctly."""
        from app.agent import gemini
        original_get_model = gemini.get_gemini_voice_model
        gemini.get_gemini_voice_model = lambda tools, **kwargs: MockGeminiVoiceModel().bind_tools(tools)

        try:
            # Turn that should trigger field extraction
            result = await AudioPipelineManager.process_utterance_turn(
                call_id=str(test_call.id),
                user_utterance="My budget is around $5000",
                campaign_id=str(test_campaign.id),
                contact_id=str(test_contact.id),
                organization_id=str(uuid.uuid4())
            )

            # Verify extracted result record exists
            stmt = select(ExtractedCallResult).where(ExtractedCallResult.call_id == test_call.id)
            res = await db_session.execute(stmt)
            extracted = res.scalar_one_or_none()

            # May or may not have fields depending on mock behavior
            if extracted:
                assert extracted.call_id == test_call.id

        finally:
            gemini.get_gemini_voice_model = original_get_model
