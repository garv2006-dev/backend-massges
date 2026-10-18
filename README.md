# AI Voice Calling Platform - Backend

FastAPI backend for AI-powered voice calling with PostgreSQL, telephony integration, and LangGraph agent orchestration.

## Project Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── config.py                    # Application configuration using pydantic-settings
│   ├── database.py                  # Async database connection and session management
│   ├── models/                      # SQLAlchemy ORM models
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── campaign.py
│   │   ├── contact.py
│   │   ├── call.py
│   │   ├── transcript.py
│   │   ├── consent_record.py
│   │   ├── suppression_record.py
│   │   ├── tool_execution_audit.py
│   │   └── call_follow_up.py
│   ├── routers/                     # API route handlers
│   │   ├── __init__.py
│   │   └── main.py
│   ├── schemas/                     # Pydantic schemas for request/response validation
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── campaign.py
│   │   ├── contact.py
│   │   └── call.py
│   ├── services/                    # Business logic layer
│   │   ├── __init__.py
│   │   ├── ai_voice_engine.py       # Legacy AI voice engine (for demo/chat)
│   │   ├── campaign_runner.py       # Campaign execution service
│   │   └── excel_service.py         # Excel import/export
│   ├── agent/                       # LangGraph Agent Orchestration
│   │   ├── __init__.py
│   │   ├── state.py                 # Typed conversation state
│   │   ├── gemini.py                # Gemini model integration
│   │   ├── audio_pipeline.py        # Audio transport layer
│   │   ├── service.py               # High-level orchestration
│   │   ├── graph/                   # LangGraph graph definition
│   │   │   ├── __init__.py
│   │   │   ├── builder.py           # Graph construction
│   │   │   ├── nodes.py             # Graph node implementations
│   │   │   ├── edges.py             # Conditional routing edges
│   │   │   └── checkpointer.py      # Checkpointer configuration
│   │   └── tools/                   # LangGraph tools
│   │       ├── __init__.py
│   │       ├── definitions.py       # Tool implementations
│   │       ├── schemas.py           # Tool validation schemas
│   │       └── security.py          # Tool security layer
│   ├── api/                         # API endpoint organization
│   │   ├── __init__.py
│   │   ├── auth.py                  # Authentication endpoints
│   │   ├── campaigns.py             # Campaign management
│   │   ├── contacts.py              # Contact management
│   │   ├── dashboard.py             # Dashboard analytics
│   │   ├── agent.py                 # LangGraph agent endpoints
│   │   └── telephony.py             # Telephony webhooks
│   ├── core/                        # Core utilities and constants
│   │   ├── __init__.py
│   │   └── deps.py                  # Dependency injection
│   ├── repositories/                # Data access layer
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── campaign.py
│   │   └── contact.py
│   ├── integrations/                # Third-party integrations
│   │   ├── __init__.py
│   │   ├── telephony/               # Telephony provider adapters
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   └── openwa.py
│   │   ├── speech_to_text/          # STT providers (Deepgram)
│   │   │   └── __init__.py
│   │   ├── llm/                     # LLM providers (Gemini)
│   │   │   └── __init__.py
│   │   └── text_to_speech/          # TTS providers (Edge-TTS)
│   │       └── __init__.py
│   ├── middleware/                  # Custom middleware
│   │   └── __init__.py
│   ├── workers/                     # Background job workers
│   │   └── __init__.py
│   ├── security/                    # Security utilities
│   │   ├── __init__.py
│   │   ├── jwt.py
│   │   └── password.py
│   └── utils/                       # Utility functions
│       ├── __init__.py
│       └── phone.py
├── alembic/                         # Database migrations
│   ├── versions/
│   │   ├── 001_initial_schema.py
│   │   └── 002_langgraph_orchestration.py
│   └── env.py
├── tests/                           # Test suite
│   ├── __init__.py
│   ├── conftest.py                  # Test configuration
│   ├── test_graph_edges.py          # Graph routing tests
│   ├── test_tools.py                # Tool execution tests
│   ├── test_tool_security.py        # Security tests
│   └── test_agent_integration.py    # Integration tests
├── docs/                            # Documentation
│   ├── README.md                    # Documentation index
│   ├── LANGGRAPH_ARCHITECTURE.md    # Architecture documentation
│   ├── ENVIRONMENT_SETUP.md         # Environment configuration
│   ├── RUNNING_AND_DEBUGGING.md     # Running and debugging guide
│   ├── DEPENDENCY_VERIFICATION.md   # Dependency compatibility
│   └── LANGGRAPH_DELIVERABLES_SUMMARY.md
├── main.py                          # Application entry point
├── requirements.txt                 # Python dependencies
├── .env.example                     # Example environment variables
├── .gitignore                       # Git ignore rules
├── alembic.ini                      # Alembic configuration
└── README.md                        # This file
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
   - OPENWA_BASE_URL: OpenWA Gateway base URL (default: http://localhost:2785)
   - OPENWA_SESSION_ID: WhatsApp session ID (default: default)
   - OPENWA_API_KEY: Optional OpenWA API key
   - PUBLIC_WEBHOOK_URL: Public URL for OpenWA webhooks
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

### Core Platform
- Async SQLAlchemy with PostgreSQL
- JWT authentication with bcrypt password hashing
- Alembic database migrations
- Phone number normalization with phonenumbers library
- Excel import/export with pandas and openpyxl
- Background job processing with Celery/ARQ
- Real-time updates with WebSockets
- Role-based access control
- Audit logging
- Rate limiting
- Webhook signature validation

### LangGraph Agent Orchestration
- **LangGraph StateGraph** for conversation orchestration
- **Conditional routing** for dynamic conversation flows
- **Tool calling** with 8 security-hardened tools
- **State management** with TypedDict and checkpointing
- **Gemini integration** for AI responses
- **Audio pipeline** with barge-in support
- **Consent enforcement** and opt-out detection
- **Tool audit logging** for compliance
- **Multi-step workflows** with bounded iterations
- **Error recovery** with retry logic

### Integrations
- Telephony provider adapters (OpenWA WhatsApp Gateway)
- Speech-to-text integration (Deepgram)
- LLM integration (Google Gemini)
- Text-to-speech integration (Edge-TTS, production providers)

## Documentation

Comprehensive documentation is available in the `docs/` directory:

- **[docs/LANGGRAPH_ARCHITECTURE.md](docs/LANGGRAPH_ARCHITECTURE.md)** - Complete LangGraph architecture, graph structure, and workflow documentation
- **[docs/ENVIRONMENT_SETUP.md](docs/ENVIRONMENT_SETUP.md)** - Environment variable configuration and setup guide
- **[docs/RUNNING_AND_DEBUGGING.md](docs/RUNNING_AND_DEBUGGING.md)** - Running the server, debugging graph execution, and troubleshooting
- **[docs/DEPENDENCY_VERIFICATION.md](docs/DEPENDENCY_VERIFICATION.md)** - Dependency compatibility and version verification
- **[docs/LANGGRAPH_DELIVERABLES_SUMMARY.md](docs/LANGGRAPH_DELIVERABLES_SUMMARY.md)** - Summary of LangGraph integration deliverables

## Testing

Run the test suite:

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_graph_edges.py -v

# Run with coverage
pytest tests/ --cov=app --cov-report=html
```

Test coverage includes:
- 67 unit tests for graph routing, tools, and security
- 10 integration tests for complete workflows
- Mock models for deterministic testing
