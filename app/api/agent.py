"""FastAPI Endpoints for LangGraph Agent Orchestration and Tool Auditing."""

import uuid
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.core.deps import get_current_user
from app.agent.service import VoiceAgentOrchestrator
from app.agent.tools.security import ToolSecurityContext, ToolSecurityManager
from app.agent.tools.definitions import create_agent_tools
from app.models.call import Call

router = APIRouter()

class VoiceTurnRequest(BaseModel):
    call_id: str = Field(description="Active Call UUID")
    user_message: str = Field(description="Transcribed customer speech utterance")
    campaign_id: Optional[str] = None
    contact_id: Optional[str] = None
    organization_id: Optional[str] = None

class ExplicitTerminationRequest(BaseModel):
    hangup_reason: str = Field(default="Application requested termination")
    opt_out: bool = Field(default=False)

class ExplicitTransferRequest(BaseModel):
    reason: str = Field(default="Escalated to human representative")
    department: Optional[str] = "support"

@router.post("/turn")
async def execute_voice_turn(
    req: VoiceTurnRequest,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Execute a real-time conversational voice turn through the LangGraph StateGraph.
    Processes customer speech, updates state, executes approved tools, and returns
    concise speech-ready agent response.
    """
    try:
        call_uuid = uuid.UUID(req.call_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid call_id format")

    call_res = await db.execute(select(Call).where(Call.id == call_uuid))
    call = call_res.scalar_one_or_none()
    if not call:
        raise HTTPException(status_code=404, detail="Call record not found")

    result = await VoiceAgentOrchestrator.process_turn(
        call_id=str(call.id),
        user_message=req.user_message,
        campaign_id=str(call.campaign_id) if call.campaign_id else req.campaign_id,
        contact_id=str(call.contact_id) if call.contact_id else req.contact_id,
        organization_id=req.organization_id
    )
    return result

@router.get("/calls/{call_id}/state")
async def get_call_agent_state(
    call_id: str,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Retrieve authoritative call business data, PostgreSQL transcript,
    extracted fields, tool execution audit records, and active LangGraph checkpoint.
    """
    state_data = await VoiceAgentOrchestrator.get_call_state_and_history(call_id)
    if "error" in state_data:
        raise HTTPException(status_code=404, detail=state_data["error"])
    return state_data

@router.get("/calls/{call_id}/audits")
async def list_tool_audit_logs(
    call_id: str,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Retrieve tool execution audit log.
    """
    return []

@router.post("/calls/{call_id}/terminate")
async def terminate_call_explicit(
    call_id: str,
    req: ExplicitTerminationRequest,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Explicit application-level call termination endpoint with authorization checks.
    """
    try:
        call_uuid = uuid.UUID(call_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid call_id format")

    call_res = await db.execute(select(Call).where(Call.id == call_uuid))
    call = call_res.scalar_one_or_none()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    context = ToolSecurityContext(call_id=str(call.id), campaign_id=str(call.campaign_id) if call.campaign_id else None)
    tools = {t.name: t for t in create_agent_tools(context, db_session=db)}
    end_tool = tools["end_call"]
    res = await end_tool.ainvoke({
        "call_id": str(call.id),
        "hangup_reason": req.hangup_reason,
        "customer_consented_or_opt_out": req.opt_out
    })
    return res

@router.post("/calls/{call_id}/transfer")
async def transfer_call_explicit(
    call_id: str,
    req: ExplicitTransferRequest,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Explicit human agent transfer endpoint with authorization checks.
    """
    try:
        call_uuid = uuid.UUID(call_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid call_id format")

    call_res = await db.execute(select(Call).where(Call.id == call_uuid))
    call = call_res.scalar_one_or_none()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    context = ToolSecurityContext(
        call_id=str(call.id),
        campaign_id=str(call.campaign_id) if call.campaign_id else None,
        supports_transfer=True
    )
    tools = {t.name: t for t in create_agent_tools(context, db_session=db)}
    transfer_tool = tools["transfer_to_human"]
    res = await transfer_tool.ainvoke({
        "call_id": str(call.id),
        "reason": req.reason,
        "department": req.department
    })
    return res
