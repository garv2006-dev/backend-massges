from fastapi import APIRouter
from app.api import auth, contacts, campaigns, dashboard

router = APIRouter()

# Include API routers
router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
router.include_router(contacts.router, prefix="/contacts", tags=["Contacts"])
router.include_router(campaigns.router, prefix="/campaigns", tags=["Campaigns"])
router.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])

@router.get("/")
def read_root():
    return {"message": "AI Voice Calling Platform API", "version": "1.0.0"}
