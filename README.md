# 🗺️ Sensei — GroupMe Travel Planning Bot

An AI-powered GroupMe chatbot that helps groups collaboratively plan vacations. Mention **@sensei** in your group chat to brainstorm destinations, organize plans, and build a complete trip itinerary — all through natural conversation.

<p align="center">
  <img src="sensei.png" width="120" alt="Sensei avatar" />
</p>

## How It Works

Add Sensei to a GroupMe group and mention **@sensei** to interact. The bot uses Azure OpenAI (GPT-4o) to chat naturally about travel planning while maintaining four markdown documents that evolve as the group makes decisions:

| Document | Purpose |
|---|---|
| **trip.md** | Destination, dates, participants, budget |
| **brainstorming.md** | Ideas, wish-list items, suggestions from anyone |
| **planning.md** | Agreed plans with researched details (not yet booked) |
| **itinerary.md** | Confirmed bookings with dates, times, confirmation numbers |

The LLM reads all documents as context on every message, and returns both a chat reply and any document updates — moving ideas from brainstorming → planning → itinerary as the group progresses.

### Features

- 💬 **Natural conversation** — Ask questions, share ideas, and give instructions in plain English
- 📎 **File & image processing** — Share flight confirmations, hotel bookings, or screenshots and Sensei extracts the details (PDF, DOCX, PPTX, XLSX, images with OCR)
- 🔄 **Conversation memory** — Rolling context window so follow-up messages work naturally ("Yes, add that to the itinerary")
- 🌐 **Web viewer** — Browse trip documents as a responsive HTML page at `/trips`
- 📋 **Trip lifecycle** — Start new trips, archive completed ones, and manage the full planning pipeline

### Example Interactions

```
You:    @sensei let's plan a trip to Japan in April
Sensei: 🎌 Japan in April — cherry blossom season! Great choice! I've created
        a new trip. What cities are you thinking? Tokyo, Kyoto, Osaka...?

You:    @sensei add ryokan stay in Hakone to brainstorming
Sensei: Added to brainstorming! A traditional ryokan in Hakone would be amazing
        — volcanic hot springs with views of Mt. Fuji. Want me to research options?

You:    [shares flight confirmation PDF]
You:    @sensei add this to the itinerary
Sensei: ✈️ Got it! Added to the itinerary:
        • DFW → NRT on ANA NH175, Apr 10 at 11:05am, arriving Apr 11 at 3:15pm
        • Confirmation: ABC123
```

## Architecture

```
GroupMe webhook → FastAPI (Azure Container Apps)
  ├── Read trip docs + chat history from Azure Blob Storage
  ├── Process file/image attachments via markitdown
  ├── Send full context to Azure OpenAI (GPT-4o)
  ├── LLM returns chat reply + document updates (JSON)
  ├── Write updated docs back to storage
  └── Reply via GroupMe Bot API
```

**Stack**: Python 3.12 · FastAPI · Azure OpenAI (GPT-4o) · Azure Blob Storage · Azure Container Apps · Managed Identity

**Key design decisions:**
- **LLM-first** — No traditional CRUD; the LLM reads all docs and returns full file replacements
- **Markdown as storage** — Human-readable, easy to render, trivially versioned with blob versioning
- **Serverless** — Container Apps scales to zero, OpenAI is pay-per-token, Blob Storage is pennies/GB

📖 **Detailed docs**: [Architecture](docs/architecture.md) · [Infrastructure](docs/infrastructure.md) · [Security](docs/security.md)

## Project Structure

```
src/app/
├── main.py                         # FastAPI entrypoint + lifespan
├── config.py                       # Pydantic settings (env vars)
├── models/
│   └── groupme.py                  # GroupMe message model
├── routers/
│   ├── webhook.py                  # POST /webhook/{secret}
│   └── web.py                      # GET /trips, GET /trips/{group_id}
└── services/
    ├── message_handler.py          # Orchestrator
    ├── llm.py                      # Azure OpenAI integration
    ├── storage.py                  # Blob Storage I/O
    ├── attachment_processor.py     # File/image → markdown conversion
    └── groupme.py                  # GroupMe Bot API client

infra/
├── main.bicep                      # Infrastructure orchestrator
├── main.bicepparam                 # Parameter values
└── modules/
    ├── identity.bicep              # User-assigned managed identity
    ├── openai.bicep                # Azure OpenAI + GPT-4o deployment
    ├── storage.bicep               # Blob Storage + lifecycle policy
    └── container-apps.bicep        # Container App + environment + TLS
```

## Development

```bash
# Install
pip install -e ".[dev]"

# Test (90 tests)
pytest tests/ -v

# Lint
ruff check src/ tests/
ruff format src/ tests/
```

### Environment Variables

Copy `.env.example` and fill in values:

| Variable | Required | Description |
|---|---|---|
| `AZURE_OPENAI_ENDPOINT` | ✅ | Azure OpenAI endpoint URL |
| `AZURE_OPENAI_DEPLOYMENT` | | Model deployment name (default: `gpt-4o`) |
| `STORAGE_ACCOUNT_NAME` | ✅ | Azure Storage account name |
| `GROUPME_BOT_ID` | ✅ | GroupMe bot ID for posting replies |
| `BOT_TRIGGER_KEYWORD` | | Trigger keyword (default: `@sensei`) |
| `WEBHOOK_SECRET` | ✅ | Secret path segment for webhook URL |
| `WEB_ACCESS_KEY` | ✅ | Shared key for web UI access |
| `AZURE_CLIENT_ID` | | Managed identity client ID (for Azure deployment) |

## Deployment

Infrastructure is defined in Bicep and deployed via GitHub Actions on push to `main`.

```bash
# Manual deploy
az deployment group create -g rg-travelbot -f infra/main.bicep \
  -p environmentName=travelbot \
     groupmeBotId=<bot-id> \
     webhookSecret=<secret> \
     webAccessKey=<key> \
     containerImage=ghcr.io/marlobello/groupmetravelbot:latest
```

### CI/CD

| Workflow | Trigger | Action |
|---|---|---|
| `ci.yml` | Push / PR | Lint + test |
| `app-deploy.yml` | Push to `src/`, `Dockerfile`, `pyproject.toml` | Build container → push to GHCR → update Container App |
| `infra-deploy.yml` | Push to `infra/` | Deploy Bicep → trigger app deploy |

## Documentation

| Document | Description |
|---|---|
| [Business Requirements](docs/business-requirements.md) | Product vision, personas, three-stage planning model |
| [Technical Requirements](docs/technical-requirements.md) | Original technical specification |
| [Architecture](docs/architecture.md) | System design, data model, request lifecycle, Mermaid diagrams |
| [Infrastructure](docs/infrastructure.md) | Azure resources, Bicep structure, cost profile, CI/CD |
| [Security](docs/security.md) | Threat model, authentication, SSRF/XSS/prompt injection protections |

## License

See [LICENSE](LICENSE).
