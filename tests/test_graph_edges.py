"""Unit tests for LangGraph conditional routing edges."""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from app.agent.graph.edges import (
    route_after_context,
    route_after_customer_input,
    route_after_model,
    route_after_validation
)
from app.agent.state import ConversationState


class TestRouteAfterContext:
    """Tests for route_after_context conditional edge."""

    def test_routes_to_finalize_call_when_suppressed(self):
        """Should route to finalize_call when should_end_call is True (suppressed)."""
        state: ConversationState = {
            "should_end_call": True,
            "consent_status": "opted_out"
        }
        result = route_after_context(state)
        assert result == "finalize_call"

    def test_routes_to_process_customer_input_normal_flow(self):
        """Should route to process_customer_input in normal flow."""
        state: ConversationState = {
            "should_end_call": False,
            "consent_status": "consented"
        }
        result = route_after_context(state)
        assert result == "process_customer_input"

    def test_routes_to_finalize_call_with_missing_flag(self):
        """Should default to process_customer_input when flag is missing."""
        state: ConversationState = {}
        result = route_after_context(state)
        assert result == "process_customer_input"


class TestRouteAfterCustomerInput:
    """Tests for route_after_customer_input conditional edge."""

    def test_routes_to_finalize_call_on_turn_limit(self):
        """Should route to finalize_call when turn limits triggered."""
        state: ConversationState = {
            "should_end_call": True,
            "turn_count": 11,
            "max_turns": 10
        }
        result = route_after_customer_input(state)
        assert result == "finalize_call"

    def test_routes_to_finalize_call_on_opt_out(self):
        """Should route to finalize_call on opt-out detection."""
        state: ConversationState = {
            "should_end_call": True,
            "consent_status": "opted_out"
        }
        result = route_after_customer_input(state)
        assert result == "finalize_call"

    def test_routes_to_call_model_normal_flow(self):
        """Should route to call_model in normal flow."""
        state: ConversationState = {
            "should_end_call": False,
            "turn_count": 3,
            "max_turns": 10
        }
        result = route_after_customer_input(state)
        assert result == "call_model"


class TestRouteAfterModel:
    """Tests for route_after_model conditional edge."""

    def test_routes_to_handle_error_on_error_state(self):
        """Should route to handle_error when error_state is set."""
        state: ConversationState = {
            "error_state": "Model timeout after 30s",
            "should_end_call": False
        }
        result = route_after_model(state)
        assert result == "handle_error"

    def test_routes_to_execute_tools_with_tool_calls(self):
        """Should route to execute_tools when AIMessage has tool_calls."""
        state: ConversationState = {
            "messages": [
                HumanMessage(content="Hello"),
                AIMessage(
                    content="I'll check that for you",
                    tool_calls=[{
                        "id": "call_123",
                        "name": "get_contact_details",
                        "args": {"contact_id": "abc-123"}
                    }]
                )
            ],
            "error_state": None,
            "should_end_call": False
        }
        result = route_after_model(state)
        assert result == "execute_tools"

    def test_routes_to_finalize_call_on_handoff_requested(self):
        """Should route to finalize_call when handoff is requested."""
        state: ConversationState = {
            "handoff_requested": True,
            "messages": [AIMessage(content="I'll transfer you")],
            "error_state": None
        }
        result = route_after_model(state)
        assert result == "finalize_call"

    def test_routes_to_finalize_call_on_should_end_call(self):
        """Should route to finalize_call when should_end_call is True."""
        state: ConversationState = {
            "should_end_call": True,
            "messages": [AIMessage(content="Goodbye")],
            "error_state": None
        }
        result = route_after_model(state)
        assert result == "finalize_call"

    def test_routes_to_generate_voice_response_conversational(self):
        """Should route to generate_voice_response for normal conversational response."""
        state: ConversationState = {
            "messages": [
                HumanMessage(content="Hello"),
                AIMessage(content="Hi there! How can I help?")
            ],
            "error_state": None,
            "should_end_call": False,
            "handoff_requested": False
        }
        result = route_after_model(state)
        assert result == "generate_voice_response"

    def test_routes_to_generate_voice_response_with_empty_messages(self):
        """Should route to generate_voice_response when messages list is empty."""
        state: ConversationState = {
            "messages": [],
            "error_state": None,
            "should_end_call": False
        }
        result = route_after_model(state)
        assert result == "generate_voice_response"

    def test_routes_to_generate_voice_response_without_tool_calls(self):
        """Should route to generate_voice_response when AIMessage has no tool_calls."""
        state: ConversationState = {
            "messages": [
                AIMessage(content="Sure, I can help with that")
            ],
            "error_state": None,
            "should_end_call": False
        }
        result = route_after_model(state)
        assert result == "generate_voice_response"


class TestRouteAfterValidation:
    """Tests for route_after_validation conditional edge."""

    def test_routes_to_finalize_call_on_handoff(self):
        """Should route to finalize_call when handoff is requested."""
        state: ConversationState = {
            "handoff_requested": True,
            "messages": [ToolMessage(content="Transfer successful", tool_call_id="123")]
        }
        result = route_after_validation(state)
        assert result == "finalize_call"

    def test_routes_to_finalize_call_on_should_end_call(self):
        """Should route to finalize_call when should_end_call is True."""
        state: ConversationState = {
            "should_end_call": True,
            "messages": [ToolMessage(content="Call ended", tool_call_id="123")]
        }
        result = route_after_validation(state)
        assert result == "finalize_call"

    def test_routes_to_call_model_for_multi_step(self):
        """Should route to call_model when last message is ToolMessage (multi-step reasoning)."""
        state: ConversationState = {
            "should_end_call": False,
            "handoff_requested": False,
            "messages": [
                HumanMessage(content="Schedule a call"),
                AIMessage(
                    content="I'll schedule that",
                    tool_calls=[{
                        "id": "call_1",
                        "name": "schedule_follow_up",
                        "args": {"scheduled_iso": "2026-10-12T10:00:00Z"}
                    }]
                ),
                ToolMessage(content="Scheduled successfully", tool_call_id="call_1")
            ]
        }
        result = route_after_validation(state)
        assert result == "call_model"

    def test_routes_to_generate_voice_response_after_tool_execution(self):
        """Should route to generate_voice_response when last message is AIMessage."""
        state: ConversationState = {
            "should_end_call": False,
            "handoff_requested": False,
            "messages": [
                AIMessage(content="I've scheduled your follow-up call.")
            ]
        }
        result = route_after_validation(state)
        assert result == "generate_voice_response"

    def test_routes_to_generate_voice_response_with_empty_messages(self):
        """Should route to generate_voice_response when messages list is empty."""
        state: ConversationState = {
            "should_end_call": False,
            "handoff_requested": False,
            "messages": []
        }
        result = route_after_validation(state)
        assert result == "generate_voice_response"
