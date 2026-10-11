# LangGraph Agent Orchestration Architecture

## Overview

This document describes the LangGraph-based AI voice conversation orchestration system integrated into the FastAPI backend. The architecture separates audio transport from conversation logic, enabling real-time voice interactions with conditional tool execution, state management, and PostgreSQL persistence.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           TELEPHONY PROVIDER (Twilio)                       │
│                               (Audio I/O Layer)                              │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        AUDIO PIPELINE MANAGER                               │
│  - Receives audio from provider                                            │
│  - Sends audio to Deepgram STT                                              │
│  - Detects complete utterances                                             │
│  - Streams TTS audio back to caller                                         │
│  - Handles barge-in interruptions                                           │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     LANGGRAPH STATEGRAPH ORCHESTRATION                       │
│  ┌─────────────┐    ┌──────────────┐    ┌─────────────┐                    │
│  │  Deepgram   │───▶│   Customer   │───▶│  LangGraph  │                    │
│  │  STT Input │    │   Utterance  │    │   Graph      │                    │
│  └─────────────┘    └──────────────┘    └──────┬──────┘                    │
│                                             │                              │
│                      ┌──────────────────────┼──────────────────────┐      │
│                      │                      │                      │      │
│                      ▼                      ▼                      ▼      │
│              ┌──────────────┐      ┌──────────────┐      ┌──────────────┐  │
│              │  PostgreSQL  │      │   Gemini     │      │   Tools      │  │
│              │  (State &    │      │   Model      │      │  (Database  │  │
│              │   Context)   │      │              │      │   & API)     │  │
│              └──────────────┘      └──────────────┘      └──────────────┘  │
│                                                                             │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           POSTGRESQL DATABASE                                │
│  - Contacts & Campaigns                                                     │
│  - Consent & Suppression Records                                            │
│  - Call Records & Events                                                    │
│  - Transcripts & Extracted Fields                                           │
│  - Tool Execution Audit Logs                                                │
│  - Follow-up Schedules                                                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

## LangGraph StateGraph Structure

### Graph Nodes

```
                    START
                      │
                      ▼
               ┌──────────────┐
               │ load_context │
               └──────┬───────┘
                      │
         ┌────────────┴────────────┐
         │   route_after_context    │
         └────────────┬────────────┘
                      │
        ┌─────────────┴─────────────┐
        │                           │
        ▼                           ▼
┌───────────────┐          ┌──────────────────┐
│finalize_call  │          │process_customer  │
│ (suppressed)  │          │   _input         │
└───────────────┘          └────────┬─────────┘
                                    │
                      ┌─────────────┴────────────┐
                      │ route_after_customer_    │
                      │        input             │
                      └─────────────┬────────────┘
                                    │
                      ┌─────────────┴────────────┐
                      │                           │
                      ▼                           ▼
              ┌───────────────┐          ┌──────────────┐
              │finalize_call  │          │  call_model  │
              │ (limits/      │          └──────┬───────┘
              │  opt-out)     │                 │
              └───────────────┘                 │
                                                │
                              ┌─────────────────┴─────────────────┐
                              │      route_after_model           │
                              └─────────────────┬─────────────────┘
                                                │
              ┌─────────────────┬───────────────┼───────────────┬──────────────┐
              │                 │               │               │              │
              ▼                 ▼               ▼               ▼              ▼
    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
    │handle_error  │  │execute_tools │  │finalize_call │  │generate_voice│  │generate_voice│
    │ (retry/      │  │ (tool calls) │  │ (handoff/    │  │  _response   │  │  _response   │
    │  terminate)  │  └──────┬───────┘  │  end)        │  └──────┬───────┘  │  (conversat-  │
    └──────────────┘         │          └──────────────┘         │          │   ional)     │
                             │                                      │          └──────┬───────┘
                             ▼                                      │                 │
                    ┌──────────────┐                                 │                 │
                    │validate_tool │                                 │                 │
                    │  _results     │                                 │                 │
                    └──────┬───────┘                                 │                 │
                           │                                         │                 │
         ┌─────────────────┴─────────────────┐                      │                 │
         │    route_after_validation         │                      │                 │
         └─────────────────┬─────────────────┘                      │                 │
                           │                                         │                 │
         ┌─────────────────┼─────────────────┐                      │                 │
         │                 │                 │                      │                 │
         ▼                 ▼                 ▼                      │                 │
┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │                 │
│finalize_call  │  │generate_voice│  │  call_model  │              │                 │
│ (after tools) │  │  _response   │  │ (multi-step) │              │                 │
└──────────────┘  └──────┬───────┘  └──────────────┘              │                 │
                         │                                          │                 │
                         └──────────────────┬───────────────────────┘                 │
                                            │                                 │
                                            ▼                                 │
                                     ┌──────────────┐                        │
                                     │ persist_turn │                        │
                                     └──────┬───────┘                        │
                                            │                                 │
                                            └─────────────────┬───────────────┘
                                                              │
                                                              ▼
                                                             END
```

### Node Descriptions

#### 1. **load_context**
- **Purpose**: Load authoritative context from PostgreSQL
- **Operations**:
  - Retrieve contact identity and profile
  - Retrieve campaign script and parameters
  - Enforce consent and suppression verification
  - Initialize conversation state (turn count, duration, tool limits)
- **Outputs**: Updated state with customer info, campaign config, consent status

#### 2. **process_customer_input**
- **Purpose**: Process customer utterance and enforce boundaries
- **Operations**:
  - Increment turn count and elapsed duration
  - Enforce turn and duration limits
  - Detect opt-out phrases and create suppression records
  - Add HumanMessage to conversation history
- **Outputs**: Updated state with message, consent status, termination flags

#### 3. **call_model**
- **Purpose**: Invoke Gemini model with bound tools
- **Operations**:
  - Bind tools with security context
  - Format system prompt with campaign instructions
  - Invoke Gemini model
  - Handle model errors
- **Outputs**: AIMessage with potential tool calls or conversational response

#### 4. **execute_tools**
- **Purpose**: Execute approved tool calls with authorization
- **Operations**:
  - Enforce tool iteration limits
  - Authorize tool access against security context
  - Validate and sanitize tool arguments
  - Execute tools with database/external API calls
  - Log audit records
- **Outputs**: ToolMessages with results, updated tool count, termination flags

#### 5. **validate_tool_results**
- **Purpose**: Validate tool execution outputs
- **Operations**:
  - Check for tool execution errors
  - Validate result structures
  - Log warnings for failed tools
- **Outputs**: Validation state (no direct state changes)

#### 6. **generate_voice_response**
- **Purpose**: Format agent response for text-to-speech
- **Operations**:
  - Extract text from AIMessage or use pre-formatted response
  - Clean markdown, XML, and formatting characters
  - Optimize for spoken output
- **Outputs**: Clean, speech-ready agent response text

#### 7. **persist_turn**
- **Purpose**: Persist conversation turn to PostgreSQL
- **Operations**:
  - Update call record with turn count
  - Record dialogue turn event
  - Append to transcript
  - Update word count
- **Outputs**: Database persistence (no state changes)

#### 8. **finalize_call**
- **Purpose**: Mark call as completed or transferred
- **Operations**:
  - Update call status and hangup cause
  - Record end timestamp and duration
  - Handle transfer vs. normal completion
- **Outputs**: Updated call status

#### 9. **handle_error**
- **Purpose**: Bounded error recovery
- **Operations**:
  - Increment retry count
  - Provide polite retry response or terminate if limit reached
- **Outputs**: Retry count, termination flag, error response

### Conditional Routing Logic

#### route_after_context
- **finalize_call**: If `should_end_call` is True (suppressed or opted-out)
- **process_customer_input**: Normal flow

#### route_after_customer_input
- **finalize_call**: If `should_end_call` is True (turn limits or opt-out)
- **call_model**: Normal flow

#### route_after_model
- **handle_error**: If `error_state` is set
- **execute_tools**: If last message is AIMessage with tool_calls
- **finalize_call**: If `should_end_call` or `handoff_requested`
- **generate_voice_response**: Normal conversational response

#### route_after_validation
- **finalize_call**: If `should_end_call` or `handoff_requested`
- **call_model**: If last message was ToolMessage (multi-step reasoning)
- **generate_voice_response**: Normal response generation

## Conversation State Schema

```python
class ConversationState(TypedDict):
    # Identifiers
    conversation_id: str
    call_id: str
    campaign_id: str
    contact_id: str
    organization_id: str

    # Conversation history
    messages: Annotated[Sequence[BaseMessage], add_messages]

    # Customer and campaign context
    customer_name: Optional[str]
    contact_phone: Optional[str]
    conversation_language: str
    campaign_name: Optional[str]
    campaign_prompt: Optional[str]

    # Dynamic extraction & intent tracking
    current_intent: Optional[str]
    extracted_fields: Dict[str, Any]
    tool_results: List[Dict[str, Any]]

    # Compliance & call state
    consent_status: str  # "consented", "opted_out", "pending", "revoked"
    call_status: str     # "queued", "in_progress", "completed", "failed", "transferred"
    retry_count: int
    should_end_call: bool
    handoff_requested: bool
    error_state: Optional[str]

    # Runtime boundaries
    turn_count: int
    max_turns: int
    elapsed_duration_seconds: int
    max_duration_seconds: int
    tool_call_count: int
    max_tool_iterations: int

    # Latest turn outputs
    last_user_utterance: str
    agent_response_text: str
    is_clarification: bool
    call_outcome: Optional[str]
```

## Tool Definitions

### Available Tools

1. **get_contact_details**
   - Retrieve authorized contact information from PostgreSQL
   - Validates contact_id and organization isolation

2. **get_campaign_context**
   - Retrieve approved campaign script and configuration
   - Validates campaign_id and authorization

3. **save_conversation_field**
   - Validate and save extracted customer response field
   - Stores in ExtractedCallResult.raw_extracted_data

4. **save_call_result**
   - Store final structured call outcome
   - Updates ExtractedCallResult with validated status

5. **schedule_follow_up**
   - Schedule follow-up when permitted and requested
   - Creates CallFollowUp record with ISO datetime validation

6. **transfer_to_human**
   - Request human transfer if provider supports it
   - Checks provider configuration for transfer support

7. **end_call**
   - Request call termination with authorization checks
   - Updates call status and records hangup cause

8. **get_call_status**
   - Retrieve current call state from database
   - Returns status, duration, timestamps

### Tool Security

All tools enforce:
- Input validation with Pydantic schemas
- Authorization via ToolSecurityContext
- Organization-level data isolation
- Parameterized database queries
- Audit logging (tool name, duration, status, correlation ID)
- Timeout and bounded retries
- No arbitrary SQL, shell commands, or unrestricted network access

## Audio Pipeline Layer

### AudioPipelineManager

Separates audio transport from LangGraph execution:

1. **process_utterance_turn**
   - Acquires per-call turn lock (prevents concurrent state modifications)
   - Handles barge-in interruption detection
   - Executes LangGraph graph with stable thread_id
   - Returns agent response with termination flags

2. **synthesize_speech_stream**
   - Streams EdgeTTS audio chunks
   - Checks interruption event during playback
   - Supports real-time barge-in when caller speaks

### Session Management

- `AudioTurnSession`: Per-call state including turn lock, speaking flag, interruption event
- Prevents concurrent graph executions against same conversation state
- Enables graceful interruption handling

## PostgreSQL Integration

### Tables for LangGraph Orchestration

1. **contact_consents** - Consent status tracking
2. **suppression_records** - Opt-out and suppression list
3. **tool_execution_audit_logs** - Tool execution audit trail
4. **call_follow_ups** - Follow-up scheduling
5. **transcripts** - Full conversation transcripts
6. **extracted_call_results** - Structured extracted fields
7. **call_events** - Event log for call lifecycle

### Checkpointing

- Supports both MemorySaver (in-memory) and AsyncPostgresSaver
- Stable thread_id per call: `call_thread_{call_id}`
- Configurable checkpoint retention
- Recovery behavior after backend restarts
- Separation between transient graph state and authoritative business records

## Security & Compliance

### Consent Enforcement
- Verified application data determines consent (not model inference)
- Suppression records prevent calling opted-out numbers
- Automatic opt-out detection from customer utterances
- Immediate call termination on opt-out request

### Data Isolation
- Organization-level data boundaries enforced in all tools
- Contact/campaign ID validation against security context
- Parameterized queries prevent SQL injection
- No sensitive data in model-visible messages

### Audit Trail
- All tool executions logged with:
  - Tool name, duration, status
  - Sanitized arguments and results
  - Correlation ID for tracing
  - Error messages (without secrets)

## Error Recovery

### Bounded Retries
- Maximum 3 retry attempts for model errors
- Polite retry messages: "I apologize, could you please repeat that?"
- Termination after retry limit with: "I am experiencing technical difficulties..."

### Tool Iteration Limits
- Maximum 4 tool iterations per turn
- Prevents infinite tool-calling loops
- Terminates call if limit exceeded

### Call Duration Limits
- Configurable max_turns (default: 10)
- Configurable max_duration_seconds (default: 300)
- Graceful termination when limits reached

## FastAPI Integration

### Endpoints

1. **POST /api/v1/agent/turn**
   - Execute real-time voice turn through LangGraph
   - Accepts: call_id, user_message, campaign_id, contact_id, organization_id
   - Returns: agent_response, should_end_call, handoff_requested, turn_count

2. **GET /api/v1/agent/calls/{call_id}/state**
   - Retrieve call state, transcript, extracted fields, tool audits
   - Returns: Authoritative business data + active graph checkpoint

3. **GET /api/v1/agent/calls/{call_id}/audits**
   - Retrieve tool execution audit logs
   - Returns: List of tool execution records

4. **POST /api/v1/agent/calls/{call_id}/terminate**
   - Explicit application-level call termination
   - Requires authorization checks

5. **POST /api/v1/agent/calls/{call_id}/transfer**
   - Explicit human agent transfer
   - Checks provider transfer support

## Dependencies

### Core LangGraph Stack
- `langgraph>=0.2.0` - Graph orchestration
- `langchain-core>=0.3.0` - Core LangChain primitives
- `langchain-google-genai>=2.0.0` - Gemini integration
- `langgraph-checkpoint-postgres>=2.0.0` - PostgreSQL checkpointing
- `psycopg-pool>=3.2.0` - PostgreSQL connection pooling

### Audio & Speech
- `deepgram-sdk>=3.0.0` - Speech-to-Text
- `edge-tts>=6.1.0` - Text-to-Speech

### Database
- `sqlalchemy[asyncio]>=2.0.23` - ORM
- `asyncpg>=0.29.0` - Async PostgreSQL driver

## Workflow Example

### Normal Conversational Turn

```
1. Customer speaks: "I'm interested in learning more"
2. Deepgram transcribes: "I'm interested in learning more"
3. AudioPipelineManager.process_utterance_turn()
4. load_context: Load contact and campaign data
5. process_customer_input: Add utterance to messages
6. call_model: Gemini generates response
7. generate_voice_response: Clean response for TTS
8. persist_turn: Save to transcript and call_events
9. Return: "We would be delighted to tell you more about our services."
10. EdgeTTS synthesizes and streams audio
```

### Tool Execution Turn

```
1. Customer speaks: "Schedule a call for tomorrow at 10am"
2. Deepgram transcribes
3. LangGraph executes
4. call_model: Gemini returns AIMessage with schedule_follow_up tool call
5. execute_tools: Validate and execute schedule_follow_up tool
6. validate_tool_results: Check tool execution success
7. call_model: Generate confirmation message
8. generate_voice_response: "Great! I've scheduled a follow-up for tomorrow at 10am."
9. persist_turn: Save to database
10. Return confirmation
```

### Opt-Out Flow

```
1. Customer speaks: "Stop calling me"
2. process_customer_input: Detects opt-out keyword
3. Creates SuppressionRecord in PostgreSQL
4. Sets should_end_call = True
5. Sets consent_status = "opted_out"
6. finalize_call: Updates call status
7. generate_voice_response: "I understand completely. We will not call this number again."
8. persist_turn: Save to database
9. Return termination signal
10. Telephony provider ends call
```

## Testing Strategy

### Unit Tests
- Conditional graph routing
- Tool selection and execution
- Invalid tool arguments
- Unauthorized organization access
- Database transaction failures
- Model timeouts and malformed outputs

### Integration Tests
- Complete agent workflow with mocked LLM
- Checkpoint recovery
- Concurrent conversation isolation
- Opt-out and suppression enforcement
- Follow-up scheduling
- Tool iteration limits

### Test Environment
- In-memory SQLite for database tests
- Mock Gemini model for deterministic behavior
- Mock telephony provider for audio I/O
- No real phone calls in test suite
