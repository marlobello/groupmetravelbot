# Copilot Instructions

## Project Overview

GroupMe Travel Bot — a Python FastAPI application that lives in a GroupMe group chat and helps members collaboratively plan vacations. It uses Azure OpenAI for natural language understanding and Cosmos DB for persistent trip storage.

## Architecture

GroupMe sends webhook POSTs → Azure Container Apps (FastAPI/Python) → processes via Azure OpenAI → stores in Cosmos DB → replies via GroupMe Bot API.

Key components in `src/app/`:
- **routers/webhook.py**: Receives GroupMe callbacks, returns 200 immediately, processes in background
- **services/message_handler.py**: Orchestrates the full message pipeline (idempotency check → load context → LLM → execute action → respond)
- **services/llm.py**: Azure OpenAI integration; LLM classifies intent and returns structured JSON (`BotAction`) which is validated via Pydantic before execution
- **services/storage.py**: Cosmos DB CRUD with optimistic concurrency (ETags) and message deduplication (TTL-based)
- **services/itinerary.py**: Generates plain-text summaries and PDF itineraries (WeasyPrint + Jinja2 → Blob Storage SAS URL)
- **services/groupme.py**: GroupMe Bot API client with message splitting (1000-char limit)

## Data Model

Single Cosmos DB container `trips` partitioned by `/groupId`. Two document types distinguished by `type` field:
- **Trip**: `{groupId, type:"trip", name, status}` — one active trip per group
- **TripItem**: `{groupId, type:"item", tripId, stage, category, title, details, addedBy}` — items flow through stages: brainstorming → planning → finalized

All models use Pydantic with `by_alias=True` serialization for camelCase Cosmos fields.

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
pytest tests/test_models.py -q

# Run a single test
pytest tests/test_models.py::test_trip_creation -q

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

Modules: identity, cosmos-db, openai, container-registry, storage, container-apps. All services use managed identity auth (no connection strings).

## Key Conventions

- **Async everywhere**: All service functions are async. Use `azure.cosmos.aio` and `azure.identity.aio`.
- **Background processing**: Webhook returns 200 immediately; work happens in `BackgroundTasks`.
- **Structured LLM output**: LLM returns JSON matching `BotAction` schema; always validate with Pydantic before executing.
- **Optimistic concurrency**: Use Cosmos ETags (`if_match`) on all replace/update operations.
- **Idempotency**: Track processed message IDs in Cosmos with 24-hour TTL.
- **No secrets in code**: All config via environment variables or managed identity. See `.env.example`.
