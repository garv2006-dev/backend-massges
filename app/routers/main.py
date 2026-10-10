from fastapi import APIRouter
from app.api import auth, contacts, campaigns, dashboard, agent, telephony

router = APIRouter()

# Include API routers
router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
router.include_router(contacts.router, prefix="/contacts", tags=["Contacts"])
router.include_router(campaigns.router, prefix="/campaigns", tags=["Campaigns"])
router.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
router.include_router(agent.router, prefix="/agent", tags=["Voice Agent Orchestration"])
router.include_router(telephony.router, prefix="/telephony", tags=["Telephony & Media Streams"])

@router.get("/")
def read_root():
    return {"message": "AI Voice Calling Platform API", "version": "1.0.0"}
