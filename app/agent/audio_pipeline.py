"""Audio Transport Layer and Real-Time Speech Pipeline.

Decouples audio I/O, Deepgram STT, and Text-to-Speech synthesis from LangGraph.
Enforces per-call synchronization locks to avoid concurrent graph executions,
and supports barge-in interruption handling.
"""

import asyncio
import logging
from typing import Dict, Optional, AsyncGenerator
import edge_tts
from app.agent.graph.builder import build_voice_agent_graph
from app.agent.graph.checkpointer import get_stable_thread_id, get_checkpointer

logger = logging.getLogger(__name__)

class AudioTurnSession:
    """Manages call-level audio state, concurrency locks, and barge-in flags."""
    def __init__(self, call_id: str):
        self.call_id = call_id
        self.turn_lock = asyncio.Lock()
        self.is_speaking = False
        self.interruption_event = asyncio.Event()

class AudioPipelineManager:
    """
    Coordinates Deepgram STT events, LangGraph execution turns,
    and TTS audio output with barge-in support.
    """
    _sessions: Dict[str, AudioTurnSession] = {}

    @classmethod
    def get_session(cls, call_id: str) -> AudioTurnSession:
        if call_id not in cls._sessions:
            cls._sessions[call_id] = AudioTurnSession(call_id)
        return cls._sessions[call_id]

    @classmethod
    def release_session(cls, call_id: str) -> None:
        cls._sessions.pop(call_id, None)

    @classmethod
    async def process_utterance_turn(
        cls,
        call_id: str,
        user_utterance: str,
        campaign_id: Optional[str] = None,
        contact_id: Optional[str] = None,
        organization_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes a finalized customer speech turn through LangGraph.
        Guarantees serial execution per call state.
        """
        session = cls.get_session(call_id)

        # Handle barge-in: If agent was speaking, signal interruption
        if session.is_speaking:
            logger.info(f"Barge-in detected for call {call_id}; interrupting current playback.")
            session.interruption_event.set()
            session.is_speaking = False

        # Acquire per-call turn lock to prevent state concurrency collisions
        async with session.turn_lock:
            session.interruption_event.clear()

            checkpointer = await get_checkpointer(use_postgres=False)
            graph = build_voice_agent_graph(checkpointer=checkpointer)
            thread_id = get_stable_thread_id(call_id)

            input_state = {
                "call_id": call_id,
                "campaign_id": campaign_id,
                "contact_id": contact_id,
                "organization_id": organization_id,
                "last_user_utterance": user_utterance,
            }

            config = {"configurable": {"thread_id": thread_id}}
            result_state = await graph.ainvoke(input_state, config=config)

            agent_response = result_state.get("agent_response_text", "")
            should_end = result_state.get("should_end_call", False)
            handoff = result_state.get("handoff_requested", False)

            return {
                "call_id": call_id,
                "user_utterance": user_utterance,
                "agent_response": agent_response,
                "should_end_call": should_end,
                "handoff_requested": handoff,
                "call_status": result_state.get("call_status", "in_progress"),
                "turn_count": result_state.get("turn_count", 1)
            }

    @classmethod
    async def synthesize_speech_stream(
        cls,
        call_id: str,
        text: str,
        voice: str = "en-IN-NeerjaNeural"
    ) -> AsyncGenerator[bytes, None]:
        """
        Streams synthesized audio chunks with barge-in interruption checks.
        """
        session = cls.get_session(call_id)
        session.is_speaking = True

        try:
            communicate = edge_tts.Communicate(text, voice)
            async for chunk in communicate.stream():
                if session.interruption_event.is_set():
                    logger.info(f"Audio playback interrupted by caller for {call_id}")
                    break
                if chunk["type"] == "audio":
                    yield chunk["data"]
        except Exception as e:
            logger.warning(f"EdgeTTS generation fallback or error: {e}")
        finally:
            session.is_speaking = False
