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
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Frontend
    FRONTEND_ORIGIN: str = "http://localhost:3000"
    
    # API
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "AI Voice Calling Platform"
    
    # AI Providers
    GEMINI_API_KEY: Optional[str] = None
    DEEPGRAM_API_KEY: Optional[str] = None
    
    # Telephony Provider (Twilio)
    TWILIO_ACCOUNT_SID: Optional[str] = None
    TWILIO_AUTH_TOKEN: Optional[str] = None
    TWILIO_PHONE_NUMBER: Optional[str] = None
    TWILIO_API_KEY: Optional[str] = None
    TWILIO_API_SECRET: Optional[str] = None
    PUBLIC_WEBHOOK_URL: Optional[str] = None  # e.g., "https://abc123.ngrok-free.app"
    
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
