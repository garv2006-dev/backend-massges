"""LangGraph Typed State Definition for AI Voice Calling Platform."""

from typing import TypedDict, List, Dict, Any, Optional, Sequence, Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class ConversationState(TypedDict, total=False):
    """
    Strongly typed state schema for LangGraph agent orchestration.
    Contains business fields, conversation history, compliance metadata,
    and runtime control flags.
    """
    # Identifiers
    conversation_id: str
    call_id: str
    campaign_id: str
    contact_id: str
    organization_id: str

    # Conversation history (uses add_messages reducer for message appending)
    messages: Annotated[Sequence[BaseMessage], add_messages]

    # Customer and campaign context
    customer_name: Optional[str]
    contact_phone: Optional[str]
    conversation_language: str
    campaign_name: Optional[str]
    campaign_prompt: Optional[str]

    # Dynamic extraction & intent tracking
    current_intent: Optional[str]
    extracted_fields: Dict[str, Any]
    tool_results: List[Dict[str, Any]]

    # Compliance & call state
    consent_status: str  # "consented", "opted_out", "pending", "revoked"
    call_status: str     # "queued", "in_progress", "completed", "failed", "transferred"
    retry_count: int
    should_end_call: bool
    handoff_requested: bool
    error_state: Optional[str]

    # Runtime boundaries
    turn_count: int
    max_turns: int
    elapsed_duration_seconds: int
    max_duration_seconds: int
    tool_call_count: int
    max_tool_iterations: int

    # Latest turn outputs
    last_user_utterance: str
    agent_response_text: str
    is_clarification: bool
    call_outcome: Optional[str]
