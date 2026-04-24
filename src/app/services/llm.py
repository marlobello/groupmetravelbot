from __future__ import annotations

import json
import logging

from azure.identity.aio import DefaultAzureCredential
from openai import AsyncAzureOpenAI

from app.config import Settings
from app.models.llm import ActionType, BotAction
from app.models.trip import Trip, TripItem

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are TripBot, a helpful travel planning assistant in a GroupMe group chat.
You help the group plan vacations by managing trip ideas through three stages:
- Brainstorming: casual ideas and suggestions
- Planning: agreed-upon options being researched and organized
- Finalized: confirmed bookings with concrete details (the itinerary)

When the user asks you to perform an action, respond with a JSON object containing:
- "action": one of {actions}
- "parameters": action-specific parameters (see below)
- "response_text": a natural, conversational response to send in the group chat

Actions and their parameters:
- add_item: {{"title": str, "category": "lodging"|"transport"|"activity"|"dining"|"other", \
"stage": "brainstorming"|"planning"|"finalized", "notes": str}}
- move_item: {{"item_title": str, "new_stage": "brainstorming"|"planning"|"finalized"}}
- update_item: {{"item_title": str, "updates": dict}}
- delete_item: {{"item_title": str}}
- query: {{"question": str}}
- generate_itinerary: {{"format": "summary"|"full"}}
- web_search: {{"query": str}}
- new_trip: {{"name": str}}
- archive_trip: {{}}
- help: {{}}
- clarify: {{"question": str}}

If the user's request is ambiguous, use "clarify" to ask a follow-up question.

Current trip context:
{trip_context}
"""

VALID_ACTIONS = {a.value for a in ActionType}


def _build_trip_context(trip: Trip | None, items: list[TripItem]) -> str:
    if not trip:
        return "No active trip. The user may want to start a new trip."
    lines = [f"Trip: {trip.name} (status: {trip.status})"]
    for stage in ["brainstorming", "planning", "finalized"]:
        stage_items = [i for i in items if i.stage == stage]
        lines.append(f"\n{stage.title()} ({len(stage_items)} items):")
        for item in stage_items:
            lines.append(f"  - [{item.category}] {item.title}: {item.details.notes or 'no notes'}")
    return "\n".join(lines)


async def get_bot_action(
    credential: DefaultAzureCredential,
    settings: Settings,
    user_message: str,
    user_name: str,
    trip: Trip | None,
    items: list[TripItem],
) -> BotAction:
    trip_context = _build_trip_context(trip, items)
    system_prompt = SYSTEM_PROMPT.format(
        actions=", ".join(VALID_ACTIONS),
        trip_context=trip_context,
    )

    client = AsyncAzureOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        azure_ad_token_provider=_get_token_provider(credential),
        api_version="2024-12-01-preview",
    )

    try:
        response = await client.chat.completions.create(
            model=settings.azure_openai_deployment,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"{user_name}: {user_message}"},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        content = response.choices[0].message.content
        data = json.loads(content)

        # Validate action is in whitelist
        if data.get("action") not in VALID_ACTIONS:
            return BotAction(
                action=ActionType.CLARIFY,
                parameters={
                    "question": "I'm not sure what you'd like me to do. Could you rephrase?"
                },
                response_text="I'm not sure what you'd like me to do. Could you rephrase that?",
            )

        return BotAction(**data)
    except Exception:
        logger.exception("Error getting bot action from LLM")
        return BotAction(
            action=ActionType.CLARIFY,
            parameters={},
            response_text="Sorry, I had trouble understanding that. Could you try again?",
        )
    finally:
        await client.close()


def _get_token_provider(credential: DefaultAzureCredential):
    async def provider():
        token = await credential.get_token("https://cognitiveservices.azure.com/.default")
        return token.token

    return provider
