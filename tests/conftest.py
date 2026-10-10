"""Pytest configuration and async test fixtures for LangGraph testing."""

import pytest
import uuid
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.database import Base, get_db
import app.models
from app.models.user import User
from app.models.campaign import Campaign, CampaignStatus
from app.models.contact import Contact
from app.models.call import Call, CallStatus, CallDirection
from app.models.consent_record import ContactConsent, SuppressionRecord
from app.security.password import get_password_hash
from app.core.deps import get_current_user

# Test in-memory SQLite async engine
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DB_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

@pytest.fixture(autouse=True)
async def init_test_db(monkeypatch):
    """Initialize schema before each test and patch AsyncSessionLocal."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Patch AsyncSessionLocal in app.database and graph nodes
    import app.database
    import app.agent.tools.definitions
    import app.agent.graph.nodes
    import app.agent.service

    monkeypatch.setattr(app.database, "AsyncSessionLocal", TestSessionLocal)
    monkeypatch.setattr(app.agent.tools.definitions, "AsyncSessionLocal", TestSessionLocal)
    monkeypatch.setattr(app.agent.graph.nodes, "AsyncSessionLocal", TestSessionLocal)
    monkeypatch.setattr(app.agent.service, "AsyncSessionLocal", TestSessionLocal)

    yield

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional test database session."""
    async with TestSessionLocal() as session:
        yield session

@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        email="testagent@example.com",
        hashed_password=get_password_hash("password123"),
        full_name="Agent Tester",
        is_active=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user

@pytest.fixture
async def test_campaign(db_session: AsyncSession, test_user: User) -> Campaign:
    campaign = Campaign(
        id=uuid.uuid4(),
        name="Customer Experience Survey",
        description="Verify service satisfaction",
        status=CampaignStatus.IN_PROGRESS,
        agent_prompt="Inquire about customer satisfaction and schedule demo if interested.",
        max_call_duration=300,
        provider_config={
            "company_name": "Acme Global",
            "agent_name": "Maya",
            "language": "English",
            "tone": "professional"
        },
        created_by=test_user.id
    )
    db_session.add(campaign)
    await db_session.commit()
    await db_session.refresh(campaign)
    return campaign

@pytest.fixture
async def test_contact(db_session: AsyncSession) -> Contact:
    contact = Contact(
        id=uuid.uuid4(),
        name="Alex Mercer",
        phone_number="+15551234567",
        phone_number_normalized="+15551234567",
        email="alex@example.com",
        language="en",
        validation_status="valid"
    )
    db_session.add(contact)
    await db_session.commit()
    await db_session.refresh(contact)
    return contact

@pytest.fixture
async def test_call(db_session: AsyncSession, test_campaign: Campaign, test_contact: Contact) -> Call:
    call = Call(
        id=uuid.uuid4(),
        campaign_id=test_campaign.id,
        contact_id=test_contact.id,
        phone_number=test_contact.phone_number_normalized,
        direction=CallDirection.OUTBOUND,
        status=CallStatus.IN_PROGRESS,
        provider="ai_voice_engine"
    )
    db_session.add(call)
    await db_session.commit()
    await db_session.refresh(call)
    return call
