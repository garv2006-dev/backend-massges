"""Conditional Routing Edges for LangGraph Voice Agent Graph."""

import logging
from typing import Literal
from langchain_core.messages import AIMessage
from app.agent.state import ConversationState

logger = logging.getLogger(__name__)

def route_after_context(state: ConversationState) -> Literal["finalize_call", "process_customer_input"]:
    """Check if contact was suppressed or opted-out during context loading."""
    if state.get("should_end_call", False):
        return "finalize_call"
    return "process_customer_input"


def route_after_customer_input(state: ConversationState) -> Literal["finalize_call", "call_model"]:
    """Check if turn limits or opt-out phrases triggered termination."""
    if state.get("should_end_call", False):
        return "finalize_call"
    return "call_model"


def route_after_model(state: ConversationState) -> Literal["handle_error", "execute_tools", "finalize_call", "generate_voice_response"]:
    """
    Decide whether to execute tools, handle errors, finalize call,
    or generate conversational voice response.
    """
    if state.get("error_state"):
        return "handle_error"

    if state.get("should_end_call", False) or state.get("handoff_requested", False):
        return "finalize_call"

    messages = state.get("messages", [])
    if messages:
        last_msg = messages[-1]
        if isinstance(last_msg, AIMessage) and getattr(last_msg, "tool_calls", None):
            return "execute_tools"

    return "generate_voice_response"


def route_after_validation(state: ConversationState) -> Literal["finalize_call", "generate_voice_response", "call_model"]:
    """
    Decide whether to end call after tool execution, perform multi-step
    model reasoning, or generate conversational response.
    """
    if state.get("should_end_call", False) or state.get("handoff_requested", False):
        return "finalize_call"

    # Multi-step tool workflow check: if tool call count is low and we need the model
    # to synthesize a follow-up answer from the tool message, route back to call_model
    messages = state.get("messages", [])
    if messages and not isinstance(messages[-1], AIMessage):
        # Last message was ToolMessage
        return "call_model"

    return "generate_voice_response"
