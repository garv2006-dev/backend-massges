# AI Voice Calling Platform - Backend

FastAPI backend for AI-powered voice calling with PostgreSQL, telephony integration, and AI services.

## Project Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── config.py           # Application configuration using pydantic-settings
│   ├── database.py         # Async database connection and session management
│   ├── models/             # SQLAlchemy ORM models
│   │   ├── __init__.py
│   │   └── user.py
│   ├── routers/            # API route handlers
│   │   ├── __init__.py
│   │   └── main.py
│   ├── schemas/            # Pydantic schemas for request/response validation
│   │   └── __init__.py
│   ├── services/           # Business logic layer
│   │   └── __init__.py
│   ├── middleware/         # Custom middleware
│   │   └── __init__.py
│   ├── api/                # API endpoint organization
│   ├── core/               # Core utilities and constants
│   ├── repositories/       # Data access layer
│   ├── integrations/       # Third-party integrations
│   │   ├── telephony/      # Telephony provider adapters (Twilio, etc.)
│   │   ├── speech_to_text/ # STT providers (Deepgram)
│   │   ├── llm/            # LLM providers (Gemini)
│   │   └── text_to_speech/ # TTS providers (Edge-TTS, production TTS)
│   ├── workers/            # Background job workers
│   ├── security/           # Security utilities (JWT, password hashing)
│   └── utils/              # Utility functions (phone normalization, etc.)
├── alembic/                # Database migrations
│   ├── versions/
│   └── env.py
├── tests/                  # Test suite
├── main.py                 # Application entry point
├── requirements.txt        # Python dependencies
├── .env.example            # Example environment variables
├── .gitignore              # Git ignore rules
├── alembic.ini             # Alembic configuration
└── README.md               # This file
```

## Setup

1. Create a virtual environment:
   ```bash
   python -m venv .venv
   # On Windows:
   .venv\Scripts\activate
   # On Linux/Mac:
   source .venv/bin/activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```
   
   Required variables in .env:
   - DATABASE_URL: PostgreSQL connection string (use postgresql+asyncpg://)
   - SECRET_KEY: Secret key for JWT tokens
   - GEMINI_API_KEY: Google Gemini API key
   - DEEPGRAM_API_KEY: Deepgram API key
   - TWILIO_ACCOUNT_SID: Twilio account SID
   - TWILIO_AUTH_TOKEN: Twilio auth token
   - TWILIO_PHONE_NUMBER: Twilio phone number
   - REDIS_URL: Redis connection string for background workers

4. Run database migrations:
   ```bash
   alembic upgrade head
   ```

5. Test database connection (optional):
   ```bash
   python test_db_connection.py
   ```

6. Run the application:
   ```bash
   python main.py
   # or
   uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

## API Documentation

Once running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health check: http://localhost:8000/health
- Readiness check: http://localhost:8000/ready

## Database Migrations

Create a new migration:
```bash
alembic revision --autogenerate -m "description"
```

Apply migrations:
```bash
alembic upgrade head
```

Rollback migrations:
```bash
alembic downgrade -1
```

## Key Features

- Async SQLAlchemy with PostgreSQL
- JWT authentication with bcrypt password hashing
- Alembic database migrations
- Phone number normalization with phonenumbers library
- Excel import/export with pandas and openpyxl
- Telephony provider adapters (Twilio)
- Speech-to-text integration (Deepgram)
- LLM integration (Google Gemini)
- Text-to-speech integration (Edge-TTS, production providers)
- Background job processing with Celery/ARQ
- Real-time updates with WebSockets
- Role-based access control
- Audit logging
- Rate limiting
- Webhook signature validation
