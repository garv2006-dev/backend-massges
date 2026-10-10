"""StateGraph Construction and Compilation for Voice Agent Orchestration."""

from langgraph.graph import StateGraph, START, END
from app.agent.state import ConversationState
from app.agent.graph.nodes import (
    load_context,
    process_customer_input,
    call_model,
    execute_tools,
    validate_tool_results,
    generate_voice_response,
    persist_turn,
    finalize_call,
    handle_error
)
from app.agent.graph.edges import (
    route_after_context,
    route_after_customer_input,
    route_after_model,
    route_after_validation
)
from app.agent.graph.checkpointer import get_checkpointer

def build_voice_agent_graph(checkpointer=None):
    """
    Constructs the compiled LangGraph StateGraph with conditional edges,
    error recovery, tool validation, and state persistence.
    """
    workflow = StateGraph(ConversationState)

    # 1. Register all nodes
    workflow.add_node("load_context", load_context)
    workflow.add_node("process_customer_input", process_customer_input)
    workflow.add_node("call_model", call_model)
    workflow.add_node("execute_tools", execute_tools)
    workflow.add_node("validate_tool_results", validate_tool_results)
    workflow.add_node("generate_voice_response", generate_voice_response)
    workflow.add_node("persist_turn", persist_turn)
    workflow.add_node("finalize_call", finalize_call)
    workflow.add_node("handle_error", handle_error)

    # 2. Add edges
    workflow.add_edge(START, "load_context")

    workflow.add_conditional_edges(
        "load_context",
        route_after_context,
        {
            "finalize_call": "finalize_call",
            "process_customer_input": "process_customer_input"
        }
    )

    workflow.add_conditional_edges(
        "process_customer_input",
        route_after_customer_input,
        {
            "finalize_call": "finalize_call",
            "call_model": "call_model"
        }
    )

    workflow.add_conditional_edges(
        "call_model",
        route_after_model,
        {
            "handle_error": "handle_error",
            "execute_tools": "execute_tools",
            "finalize_call": "finalize_call",
            "generate_voice_response": "generate_voice_response"
        }
    )

    workflow.add_edge("execute_tools", "validate_tool_results")

    workflow.add_conditional_edges(
        "validate_tool_results",
        route_after_validation,
        {
            "finalize_call": "finalize_call",
            "generate_voice_response": "generate_voice_response",
            "call_model": "call_model"
        }
    )

    workflow.add_edge("finalize_call", "generate_voice_response")
    workflow.add_edge("handle_error", "persist_turn")
    workflow.add_edge("generate_voice_response", "persist_turn")
    workflow.add_edge("persist_turn", END)

    if checkpointer is not None:
        return workflow.compile(checkpointer=checkpointer)
    return workflow.compile()
