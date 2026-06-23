# Copilot Instructions

## Project Overview

GroupMe Travel Bot ("Sensei") — a Python FastAPI application that lives in a GroupMe group chat and helps members collaboratively plan vacations. It uses the **Microsoft Agent Framework** with Azure OpenAI as the intelligence layer and Azure Blob Storage for persistent markdown-based trip documents.

## Architecture

GroupMe webhook POST → Azure Container Apps (FastAPI/Python) → read trip docs from Blob Storage → Microsoft Agent Framework (OpenAI agent with function tools, web search, session persistence) → tools handle document writes as side effects → reply via GroupMe Bot API.

**Design philosophy**: The agent does the heavy lifting (conversation, research, document editing via tools). Python is a thin facilitator for I/O.

Key components in `src/app/`:
- **routers/webhook.py**: Receives GroupMe callbacks, validates the secret, and processes synchronously (awaits the handler so Container Apps keeps the replica alive while `minReplicas: 0`)
- **services/message_handler.py**: Thin orchestrator — atomic idempotency claim (under per-group lock) → read blobs → route to agent → send reply
- **services/agent.py**: Microsoft Agent Framework integration — creates agent with tools, middleware, context providers, and session
- **services/tools.py**: `@tool`-decorated function tools: `write_trip_file`, `create_trip`, `archive_trip`
- **services/history_provider.py**: `BlobHistoryProvider` — automatic conversation persistence via framework's `HistoryProvider` (context provider pattern)
- **services/storage.py**: Azure Blob Storage I/O for markdown trip documents
- **services/groupme.py**: GroupMe Bot API client with message splitting (1000-char limit)

## Data Model

Each group's trip data lives in Azure Blob Storage as markdown files:

```
trips/{group_id}/active_trip.json          — pointer to current trip
trips/{group_id}/session_history.json      — agent conversation history (last 40 messages)
trips/{group_id}/{trip_id}/trip.md          — trip name, dates, participants, details
trips/{group_id}/{trip_id}/brainstorming.md — ideas and wish-list items
trips/{group_id}/{trip_id}/planning.md      — agreed plans (not yet booked)
trips/{group_id}/{trip_id}/itinerary.md     — confirmed plans with reservations
```

Idempotency markers: `processed/{group_id}/msg-{id}` blobs (auto-cleaned by lifecycle policy).

## Agent Framework

The bot uses `agent-framework-core` and `agent-framework-openai` (v1.2.2+):
- **Agent**: `OpenAIChatCompletionClient.as_agent()` with tools, middleware, and context providers
- **Tools**: `@tool`-decorated async methods on `TripTools` class — the agent calls these as side effects
- **History**: `BlobHistoryProvider` (extends `HistoryProvider`, a `ContextProvider`) — framework auto-loads/saves conversation history
- **Session**: `agent.create_session(session_id=group_id)` — keyed by GroupMe group for conversation continuity
- **Middleware**: `LoggingMiddleware` for observability
- **Client reuse**: `agent.py` caches the `OpenAIChatCompletionClient` per credential/endpoint/deployment/api-version instead of rebuilding it per message

## Build, Test, and Lint

```bash
# Install dependencies
pip install -e ".[dev]"

# Lint
ruff check src/ tests/
ruff format --check src/ tests/

# Run all tests
pytest tests/ -q

# Run a single test file
pytest tests/test_storage.py -q

# Auto-format
ruff format src/ tests/

# Dev server (requires .env with real credentials)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Infrastructure

All Azure resources are defined in Bicep (`infra/`) — never create or modify resources manually.

```bash
# Deploy infrastructure (requires Azure CLI login)
az deployment group create -g <resource-group> -f infra/main.bicep -p environmentName=travelbot groupmeBotId=<bot-id>
```

Modules: identity, openai, storage, container-apps. All services use managed identity auth (no connection strings). Blob Storage has versioning and soft delete enabled for document safety.

## Key Conventions

- **Async everywhere**: All service functions are async. Use `azure.storage.blob.aio` and `azure.identity.aio`.
- **Synchronous processing**: The webhook `await`s `handle_message` and returns 200 only after the reply is sent. This is deliberate: it keeps the request in flight so Container Apps does not scale the replica to zero mid-processing while `minReplicas: 0`. Do not reintroduce `BackgroundTasks`.
- **LLM-first**: The LLM reads and writes trip documents directly. Python handles I/O only.
- **Concurrency**: Per-group `asyncio.Lock` serialises processing within the same replica. Blob versioning provides rollback safety.
- **Idempotency**: `storage.claim_message_processed` does an atomic conditional PUT (`overwrite=False`) on a `processed/{group_id}/msg-{id}` marker under the per-group lock before processing, so duplicate webhook deliveries are skipped. Markers are auto-cleaned by a lifecycle policy.
- **No secrets in code**: All config via environment variables or managed identity. See `.env.example`.
- **Filename whitelist**: Only 4 valid filenames accepted for writes: `trip.md`, `brainstorming.md`, `planning.md`, `itinerary.md`.
