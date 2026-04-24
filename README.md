# GroupMe Travel Bot ("Sensei")

A GroupMe chatbot that helps groups collaboratively plan vacations using AI.

## How It Works

Add the bot to a GroupMe group and mention **@sensei** to interact. The bot uses Azure OpenAI to chat naturally about travel planning while maintaining four markdown documents:

- **trip.md** — Destination, dates, participants, budget
- **brainstorming.md** — Ideas, wish-list items, suggestions
- **planning.md** — Agreed plans (not yet booked)
- **itinerary.md** — Confirmed plans with reservations, times, confirmation numbers

The LLM reads all documents as context and updates them as the conversation progresses — moving ideas from brainstorming → planning → itinerary as the group makes decisions.

## Architecture

```
GroupMe webhook → FastAPI (Azure Container Apps)
  → Read trip docs from Azure Blob Storage
  → Send to Azure OpenAI with full context
  → LLM returns chat reply + document updates
  → Write updated docs → Reply via GroupMe API
```

**Stack**: Python 3.12 · FastAPI · Azure OpenAI (gpt-4o) · Azure Blob Storage · Azure Container Apps · Managed Identity

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v          # 45 tests
ruff check src/ tests/    # lint
```

## Deployment

Infrastructure is defined in Bicep (`infra/`). CI/CD via GitHub Actions deploys on push to `main`.

```bash
az deployment group create -g rg-travelbot -f infra/main.bicep \
  -p environmentName=travelbot groupmeBotId=<bot-id>
```

## License

See [LICENSE](LICENSE).
