# Technical Requirements Document — GroupMe Travel Bot

## 1. Architecture Overview

```
┌────────────┐     HTTPS POST      ┌──────────────────────────────┐
│  GroupMe    │ ──────────────────→ │  Azure Container Apps        │
│  Chat Group │ ←────────────────── │  (Python / FastAPI)          │
└────────────┘   GroupMe Bot API    │                              │
                                    │  ┌────────────────────────┐  │
                                    │  │ Webhook Receiver       │  │
                                    │  │ Message Router         │  │
                                    │  │ LLM Pipeline           │  │
                                    │  │ Storage Layer          │  │
                                    │  │ Itinerary Generator    │  │
                                    │  └────────────────────────┘  │
                                    └──────┬──────────┬────────────┘
                                           │          │
                              ┌────────────┘          └──────────────┐
                              ▼                                      ▼
                    ┌──────────────────┐                 ┌───────────────────┐
                    │ Azure OpenAI     │                 │ Azure Cosmos DB   │
                    │ Service          │                 │ (Serverless)      │
                    │                  │                 │                   │
                    │ • Chat completion│                 │ • brainstorming   │
                    │ • Web search     │                 │ • planning        │
                    │   grounding      │                 │ • finalized       │
                    └──────────────────┘                 └───────────────────┘
```

**Request flow**: GroupMe sends an HTTP POST to the bot's callback URL on every group message → Azure Container Apps receives the request → the message handler checks for @mention/trigger → if triggered, the LLM pipeline builds a prompt with trip context from Cosmos DB → Azure OpenAI generates a response → the bot posts back via GroupMe Bot API.

## 2. Components

### 2.1 Webhook Receiver

- **Framework**: FastAPI (latest stable)
- **Endpoint**: `POST /webhook` — receives GroupMe message payloads.
- **Validation**: Verify payload structure; ignore messages sent by the bot itself (prevent loops).
- **Health check**: `GET /health` for Container Apps probes.

### 2.2 Message Router

- Parses the incoming message text for @mention or trigger keyword.
- Classifies the intent (question, add item, move item, show contents, generate itinerary, web search, manage trip).
- Routes to the appropriate handler in the LLM pipeline.

### 2.3 LLM Pipeline

- **Provider**: Azure OpenAI Service.
- **Model**: GPT-4o (or latest recommended chat model at time of deployment).
- **System prompt**: Includes the bot's persona, the current trip context (stage summaries from Cosmos DB), and instructions for structured output when needed.
- **Web search**: Use Azure OpenAI's built-in web search grounding (Bing-backed). If this proves insufficient, fall back to a dedicated Bing Web Search API resource.
- **Structured output**: For storage operations (add/move items), the LLM returns structured JSON that the storage layer can process.

### 2.4 Storage Layer

- **Service**: Azure Cosmos DB for NoSQL, serverless capacity mode.
- **Database**: One database per deployment (e.g., `travelbot`).
- **Container strategy**: A single container `trips` with partition key `/groupId`.
- **SDK**: `azure-cosmos` Python SDK (latest stable).
- **Authentication**: Managed identity (no connection strings in code or config).

### 2.5 Itinerary Generator

- **Chat summary**: Plain text, day-by-day format, posted directly via GroupMe Bot API.
- **Full document**: Generated as PDF using WeasyPrint (or similar). Stored in Azure Blob Storage with a time-limited SAS URL shared in chat.
- **Template**: Jinja2 HTML template → rendered to PDF.

### 2.6 GroupMe Integration

- **Bot API**: Register a bot at `https://dev.groupme.com` per group. Each bot has a `bot_id` used to post messages.
- **Posting messages**: `POST https://api.groupme.com/v3/bots/post` with `bot_id` and `text`.
- **Message length**: GroupMe has a 1000-character limit per message. Long responses must be split across multiple messages.

## 3. Data Model

### 3.1 Trip Document

```json
{
  "id": "<unique-trip-id>",
  "groupId": "<groupme-group-id>",
  "type": "trip",
  "name": "Costa Rica 2026",
  "status": "active",
  "createdAt": "2026-04-24T00:00:00Z",
  "updatedAt": "2026-04-24T00:00:00Z"
}
```

### 3.2 Trip Item Document

```json
{
  "id": "<unique-item-id>",
  "groupId": "<groupme-group-id>",
  "type": "item",
  "tripId": "<trip-id>",
  "stage": "brainstorming | planning | finalized",
  "category": "lodging | transport | activity | dining | other",
  "title": "Beachfront Airbnb in Tulum",
  "details": {
    "notes": "Found by Maria, ~$150/night, has pool",
    "links": ["https://..."],
    "dates": { "start": "2026-07-10", "end": "2026-07-14" },
    "booking": {
      "confirmationNumber": null,
      "provider": null,
      "address": null,
      "contactInfo": null
    }
  },
  "addedBy": "<groupme-user-name>",
  "createdAt": "2026-04-24T00:00:00Z",
  "updatedAt": "2026-04-24T00:00:00Z"
}
```

### 3.3 Partition Strategy

- Partition key: `/groupId` — all items for a group are colocated for efficient queries.
- Queries scoped to `groupId` + `tripId` + `stage` cover all access patterns.

## 4. Azure Infrastructure (Bicep)

All resources provisioned via Bicep templates. No manual resource creation.

### 4.1 Resource List

| Resource | SKU / Tier | Purpose |
|---|---|---|
| Resource Group | — | Logical container |
| Azure Container Apps Environment | Consumption | Hosting environment |
| Azure Container App | Consumption (scale 0–1) | Bot application |
| GitHub Container Registry (GHCR) | Free (GitHub) | Store bot container image |
| Azure Cosmos DB Account | Serverless | Trip data storage |
| Azure OpenAI Service | S0 | LLM for chat and web search grounding |
| Azure Blob Storage Account | Standard LRS, Hot | Itinerary PDF storage |
| User-Assigned Managed Identity | — | Inter-service authentication |
| Bing Web Search (conditional) | S1 | Only if Azure OpenAI grounding is insufficient |

### 4.2 Bicep Structure

```
infra/
├── main.bicep              # Orchestrates all modules
├── main.bicepparam         # Parameter file
├── modules/
│   ├── container-apps.bicep
│   ├── cosmos-db.bicep
│   ├── openai.bicep
│   ├── storage.bicep
│   └── identity.bicep
```

### 4.3 Cost Minimization

- **Cosmos DB serverless**: Pay per RU consumed; no cost at rest.
- **Container Apps consumption**: Scale to zero when idle; no charge when no requests.
- **Azure OpenAI**: Pay per token; no provisioned throughput.
- **Blob Storage**: Minimal cost for occasional PDF storage.
- **GHCR**: Free container image storage with GitHub plan.
- **No always-on resources**: Everything scales to zero or is pay-per-use.
## 5. Key Libraries

| Library | Purpose |
|---|---|
| `fastapi` | HTTP framework for webhook receiver |
| `uvicorn` | ASGI server |
| `azure-cosmos` | Cosmos DB SDK |
| `openai` | Azure OpenAI SDK (supports Azure endpoints natively) |
| `pydantic` | Data validation and serialization |
| `weasyprint` | HTML-to-PDF generation for itineraries |
| `jinja2` | HTML templating for itinerary documents |
| `azure-identity` | Managed identity authentication |
| `azure-storage-blob` | Blob storage for generated PDFs |
| `httpx` | HTTP client for GroupMe Bot API calls |

All libraries pinned to latest stable release at time of implementation.

## 6. CI/CD (GitHub Actions)

### 6.1 Workflow

1. On push to `main`: lint → test → build container image → push to ACR → deploy via Bicep.
2. On pull request: lint → test only.

### 6.2 Pipeline Steps

- **Lint**: `ruff check` and `ruff format --check`
- **Test**: `pytest` with coverage
- **Build**: `docker build` → tag with commit SHA
- **Push**: `docker push` to GitHub Container Registry (GHCR)
- **Deploy**: `az containerapp update` to pull latest image from GHCR

## 7. Security Considerations

- **No secrets in code**: All credentials via managed identity or Azure Key Vault.
- **GroupMe bot token**: Stored as a Container Apps secret (sourced from Key Vault if needed).
- **HTTPS only**: Container Apps provides TLS termination.
- **Input validation**: All incoming GroupMe payloads validated via Pydantic models.
- **Bot loop prevention**: Bot ignores messages from its own sender ID.

## 8. Non-Functional Requirements

| Requirement | Target |
|---|---|
| Response latency | < 10 seconds from message to bot reply (excluding cold start) |
| Availability | Best-effort; acceptable cold start delay of ~30 seconds |
| Data durability | Cosmos DB provides automatic replication within region |
| Scalability | Single instance sufficient for MVP; Container Apps can scale if needed |
| Observability | Container Apps built-in logging; structured logs via Python `logging` module |
