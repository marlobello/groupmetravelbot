# Copilot Instructions

## Project Overview

GroupMe Travel Bot ("Sensei") — a Python FastAPI application that lives in a GroupMe group chat and helps members collaboratively plan vacations. It uses Azure OpenAI as the primary intelligence layer and Azure Blob Storage for persistent markdown-based trip documents.

## Architecture

GroupMe webhook POST → Azure Container Apps (FastAPI/Python) → read trip docs from Blob Storage → send to Azure OpenAI with full context → LLM returns chat reply + file updates → write updated docs back → reply via GroupMe Bot API.

**Design philosophy**: The LLM does the heavy lifting (conversation, research, document editing). Python is a thin facilitator for I/O.

Key components in `src/app/`:
- **routers/webhook.py**: Receives GroupMe callbacks, returns 200 immediately, processes in background
- **services/message_handler.py**: Thin orchestrator (~90 lines) — idempotency check → read blobs → LLM → write file updates → send reply
- **services/llm.py**: Azure OpenAI integration; LLM receives all 4 trip documents as context and returns JSON with chat message + optional file updates
- **services/storage.py**: Azure Blob Storage I/O for markdown trip documents with per-group async locks for concurrency
- **services/groupme.py**: GroupMe Bot API client with message splitting (1000-char limit)

## Data Model

Each group's trip data lives in Azure Blob Storage as markdown files:

```
trips/{group_id}/active_trip.json          — pointer to current trip
trips/{group_id}/{trip_id}/trip.md          — trip name, dates, participants, details
trips/{group_id}/{trip_id}/brainstorming.md — ideas and wish-list items
trips/{group_id}/{trip_id}/planning.md      — agreed plans (not yet booked)
trips/{group_id}/{trip_id}/itinerary.md     — confirmed plans with reservations
```

Idempotency markers: `processed/{group_id}/msg-{id}` blobs (auto-cleaned by lifecycle policy).

## LLM Response Format

The LLM always returns JSON:
```json
{
  "message": "Chat reply for the group",
  "file_updates": {"brainstorming.md": "# Full updated content...", "trip.md": null, ...}
}
```
- `null` = no change to that file
- File updates contain **complete** file content (not diffs)
- Special lifecycle: `"new_trip": "name"` or `"archive_trip": true`

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
- **Background processing**: Webhook returns 200 immediately; work happens in `BackgroundTasks`.
- **LLM-first**: The LLM reads and writes trip documents directly. Python handles I/O only.
- **Concurrency**: Per-group `asyncio.Lock` serialises writes within the same replica. Blob versioning provides rollback safety.
- **Idempotency**: Persistent blob-based markers (`processed/` prefix) with lifecycle auto-cleanup.
- **No secrets in code**: All config via environment variables or managed identity. See `.env.example`.
- **Filename whitelist**: Only 4 valid filenames accepted for writes: `trip.md`, `brainstorming.md`, `planning.md`, `itinerary.md`.
