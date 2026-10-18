from fastapi import APIRouter
from app.api import auth, contacts, campaigns, dashboard, telephony, company

router = APIRouter()

# Include API routers
router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
router.include_router(company.router, prefix="/company", tags=["Company & WhatsApp"])
router.include_router(contacts.router, prefix="/contacts", tags=["Contacts"])
router.include_router(campaigns.router, prefix="/campaigns", tags=["Campaigns"])
router.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
router.include_router(telephony.router, prefix="/telephony", tags=["WhatsApp Gateway & Messaging"])

@router.get("/")
def read_root():
    return {"message": "WhatsApp Automation & AI Messaging API", "version": "1.0.0"}

