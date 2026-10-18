"""Gemini Model Integration with Tool Calling and Spoken Voice Instructions."""

import logging
from typing import List, Optional, Any
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.outputs import ChatResult, ChatGeneration
from langchain_google_genai import ChatGoogleGenerativeAI
from app.config import settings

logger = logging.getLogger(__name__)

VOICE_AGENT_SYSTEM_PROMPT = """You are an AI voice phone assistant representing {company_name}.
Agent Name: {agent_name}
Language: {language}
Tone: {tone}

Campaign Instructions:
{campaign_prompt}

Customer Details:
Name: {customer_name}

CRITICAL PHONE CALL RULES:
1. Speak concisely in 1 to 2 spoken sentences maximum per turn. Never output bullet points, headers, or markdown formatting.
2. Be polite, natural, and helpful.
3. If the customer asks to stop, opt-out, or states they do not wish to be called, respect their request immediately, use the `end_call` tool, and do not argue.
4. Only use tools when genuinely required. Do not hallucinate contact information.
5. If customer information or intent is ambiguous, ask a clarifying question.
6. When final agreement, scheduling, or conclusion is reached, use appropriate tools (`save_conversation_field`, `schedule_follow_up`, `save_call_result`, or `end_call`).
"""

class MockGeminiVoiceModel(BaseChatModel):
    """
    Simulated conversational model for offline environments and automated testing.
    Emulates realistic tool selection and conversational voice turns.
    """
    bound_tools: List[Any] = []

    @property
    def _llm_type(self) -> str:
        return "mock_gemini_voice_model"

    def bind_tools(self, tools: List[Any], **kwargs: Any) -> "MockGeminiVoiceModel":
        new_model = MockGeminiVoiceModel()
        new_model.bound_tools = list(tools)
        return new_model

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any
    ) -> ChatResult:
        # Inspect latest human message
        last_human = ""
        for m in reversed(messages):
            if isinstance(m, HumanMessage):
                last_human = m.content.lower()
                break

        # Check for opt-out intent
        if any(w in last_human for w in ["stop", "don't call", "do not call", "unsubscribe", "opt out", "remove my number"]):
            ai_msg = AIMessage(
                content="I understand completely. I will make sure your number is removed and end the call now. Have a nice day.",
                tool_calls=[{
                    "id": "call_end_optout",
                    "name": "end_call",
                    "args": {
                        "call_id": kwargs.get("call_id", ""),
                        "hangup_reason": "Customer requested opt-out",
                        "customer_consented_or_opt_out": True
                    }
                }]
            )
            return ChatResult(generations=[ChatGeneration(message=ai_msg)])

        # Check for transfer intent
        if any(w in last_human for w in ["transfer", "human", "supervisor", "representative", "manager"]):
            ai_msg = AIMessage(
                content="I would be happy to transfer you to a human representative. Please hold on for just a moment.",
                tool_calls=[{
                    "id": "call_transfer_req",
                    "name": "transfer_to_human",
                    "args": {
                        "call_id": kwargs.get("call_id", ""),
                        "reason": "Customer requested human representative",
                        "department": "support"
                    }
                }]
            )
            return ChatResult(generations=[ChatGeneration(message=ai_msg)])

        # Check for follow-up scheduling intent
        if any(w in last_human for w in ["schedule", "call back tomorrow", "call later", "follow up"]):
            ai_msg = AIMessage(
                content="Certainly! I will schedule a follow-up for tomorrow so we can speak at your convenience.",
                tool_calls=[{
                    "id": "call_sched_followup",
                    "name": "schedule_follow_up",
                    "args": {
                        "call_id": kwargs.get("call_id", ""),
                        "contact_id": kwargs.get("contact_id", ""),
                        "scheduled_iso": "2026-10-11T10:00:00Z",
                        "channel": "voice",
                        "notes": "Follow-up requested by customer"
                    }
                }]
            )
            return ChatResult(generations=[ChatGeneration(message=ai_msg)])

        # Check for ambiguity requiring clarification
        if any(w in last_human for w in ["maybe", "not sure", "depends", "what do you mean"]):
            ai_msg = AIMessage(
                content="Could you share a bit more about what you are looking for so I can assist you better?"
            )
            return ChatResult(generations=[ChatGeneration(message=ai_msg)])

        # Standard conversational response
        ai_msg = AIMessage(
            content="Thank you for sharing that. We would be delighted to assist your business with our voice solutions. Would you like more details?"
        )
        return ChatResult(generations=[ChatGeneration(message=ai_msg)])


def get_gemini_voice_model(
    tools: Optional[List[Any]] = None,
    model_name: str = "gemini-1.5-flash",
    temperature: float = 0.2,
    force_mock: bool = False
) -> BaseChatModel:
    """
    Returns a configured Gemini Chat model with bound tools,
    or a robust conversational mock when credentials are not configured or in test environments.
    """
    has_valid_key = (
        bool(settings.GEMINI_API_KEY) and
        not settings.GEMINI_API_KEY.startswith("your-") and
        not force_mock
    )

    if has_valid_key:
        try:
            model = ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=settings.GEMINI_API_KEY,
                temperature=temperature,
                max_retries=2,
            )
            if tools:
                return model.bind_tools(tools)
            return model
        except Exception as e:
            logger.warning(f"Failed to initialize ChatGoogleGenerativeAI: {e}, using mock fallback.")

    # Return mock model
    mock = MockGeminiVoiceModel()
    if tools:
        return mock.bind_tools(tools)
    return mock
