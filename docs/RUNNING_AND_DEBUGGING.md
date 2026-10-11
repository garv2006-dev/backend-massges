# Running and Debugging LangGraph Agent Execution

This guide provides instructions for running the LangGraph voice agent, debugging graph execution, and troubleshooting common issues.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Starting the Backend Server](#starting-the-backend-server)
3. [Running LangGraph Graph Execution](#running-langgraph-graph-execution)
4. [Debugging Graph Execution](#debugging-graph-execution)
5. [Testing the Agent](#testing-the-agent)
6. [Inspecting Conversation State](#inspecting-conversation-state)
7. [Common Issues and Solutions](#common-issues-and-solutions)
8. [Performance Optimization](#performance-optimization)

---

## Prerequisites

Before running the LangGraph agent, ensure you have:

1. **Python 3.10+** installed
2. **PostgreSQL** database running
3. **Redis** server running (for caching/queues)
4. **Environment variables** configured in `.env`
5. **Dependencies** installed

### Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### Initialize Database

```bash
# Run database migrations
alembic upgrade head

# Or create tables from scratch (for development)
alembic revision --autogenerate -m "Initial schema"
alembic upgrade head
```

---

## Starting the Backend Server

### Development Mode

```bash
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Options**:
- `--reload`: Auto-reload on code changes
- `--host 0.0.0.0`: Listen on all interfaces
- `--port 8000`: Port number (default 8000)

### Production Mode

```bash
cd backend
uvicorn main:app --workers 4 --host 0.0.0.0 --port 8000
```

**Options**:
- `--workers 4`: Number of worker processes
- Remove `--reload` for production

### Verify Server is Running

```bash
curl http://localhost:8000/api/v1/health
```

Expected response:
```json
{"status": "healthy"}
```

---

## Running LangGraph Graph Execution

### Manual Graph Execution via API

The LangGraph graph is executed through the FastAPI endpoint:

```bash
curl -X POST http://localhost:8000/api/v1/agent/turn \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "call_id": "uuid-of-call",
    "user_message": "I am interested in your services",
    "campaign_id": "uuid-of-campaign",
    "contact_id": "uuid-of-contact",
    "organization_id": "uuid-of-organization"
  }'
```

**Response**:
```json
{
  "call_id": "uuid-of-call",
  "user_utterance": "I am interested in your services",
  "agent_response": "We would be delighted to help you with our services. Would you like more details?",
  "should_end_call": false,
  "handoff_requested": false,
  "call_status": "in_progress",
  "turn_count": 1
}
```

### Programmatic Execution (Python)

```python
import asyncio
from app.agent.audio_pipeline import AudioPipelineManager

async def run_conversation_turn():
    result = await AudioPipelineManager.process_utterance_turn(
        call_id="call-uuid-here",
        user_utterance="Hello, I'd like to learn more",
        campaign_id="campaign-uuid-here",
        contact_id="contact-uuid-here",
        organization_id="org-uuid-here"
    )
    print(f"Agent: {result['agent_response']}")
    print(f"Should end: {result['should_end_call']}")

asyncio.run(run_conversation_turn())
```

### Direct Graph Execution (Advanced)

For direct graph testing without the audio pipeline:

```python
import asyncio
from app.agent.graph.builder import build_voice_agent_graph
from app.agent.graph.checkpointer import get_stable_thread_id, get_checkpointer

async def execute_graph_directly():
    # Build graph
    checkpointer = await get_checkpointer(use_postgres=False)
    graph = build_voice_agent_graph(checkpointer=checkpointer)

    # Prepare initial state
    input_state = {
        "call_id": "call-uuid",
        "campaign_id": "campaign-uuid",
        "contact_id": "contact-uuid",
        "organization_id": "org-uuid",
        "last_user_utterance": "Tell me about your services"
    }

    # Execute graph
    thread_id = get_stable_thread_id("call-uuid")
    config = {"configurable": {"thread_id": thread_id}}
    result = await graph.ainvoke(input_state, config=config)

    print(f"Agent response: {result['agent_response_text']}")
    print(f"Turn count: {result['turn_count']}")

asyncio.run(execute_graph_directly())
```

---

## Debugging Graph Execution

### Enable Detailed Logging

Edit `app/config.py` or set environment variable:

```bash
export LOG_LEVEL=DEBUG
```

Or add to `.env`:
```bash
LOG_LEVEL=DEBUG
```

Then in your code:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Log Graph Execution Steps

Add logging to graph nodes:

```python
# In app/agent/graph/nodes.py
async def call_model(state: ConversationState) -> Dict[str, Any]:
    logger.info(f"Calling model with {len(state.get('messages', []))} messages")
    # ... existing code
    logger.info(f"Model response: {response.content[:100]}...")
    return updates
```

### Inspect Graph State

Use the state inspection endpoint:

```bash
curl -X GET http://localhost:8000/api/v1/agent/calls/{call_id}/state \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Response**:
```json
{
  "call_id": "uuid",
  "status": "in_progress",
  "duration_seconds": 45,
  "ai_interactions": 3,
  "transcript": "[00:05] Customer: Hello\n[00:08] AI Agent: Hi there...",
  "extracted_result": {
    "outcome": null,
    "intent": "Interested",
    "rating": null,
    "raw_data": {}
  },
  "tool_audit_logs": [
    {
      "tool_name": "get_contact_details",
      "status": "success",
      "duration_ms": 15,
      "arguments": {"contact_id": "uuid"},
      "result": {"name": "John Doe"},
      "created_at": "2026-10-11T10:00:00Z"
    }
  ],
  "active_graph_state": {
    "turn_count": 3,
    "current_intent": "Interested",
    "should_end_call": false
  }
}
```

### View Tool Execution Audit Logs

```bash
curl -X GET http://localhost:8000/api/v1/agent/calls/{call_id}/audits \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

### Step-by-Step Graph Tracing

Add custom tracing to track execution:

```python
import time

async def call_model(state: ConversationState) -> Dict[str, Any]:
    start = time.time()
    logger.info(f"[TRACE] Entering call_model node")
    logger.info(f"[TRACE] State: turn_count={state.get('turn_count')}, messages={len(state.get('messages', []))}")

    # ... existing code

    elapsed = time.time() - start
    logger.info(f"[TRACE] Exiting call_model node in {elapsed:.2f}s")
    return updates
```

### Visualize Graph Execution

LangGraph provides built-in visualization. Add this to your code:

```python
from app.agent.graph.builder import build_voice_agent_graph

# Build graph without checkpointer for visualization
graph = build_voice_agent_graph(checkpointer=None)

# Print graph structure
print(graph.get_graph().print_ascii())
```

### Debug with Python Debugger

Insert breakpoints in graph nodes:

```python
async def execute_tools(state: ConversationState) -> Dict[str, Any]:
    import pdb; pdb.set_trace()  # Python debugger
    # ... existing code
```

Or use VS Code debugger:
1. Set breakpoints in `app/agent/graph/nodes.py`
2. Run with VS Code debugger
3. Send request to trigger breakpoint

---

## Testing the Agent

### Run Unit Tests

```bash
cd backend
pytest tests/ -v
```

**Run specific test file**:
```bash
pytest tests/test_graph_edges.py -v
```

**Run with coverage**:
```bash
pytest tests/ --cov=app --cov-report=html
```

### Run Integration Tests

```bash
pytest tests/test_agent_integration.py -v
```

### Test with Mock Model

The system automatically uses a mock model when `GEMINI_API_KEY` is not set:

```python
# In .env, comment out or leave empty:
# GEMINI_API_KEY=
```

The mock model (`MockGeminiVoiceModel`) simulates:
- Normal conversational responses
- Opt-out detection
- Tool calling (schedule_follow_up, transfer_to_human, end_call)
- Clarification requests

### Test with Real Gemini Model

Set your Gemini API key:

```bash
# In .env
GEMINI_API_KEY=your-actual-gemini-api-key
```

The system will use the real Gemini model for tool calling and response generation.

### Manual Testing Script

Create `test_agent.py`:

```python
import asyncio
import uuid
from app.agent.audio_pipeline import AudioPipelineManager
from app.database import AsyncSessionLocal
from app.models.call import Call, CallStatus, CallDirection
from app.models.contact import Contact
from app.models.campaign import Campaign

async def create_test_data():
    async with AsyncSessionLocal() as db:
        # Create contact
        contact = Contact(
            id=uuid.uuid4(),
            name="Test User",
            phone_number="+15551234567",
            phone_number_normalized="+15551234567",
            email="test@example.com",
            language="en"
        )
        db.add(contact)

        # Create campaign
        campaign = Campaign(
            id=uuid.uuid4(),
            name="Test Campaign",
            status="in_progress",
            agent_prompt="Test the voice agent",
            max_call_duration=300
        )
        db.add(campaign)

        # Create call
        call = Call(
            id=uuid.uuid4(),
            campaign_id=campaign.id,
            contact_id=contact.id,
            phone_number=contact.phone_number_normalized,
            direction=CallDirection.OUTBOUND,
            status=CallStatus.IN_PROGRESS,
            provider="ai_voice_engine"
        )
        db.add(call)

        await db.commit()
        return str(call.id), str(campaign.id), str(contact.id)

async def test_conversation():
    call_id, campaign_id, contact_id = await create_test_data()

    # First turn
    result1 = await AudioPipelineManager.process_utterance_turn(
        call_id=call_id,
        user_utterance="Hello, I'm interested in your services",
        campaign_id=campaign_id,
        contact_id=contact_id,
        organization_id=str(uuid.uuid4())
    )
    print(f"Turn 1 - Agent: {result1['agent_response']}")

    # Second turn
    result2 = await AudioPipelineManager.process_utterance_turn(
        call_id=call_id,
        user_utterance="Can you tell me more about pricing?",
        campaign_id=campaign_id,
        contact_id=contact_id,
        organization_id=str(uuid.uuid4())
    )
    print(f"Turn 2 - Agent: {result2['agent_response']}")

asyncio.run(test_conversation())
```

Run with:
```bash
python test_agent.py
```

---

## Inspecting Conversation State

### Via API Endpoint

```bash
curl http://localhost:8000/api/v1/agent/calls/{call_id}/state \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Direct Database Query

```python
import asyncio
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.call import Call
from app.models.transcript import Transcript
from app.models.extracted_call_result import ExtractedCallResult

async def inspect_call(call_id: str):
    async with AsyncSessionLocal() as db:
        # Get call record
        call = await db.get(Call, uuid.UUID(call_id))
        print(f"Call status: {call.status}")
        print(f"Duration: {call.duration_seconds}s")
        print(f"Turns: {call.ai_interactions}")

        # Get transcript
        stmt = select(Transcript).where(Transcript.call_id == uuid.UUID(call_id))
        transcript = (await db.execute(stmt)).scalar_one_or_none()
        if transcript:
            print(f"\nTranscript:\n{transcript.full_transcript}")

        # Get extracted results
        stmt = select(ExtractedCallResult).where(ExtractedCallResult.call_id == uuid.UUID(call_id))
        extracted = (await db.execute(stmt)).scalar_one_or_none()
        if extracted:
            print(f"\nExtracted data: {extracted.raw_extracted_data}")

asyncio.run(inspect_call("call-uuid-here"))
```

### Checkpoint Inspection

```python
import asyncio
from app.agent.graph.builder import build_voice_agent_graph
from app.agent.graph.checkpointer import get_stable_thread_id, get_checkpointer

async def inspect_checkpoint(call_id: str):
    thread_id = get_stable_thread_id(call_id)
    checkpointer = await get_checkpointer(use_postgres=False)
    graph = build_voice_agent_graph(checkpointer=checkpointer)

    snapshot = await graph.aget_state({"configurable": {"thread_id": thread_id}})
    if snapshot:
        print(f"Checkpoint values: {snapshot.values}")
        print(f"Next node: {snapshot.next}")
        print(f"Config: {snapshot.config}")

asyncio.run(inspect_checkpoint("call-uuid-here"))
```

---

## Common Issues and Solutions

### Issue: Graph hangs or times out

**Symptoms**: Request never returns, execution stuck

**Solutions**:
1. Check if database connection is working
2. Verify Redis is running
3. Check tool execution logs for stuck operations
4. Increase timeout in graph configuration
5. Check for infinite loops in conditional edges

```python
# Add timeout to graph execution
try:
    result = await asyncio.wait_for(
        graph.ainvoke(input_state, config=config),
        timeout=30.0  # 30 second timeout
    )
except asyncio.TimeoutError:
    logger.error("Graph execution timed out")
```

### Issue: Tool execution fails with "Unauthorized"

**Symptoms**: Tool returns error about unauthorized access

**Solutions**:
1. Verify security context matches call/campaign/contact IDs
2. Check organization isolation is correct
3. Ensure call exists in database
4. Verify tool is in allowed_tools set

```python
# Debug security context
context = ToolSecurityContext(
    call_id="actual-call-id",
    campaign_id="actual-campaign-id",
    contact_id="actual-contact-id",
    organization_id="actual-org-id"
)
logger.info(f"Security context: {context}")
```

### Issue: Opt-out not detected

**Symptoms**: Customer says "stop calling" but call continues

**Solutions**:
1. Check opt-out keyword list in `process_customer_input` node
2. Verify utterance is being passed correctly
3. Check consent_status is being set
4. Verify suppression record is created

```python
# In process_customer_input node
opt_out_keywords = ["stop calling", "do not call", "don't call", "unsubscribe", "remove my number", "opt out"]
logger.info(f"Checking utterance: '{user_utterance}' against keywords: {opt_out_keywords}")
```

### Issue: Tool iteration limit exceeded

**Symptoms**: Call terminates unexpectedly with tool iteration error

**Solutions**:
1. Increase `max_tool_iterations` in state initialization
2. Check if model is making unnecessary tool calls
3. Review tool results to ensure they're not errors
4. Optimize system prompt to reduce tool usage

```python
# In load_context node
updates["max_tool_iterations"] = 8  # Increase from default 4
```

### Issue: Checkpoint not persisting

**Symptoms**: State not recovered after restart

**Solutions**:
1. Verify checkpointer is correctly initialized
2. Check thread_id is stable and consistent
3. If using PostgreSQL checkpointer, verify connection
4. Check checkpointer configuration

```python
# Verify checkpointer
checkpointer = await get_checkpointer(use_postgres=True)
# Ensure connection string is correct in DATABASE_URL
```

### Issue: Mock model used instead of real Gemini

**Symptoms**: Responses are generic, not using real AI

**Solutions**:
1. Verify `GEMINI_API_KEY` is set in `.env`
2. Check API key is valid and active
3. Ensure no typos in variable name
4. Check for leading/trailing spaces in key

```python
# Verify API key loading
from app.config import settings
print(f"GEMINI_API_KEY set: {bool(settings.GEMINI_API_KEY)}")
print(f"API key starts with: {settings.GEMINI_API_KEY[:10] if settings.GEMINI_API_KEY else 'None'}")
```

### Issue: TTS audio not streaming

**Symptoms**: Agent response generated but no audio

**Solutions**:
1. Check EdgeTTS is installed and working
2. Verify voice name is valid
3. Check audio streaming endpoint
4. Ensure telephony provider accepts audio stream

```python
# Test TTS directly
import edge_tts
communicate = edge_tts.Communicate("Hello world", "en-IN-NeerjaNeural")
await communicate.save("test.mp3")
```

### Issue: Database transaction deadlocks

**Symptoms**: Random failures with deadlock errors

**Solutions**:
1. Ensure proper session management
2. Use appropriate isolation levels
3. Minimize transaction duration
4. Add retry logic for transient failures

```python
# Add retry wrapper
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
async def safe_db_operation():
    async with AsyncSessionLocal() as db:
        # ... database operations
        pass
```

---

## Performance Optimization

### Reduce Latency

1. **Use PostgreSQL checkpointer** instead of in-memory for production
2. **Enable connection pooling** in SQLAlchemy
3. **Cache frequently accessed data** (campaign configs, contact info)
4. **Use async operations** throughout the stack

```python
# In app/database.py
engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True
)
```

### Optimize Tool Execution

1. **Batch database queries** when possible
2. **Use indexes** on frequently queried columns
3. **Cache tool results** for repeated calls
4. **Set appropriate timeouts** for external API calls

```python
# Add timeout to tool execution
try:
    result = await asyncio.wait_for(
        target_tool.ainvoke(tool_args),
        timeout=10.0  # 10 second timeout per tool
    )
except asyncio.TimeoutError:
    logger.error(f"Tool {tool_name} timed out")
    res_content = {"error": "Tool execution timeout"}
```

### Monitor Performance

Add performance logging:

```python
import time
from functools import wraps

def log_performance(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start = time.time()
        result = await func(*args, **kwargs)
        elapsed = time.time() - start
        logger.info(f"{func.__name__} completed in {elapsed:.2f}s")
        return result
    return wrapper

# Apply to graph nodes
@log_performance
async def call_model(state: ConversationState) -> Dict[str, Any]:
    # ... existing code
```

### Load Testing

Use `locust` or similar tool to test concurrent load:

```python
# locustfile.py
from locust import HttpUser, task, between

class AgentUser(HttpUser):
    wait_time = between(1, 3)

    @task
    def process_turn(self):
        self.client.post(
            "/api/v1/agent/turn",
            json={
                "call_id": "test-call-id",
                "user_message": "Test message",
                "campaign_id": "test-campaign-id",
                "contact_id": "test-contact-id"
            },
            headers={"Authorization": "Bearer test-token"}
        )
```

Run load test:
```bash
locust -f locustfile.py --host=http://localhost:8000
```

---

## Summary

- Start the backend with `uvicorn main:app --reload`
- Execute graph via `/api/v1/agent/turn` endpoint
- Enable DEBUG logging for detailed execution traces
- Use state inspection endpoint to debug issues
- Run tests with `pytest tests/`
- Mock model for testing, real Gemini for production
- Monitor tool audit logs for security and performance
- Optimize database queries and connection pooling
- Use timeouts and retry logic for robustness
