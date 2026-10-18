"""Company Details & WhatsApp Connection API.

Manages:
- Company identity (Name, Phone number, Email, Category) stored in PostgreSQL
- WhatsApp Gateway connectivity (OpenWA Session status, QR Code retrieval, Session initialization)
- Simulated / Live WhatsApp Pairing toggle for testing
"""

import logging
import uuid
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import httpx

from app.config import settings
from app.database import get_db
from app.models.company_profile import CompanyProfile
from app.integrations.telephony.openwa import OpenWATelephonyProvider

logger = logging.getLogger(__name__)
router = APIRouter()

# Global provider instance
openwa_provider = OpenWATelephonyProvider()


def serialize_profile(profile: CompanyProfile) -> Dict[str, Any]:
    """Serialize CompanyProfile ORM model to frontend JSON format."""
    return {
        "name": profile.name or "",
        "phone_number": profile.phone_number or "",
        "email": profile.email or "",
        "industry": profile.industry or "",
        "website": profile.website or "",
        "default_agent_name": profile.default_agent_name or "Sarah",
        "default_voice": profile.default_voice or "en-IN-NeerjaNeural",
        "default_language": profile.default_language or "English",
        "simulated_connected": bool(profile.simulated_connected),
        "whatsapp_phone": profile.whatsapp_phone or ""
    }


async def get_or_create_company_profile(db: AsyncSession) -> CompanyProfile:
    """Fetch existing company profile from PostgreSQL or create default record."""
    res = await db.execute(select(CompanyProfile).order_by(CompanyProfile.created_at.asc()))
    profile = res.scalars().first()
    if not profile:
        profile = CompanyProfile(
            name="",
            phone_number="",
            email="",
            industry="Customer Service & Sales Automation",
            website="",
            default_agent_name="Sarah",
            default_voice="en-IN-NeerjaNeural",
            default_language="English",
            simulated_connected=False,
            whatsapp_phone=""
        )
        db.add(profile)
        await db.commit()
        await db.refresh(profile)
    return profile


class CompanyUpdateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Company legal or operating name")
    phone_number: str = Field(..., min_length=5, max_length=50, description="Official company phone number")
    email: Optional[str] = Field(None, max_length=255, description="Support or business email")
    industry: Optional[str] = Field("Customer Service & Sales Automation", max_length=255, description="Business industry")
    website: Optional[str] = Field(None, max_length=255, description="Company website")
    default_agent_name: Optional[str] = Field("Sarah", max_length=100, description="Default AI representative name")
    default_voice: Optional[str] = Field("en-IN-NeerjaNeural", max_length=100, description="Preferred TTS Voice")
    default_language: Optional[str] = Field("English", max_length=100, description="Primary communication language")


@router.get("")
async def get_company_details(db: AsyncSession = Depends(get_db)):
    """
    Get company details from PostgreSQL and live WhatsApp connection status.
    """
    profile = await get_or_create_company_profile(db)

    # Check live OpenWA status
    session_status = await openwa_provider.get_session_status()
    raw_status = session_status.get("status", "").lower()

    # Consider connected if real OpenWA is connected/ready or if simulation toggle is on
    real_connected = raw_status in ["ready", "connected", "authenticated", "qr_ready"] and session_status.get("phone") is not None
    is_connected = real_connected or bool(profile.simulated_connected)

    # Extract phone from session if available
    session_phone = session_status.get("phone")
    if session_phone and profile.whatsapp_phone != session_phone:
        profile.whatsapp_phone = session_phone
        await db.commit()
        await db.refresh(profile)

    return {
        "company": serialize_profile(profile),
        "whatsapp": {
            "gateway_url": openwa_provider.base_url,
            "session_id": openwa_provider.session_id,
            "is_connected": is_connected,
            "real_status": session_status.get("status", "unknown"),
            "session_details": session_status,
            "simulated": bool(profile.simulated_connected)
        }
    }


@router.post("")
async def update_company_details(payload: CompanyUpdateRequest, db: AsyncSession = Depends(get_db)):
    """
    Update company details (Name, Phone number, Email, Industry, Agent settings) in PostgreSQL.
    """
    profile = await get_or_create_company_profile(db)

    profile.name = payload.name.strip()
    profile.phone_number = payload.phone_number.strip()
    profile.email = payload.email.strip() if payload.email else profile.email
    profile.industry = payload.industry.strip() if payload.industry else profile.industry
    profile.website = payload.website.strip() if payload.website else profile.website
    profile.default_agent_name = payload.default_agent_name.strip() if payload.default_agent_name else "Sarah"
    profile.default_voice = payload.default_voice or "en-IN-NeerjaNeural"
    profile.default_language = payload.default_language or "English"
    profile.whatsapp_phone = payload.phone_number.strip()

    await db.commit()
    await db.refresh(profile)

    return {
        "success": True,
        "message": "Company details updated successfully in database",
        "company": serialize_profile(profile)
    }


@router.post("/whatsapp/start-session")
async def start_whatsapp_session():
    """
    Ensure the WhatsApp session is booted and generating QR code in OpenWA Gateway.
    """
    url = f"{openwa_provider.base_url}/api/sessions/{openwa_provider.session_id}/start"
    headers = openwa_provider.get_auth_headers()
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            res = await client.post(url, headers=headers)
            if res.status_code in [200, 201]:
                return {"success": True, "data": res.json()}
            return {"success": False, "statusCode": res.status_code, "detail": res.text}
    except Exception as e:
        logger.error(f"Error starting OpenWA session: {e}")
        return {"success": False, "error": str(e)}


@router.post("/whatsapp/simulate-connect")
async def toggle_simulate_connect(enable: bool = True, db: AsyncSession = Depends(get_db)):
    """
    Toggle simulated WhatsApp connection in PostgreSQL database for rapid testing and demonstrations.
    """
    profile = await get_or_create_company_profile(db)
    profile.simulated_connected = enable
    await db.commit()
    await db.refresh(profile)

    return {
        "success": True,
        "is_connected": enable,
        "message": "WhatsApp simulated connection " + ("enabled" if enable else "disabled")
    }
