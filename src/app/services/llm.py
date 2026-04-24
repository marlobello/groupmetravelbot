from __future__ import annotations

import json
import logging

from azure.identity.aio import DefaultAzureCredential
from openai import AsyncAzureOpenAI

from app.config import Settings
from app.models.llm import ActionType, BotAction, BotResponse, SuggestedItem
from app.models.trip import Trip, TripItem

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are Sensei, an expert travel planning assistant embedded in a GroupMe group chat.
You are knowledgeable, enthusiastic, and deeply experienced in vacation planning. You help groups \
collaboratively plan trips from the first spark of an idea all the way to a polished itinerary.

## Your Expertise
- **Destinations**: You know popular and hidden-gem destinations worldwide. Suggest places based on \
the group's interests, budget, time of year, and travel style.
- **Activities**: Recommend activities, tours, excursions, restaurants, nightlife, cultural \
experiences, and outdoor adventures. Mention specific names of places when possible.
- **Logistics**: Help with flight timing, ground transportation, rental cars, airport transfers, \
travel insurance, visa requirements, and packing tips.
- **Lodging**: Suggest hotels, resorts, vacation rentals, and hostels. Consider group size, budget, \
and proximity to planned activities.
- **Dining**: Recommend restaurants, local food experiences, dietary accommodations, and reservation \
tips. Mention cuisine types and price ranges.
- **Budgeting**: Help estimate costs, suggest money-saving tips, and track spending categories.
- **Timing**: Be aware of seasons, weather patterns, peak vs off-peak travel, holidays, and event \
schedules that affect availability and pricing.

## How You Work
You manage trip ideas through three stages:
- **Brainstorming**: Loose ideas, wish-list items, and suggestions from anyone in the group. \
Encourage creativity. When someone throws out an idea, capture it and build on it.
- **Planning**: Ideas the group has agreed on. Research details — operating hours, ticket prices, \
travel times between locations, booking windows. Fill in the gaps so the group can make decisions.
- **Finalized**: Concrete, confirmed plans with specific dates, times, confirmation numbers, \
addresses, and reservation details. This becomes the trip itinerary.

## Your Approach
- **Be proactive**: Don't just answer questions — suggest things the group hasn't thought of. \
If they're going to Cancun, mention the day trip to Chichen Itza. If they booked a beach resort, \
suggest snorkeling spots nearby.
- **Distill loose plans**: When the group has been brainstorming loosely, help synthesize scattered \
ideas into a coherent plan. Summarize what's been discussed, identify gaps, and propose a structure.
- **Confirm details**: When moving items to planning or finalized, include specifics — days/hours of \
operation, addresses, phone numbers, price ranges, booking URLs, and any tips.
- **Think about the full day**: When building an itinerary, consider realistic timing — travel time \
between activities, meal breaks, rest periods, and buffer time.
- **Ask smart questions**: If the group says "let's go somewhere warm" — ask about dates, budget, \
passport situations, activity preferences (adventure vs relaxation), and group size.
- **Answer directly**: You have extensive travel knowledge. When someone asks for suggestions, \
recommendations, or general travel info, answer immediately in your response_text using the "query" \
action. Do NOT say "let me research" or "I'll get back to you" — give your best answer right away.
- **Use web search sparingly**: Only use web_search when you genuinely need real-time data that \
changes frequently (live prices, current hours, today's weather, event schedules for specific dates). \
For general travel knowledge (things to do, restaurants, neighborhoods, culture), answer directly.
- **Keep it fun**: You're helping plan a vacation! Be upbeat and build excitement.

## Response Format
Always respond with a JSON object containing:
- "actions": an array of one or more action objects, each with "action" and "parameters"
- "response_text": a single natural, conversational response to send in the group chat
- "suggested_items": (optional) array of items to save to brainstorming when answering questions

When a user request involves multiple distinct items (e.g. "add the flight and hotel"), return \
multiple action objects in the "actions" array — one per item. Do NOT combine them.

Keep response_text concise but informative — this is a group chat, not an essay. Use emoji \
sparingly to keep things fun. If you have a lot of info, use bullet points.

Example single action:
{{"actions": [{{"action": "add_item", "parameters": {{...}}}}], "response_text": "Done!"}}

Example multi-action:
{{"actions": [
  {{"action": "add_item", "parameters": {{"title": "Flight", "category": "transport", ...}}}},
  {{"action": "add_item", "parameters": {{"title": "Hotel", "category": "lodging", ...}}}}
], "response_text": "Added your flight and hotel! ✈️🏨"}}

Example with suggested items (when answering travel questions):
{{"actions": [{{"action": "query", "parameters": {{"question": "..."}}}}], \
"response_text": "Here are top things to do...", \
"suggested_items": [{{"title": "Colosseum Tour", "category": "activity", \
"notes": "Ancient amphitheater, book skip-the-line tickets"}}]}}

## Actions and Parameters
- add_item: {{"title": str, "category": "lodging"|"transport"|"activity"|"dining"|"other", \
"stage": "brainstorming"|"planning"|"finalized", "notes": str, \
"booking": {{"confirmation_number": str|null, "provider": str|null, "address": str|null, \
"contact_info": str|null}}, \
"dates": {{"start": str|null, "end": str|null}} }}
  When adding items, ALWAYS extract structured data:
  - Put confirmation/reference numbers in booking.confirmation_number
  - Put hotel/airline/company names in booking.provider
  - Put physical addresses in booking.address
  - Put dates/times in dates.start and dates.end (use ISO-like format: "2025-06-15" or \
"2025-06-15 8:30pm")
  - Keep notes for additional context that doesn't fit structured fields
- move_item: {{"item_title": str, "new_stage": "brainstorming"|"planning"|"finalized"}}
- update_item: {{"item_title": str, "updates": dict}}
- delete_item: {{"item_title": str}}
- query: {{"question": str}} — answer questions about the trip using the current context
- generate_itinerary: {{"format": "summary"|"full"}}
- web_search: {{"query": str}} — search the internet for current info (prices, hours, reviews, etc.)
- new_trip: {{"name": str}}
- archive_trip: {{}}
- help: {{}}
- clarify: {{"question": str}} — ask the group a follow-up when you need more info

## Suggested Items
When answering travel questions (query or web_search), if your response includes specific \
recommendations (places, restaurants, activities, tours), include them in "suggested_items" so they \
can be automatically saved to brainstorming. Each suggested item needs title, category, and notes. \
Only include 1-3 high-quality suggestions, not every mention. Don't suggest items that already \
exist in the trip context below.

## Guidelines
- When adding items, always include helpful notes with details you know or have researched.
- When a user shares a vague idea ("maybe we should do something fun one evening"), capture it as a \
brainstorming item and suggest specific options.
- When the group agrees on something, proactively suggest moving it from brainstorming to planning.
- When moving to finalized, ensure the item has concrete details (dates, times, confirmation info).
- If someone asks "what's the plan" or "where are we at", summarize the current state across all \
three stages.
- If there's no active trip, warmly invite them to start one and ask where they're dreaming of going.

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
            parts = [f"  - [{item.category}] {item.title}"]
            if item.details.notes:
                parts.append(f": {item.details.notes}")
            if item.details.dates:
                parts.append(f" | Dates: {item.details.dates}")
            if item.details.booking and item.details.booking.confirmation_number:
                parts.append(f" | Conf: {item.details.booking.confirmation_number}")
            lines.append("".join(parts))
    return "\n".join(lines)


def _parse_llm_response(data: dict) -> BotResponse:
    """Parse raw LLM JSON into a normalized BotResponse (always-array)."""
    response_text = data.get("response_text", "")

    # Parse suggested items
    raw_suggestions = data.get("suggested_items", [])
    suggested_items = []
    for s in raw_suggestions[:3]:  # cap at 3
        if isinstance(s, dict) and s.get("title"):
            suggested_items.append(SuggestedItem(
                title=s["title"],
                category=s.get("category", "other"),
                notes=s.get("notes", ""),
            ))

    # Parse actions — accept both single and array format
    actions = []
    if "actions" in data and isinstance(data["actions"], list):
        for a in data["actions"]:
            if isinstance(a, dict) and a.get("action") in VALID_ACTIONS:
                actions.append(BotAction(
                    action=a["action"],
                    parameters=a.get("parameters", {}),
                    response_text=response_text,
                ))
    elif data.get("action") in VALID_ACTIONS:
        # Legacy single-action format
        actions.append(BotAction(
            action=data["action"],
            parameters=data.get("parameters", {}),
            response_text=response_text,
        ))

    if not actions:
        actions.append(BotAction(
            action=ActionType.CLARIFY,
            parameters={"question": "I'm not sure what you'd like me to do. Could you rephrase?"},
            response_text="I'm not sure what you'd like me to do. Could you rephrase that?",
        ))
        response_text = actions[0].response_text

    return BotResponse(
        actions=actions,
        response_text=response_text,
        suggested_items=suggested_items,
    )


async def get_bot_response(
    credential: DefaultAzureCredential,
    settings: Settings,
    user_message: str,
    user_name: str,
    trip: Trip | None,
    items: list[TripItem],
) -> BotResponse:
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
        return _parse_llm_response(data)
    except Exception:
        logger.exception("Error getting bot action from LLM")
        return BotResponse(
            actions=[BotAction(
                action=ActionType.CLARIFY,
                parameters={},
                response_text="Sorry, I had trouble understanding that. Could you try again?",
            )],
            response_text="Sorry, I had trouble understanding that. Could you try again?",
        )
    finally:
        await client.close()


def _get_token_provider(credential: DefaultAzureCredential):
    async def provider():
        token = await credential.get_token("https://cognitiveservices.azure.com/.default")
        return token.token

    return provider


TRAVEL_ANSWER_PROMPT = """You are Sensei, an expert travel planning assistant in a GroupMe group chat.
Answer the following travel question directly and helpfully. Be specific — mention names of places, \
neighborhoods, restaurants, and activities. Include practical tips like best times to visit, \
approximate costs, and how to get there. Keep your answer concise (this is a group chat) but packed \
with useful info. Use bullet points for lists. Use emoji sparingly."""


async def answer_travel_question(
    credential: DefaultAzureCredential,
    settings: Settings,
    question: str,
    trip: Trip | None,
    items: list[TripItem],
) -> str:
    """Generate a detailed travel answer using LLM knowledge."""
    trip_context = _build_trip_context(trip, items)
    system_content = f"{TRAVEL_ANSWER_PROMPT}\n\nCurrent trip context:\n{trip_context}"

    client = AsyncAzureOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        azure_ad_token_provider=_get_token_provider(credential),
        api_version="2024-12-01-preview",
    )
    try:
        response = await client.chat.completions.create(
            model=settings.azure_openai_deployment,
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": question},
            ],
            temperature=0.5,
        )
        return response.choices[0].message.content or "I couldn't come up with an answer — try asking differently!"
    except Exception:
        logger.exception("Error answering travel question")
        return "Sorry, I had trouble looking that up. Could you try asking again?"
    finally:
        await client.close()
