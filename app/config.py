from pydantic_settings import BaseSettings
from dotenv import load_dotenv
from typing import Optional

load_dotenv()

class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/mydb"
    
    # Security
    SECRET_KEY: str = "your-secret-key-here-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080  # 7 days (7 * 24 * 60 minutes)
    
    # Frontend
    FRONTEND_ORIGIN: str = "http://localhost:3000"
    
    # API
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "AI Voice Calling Platform"
    
    # AI Providers
    GEMINI_API_KEY: Optional[str] = None
    DEEPGRAM_API_KEY: Optional[str] = None
    
    # WhatsApp Telephony Gateway (OpenWA)
    OPENWA_BASE_URL: str = "http://localhost:2785"
    OPENWA_API_KEY: Optional[str] = None
    OPENWA_SESSION_ID: str = "default"
    OPENWA_WEBHOOK_SECRET: Optional[str] = None
    PUBLIC_WEBHOOK_URL: Optional[str] = None  # e.g., Cloudflare tunnel or ngrok webhook URL
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Application Settings
    MAX_CALL_DURATION: int = 300
    MAX_RETRIES: int = 3
    CAMPAIGN_CONCURRENCY_LIMIT: int = 5
    DEFAULT_PHONE_REGION: str = "IN"

    # Clerk (Optional)
    CLERK_SECRET_KEY: Optional[str] = None
    CLERK_PUBLISHABLE_KEY: Optional[str] = None
    
    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
