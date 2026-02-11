# YolkDemo — AI Sales Coach Backend

Training project replicating the Yolk backend architecture: real-time AI roleplay coaching for sales teams.

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│  REST API    │     │  WebSocket   │     │   RabbitMQ      │
│  (FastAPI)   │     │  Roleplay    │     │   (FastStream)  │
└──────┬───────┘     └──────┬───────┘     └──────┬──────────┘
       │                    │                     │
       ▼                    ▼                     ▼
┌──────────────────────────────────────────────────────────┐
│                    Service Layer                          │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐ │
│  │ Evaluation   │  │  Roleplay    │  │  Gap-to-Game    │ │
│  │ Engine       │  │  Service     │  │  Orchestrator   │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬──────────┘ │
│         │                 │                  │            │
│         ▼                 ▼                  │            │
│  ┌─────────────┐  ┌──────────────┐           │            │
│  │ LLM Client  │  │State Machine │           │            │
│  │ (OpenAI/    │  │(Conv Phases) │           │            │
│  │  Anthropic) │  └──────────────┘           │            │
│  └─────────────┘                             │            │
└──────────────────────────────┬───────────────┘            │
                               │                            │
                               ▼                            │
                    ┌─────────────────┐                     │
                    │   PostgreSQL    │◄────────────────────┘
                    │ (SQLAlchemy 2.0 │
                    │     async)      │
                    └─────────────────┘
```

## Key Components

| Component | File | What it demonstrates |
|-----------|------|---------------------|
| **State Machine** | `core/state_machine.py` | Conversation phase management with async transitions |
| **WebSocket Roleplay** | `api/websocket/roleplay.py` | Stateful WS connections, heartbeat, connection manager |
| **LLM Client** | `services/llm.py` | Async HTTP streaming, retry with backoff, multi-provider |
| **Evaluation Engine** | `services/evaluation.py` | LLM-powered transcript analysis, structured data extraction |
| **Gap-to-Game** | `services/orchestrator.py` | Algorithm: skill gaps → training scenario assignment |
| **Message Broker** | `messaging/broker.py` | FastStream + RabbitMQ event-driven pipeline |
| **Tracing** | `core/tracing.py` | OpenTelemetry distributed tracing setup |

## Quick Start

```bash
# Install uv (if not installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and setup
cd YolkDemo
uv sync --all-extras

# Start infrastructure
docker compose up -d

# Copy env
cp .env.example .env
# Edit .env with your API keys

# Run
uv run uvicorn yolk.main:app --reload --host 0.0.0.0 --port 8000

# Run tests
uv run pytest -v
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/api/v1/users/` | Create user |
| `GET` | `/api/v1/users/` | List users |
| `POST` | `/api/v1/calls/` | Upload call transcript |
| `POST` | `/api/v1/calls/{id}/evaluate` | Trigger LLM evaluation |
| `GET` | `/api/v1/calls/{id}/evaluation` | Get evaluation results |
| `GET` | `/api/v1/calls/{id}/skill-gaps` | Get detected skill gaps |
| `POST` | `/api/v1/sessions/auto-assign/{user_id}` | Auto-assign training |
| `GET` | `/api/v1/sessions/` | List all sessions |
| `GET` | `/api/v1/sessions/{id}` | Get session details |
| `GET` | `/api/v1/sessions/{id}/messages` | Get roleplay transcript |
| `POST` | `/api/v1/sessions/{id}/evaluate` | LLM analysis of roleplay |
| `WS` | `/api/v1/ws/roleplay/{session_id}` | Live roleplay session |

Swagger UI available at **http://localhost:8000/docs**

## Demo: Full Pipeline Walkthrough

### Step 1 — Create user and upload a call

```bash
# Create a sales rep
curl -s -X POST http://localhost:8000/api/v1/users/ \
  -H "Content-Type: application/json" \
  -d '{"name": "Alex Johnson", "email": "alex@acme.com"}' | python3 -m json.tool
# → note the "id" field (USER_ID)

# Upload a call transcript
curl -s -X POST http://localhost:8000/api/v1/calls/ \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "USER_ID",
    "transcript": "Rep: Hi, I wanted to show you our platform.\nBuyer: Sure, what does it do?\nRep: It helps teams close more deals with AI coaching.\nBuyer: Sounds expensive. How much?\nRep: I can send you pricing.\nBuyer: Ok, I will think about it. Bye.",
    "duration_seconds": 180
  }' | python3 -m json.tool
# → note the "id" field (CALL_ID)
```

### Step 2 — Run LLM evaluation on the call

```bash
# Gemma analyzes the transcript and scores the rep
curl -s -X POST http://localhost:8000/api/v1/calls/CALL_ID/evaluate | python3 -m json.tool

# See what skill gaps were detected
curl -s http://localhost:8000/api/v1/calls/CALL_ID/skill-gaps | python3 -m json.tool
```

### Step 3 — Auto-assign roleplay training

```bash
# The orchestrator picks training scenarios based on skill gaps
curl -s -X POST http://localhost:8000/api/v1/sessions/auto-assign/USER_ID | python3 -m json.tool
# → returns a list of sessions with scenario_id and session IDs
```

### Step 4 — Run interactive roleplay

```bash
# Interactive CLI — pick a session and practice selling
uv run python scripts/demo_roleplay.py

# Or connect to a specific session
uv run python scripts/demo_roleplay.py --session SESSION_ID
```

During the roleplay, you play the sales rep and Gemma plays the buyer persona.
Type `/quit` to end and get a full LLM evaluation of your performance.

### Step 5 — Get roleplay analysis

```bash
# Full LLM analysis of a completed roleplay session
curl -s -X POST http://localhost:8000/api/v1/sessions/SESSION_ID/evaluate | python3 -m json.tool

# View the transcript
curl -s http://localhost:8000/api/v1/sessions/SESSION_ID/messages | python3 -m json.tool
```

The analysis includes:
- **overall_score** (0-10) — how well you did
- **phase_analysis** — score and feedback per conversation phase
- **strengths / weaknesses** — what went well / what didn't
- **improvement_tips** — actionable advice
- **buyer_engagement** (0-10) — how engaged the buyer was
- **would_close_deal** — whether the buyer would sign

### Demo Script Commands

```bash
# Interactive session picker
uv run python scripts/demo_roleplay.py

# Connect to specific session
uv run python scripts/demo_roleplay.py --session SESSION_ID

# Create new training sessions for a user
uv run python scripts/demo_roleplay.py --new --user USER_ID

# Evaluate a completed session (no roleplay, just analysis)
uv run python scripts/demo_roleplay.py --evaluate SESSION_ID

# View transcript of a completed session
uv run python scripts/demo_roleplay.py --transcript SESSION_ID
```

## WebSocket Protocol

```json
// Client → Server
{"type": "message", "content": "Hi, I'm calling about your software needs..."}
{"type": "ping"}
{"type": "end_session"}

// Server → Client
{"type": "session_started", "session_id": "...", "phase": "greeting"}
{"type": "typing", "is_typing": true}
{"type": "message", "content": "...", "phase": "discovery", "turn_number": 3}
{"type": "session_ended", "evaluation_summary": {...}}
{"type": "heartbeat"}
{"type": "error", "error": "..."}
```

## Interview Prep: Key Concepts Demonstrated

### AsyncIO & Event Loop
- `services/llm.py`: Non-blocking HTTP with httpx, async streaming
- `api/websocket/roleplay.py`: `asyncio.wait_for`, `asyncio.create_task` for heartbeat
- `messaging/broker.py`: Async message consumers
- `database.py`: Async SQLAlchemy sessions with proper cleanup

### State Management
- `core/state_machine.py`: In-memory state with async lock for thread safety
- `services/roleplay.py`: Session state persisted to DB + kept in memory for active sessions
- WebSocket: Connection manager handles reconnects without losing context

### Concurrency Patterns
- Connection manager with `asyncio.Lock` for thread-safe operations
- WebSocket heartbeat as background task
- Non-blocking LLM calls with timeout
- Proper cleanup in `finally` blocks

### Database Patterns (SQLAlchemy 2.0 async)
- Async session factory with connection pooling
- Dependency injection via FastAPI `Depends`
- Proper commit/rollback/close pattern
- Mapped columns with strict typing

### Event-Driven Architecture
- FastStream + RabbitMQ for async processing pipeline
- Call uploaded → Evaluation → Gap Detection → Training Assignment
- Decoupled services communicating via message queues

### Observability
- OpenTelemetry spans on every service method
- Structured logging with structlog
- Correlation IDs through the full request lifecycle

## Tech Stack Match

| Yolk Requirement | This Project |
|-----------------|--------------|
| Python 3.12+ | ✅ `requires-python = ">=3.12"` |
| FastAPI | ✅ REST + WebSocket |
| SQLAlchemy 2.0 async | ✅ Async sessions, mapped columns |
| PostgreSQL | ✅ via asyncpg |
| WebSockets | ✅ Stateful with state machine |
| RabbitMQ + FastStream | ✅ Event-driven pipeline |
| OpenAI/Anthropic APIs | ✅ Dual provider with streaming |
| uv | ✅ Package manager |
| ruff | ✅ Linter config |
| basedpyright (strict) | ✅ Type checking |
| OpenTelemetry | ✅ Distributed tracing |
| Pydantic strict | ✅ All schemas |
