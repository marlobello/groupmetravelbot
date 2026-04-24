from __future__ import annotations

import logging

from azure.cosmos.aio import ContainerProxy
from azure.identity.aio import DefaultAzureCredential

from app.config import Settings
from app.models.groupme import GroupMeMessage
from app.models.llm import ActionType
from app.models.trip import Stage, TripItem
from app.services import groupme, itinerary, llm, storage

logger = logging.getLogger(__name__)


async def handle_message(
    message: GroupMeMessage,
    cosmos_container: ContainerProxy,
    credential: DefaultAzureCredential,
    settings: Settings,
) -> None:
    """Process an incoming GroupMe message."""
    try:
        # Idempotency check
        if await storage.check_message_processed(cosmos_container, message.group_id, message.id):
            logger.info("Message %s already processed, skipping", message.id)
            return

        # Get current trip context
        trip = await storage.get_active_trip(cosmos_container, message.group_id)
        items = (
            await storage.get_all_items(cosmos_container, message.group_id, trip.id) if trip else []
        )

        # Strip trigger keyword from message for cleaner LLM input
        clean_text = (
            message.text.replace(settings.bot_trigger_keyword, "").strip() if message.text else ""
        )

        # Get action from LLM
        action = await llm.get_bot_action(
            credential=credential,
            settings=settings,
            user_message=clean_text,
            user_name=message.name,
            trip=trip,
            items=items,
        )

        # Execute action
        response_text = await _execute_action(
            action_type=action.action,
            params=action.parameters,
            default_response=action.response_text,
            message=message,
            trip=trip,
            items=items,
            container=cosmos_container,
            credential=credential,
            settings=settings,
        )

        # Mark message as processed
        await storage.mark_message_processed(cosmos_container, message.group_id, message.id)

        # Send response
        await groupme.send_message(settings.groupme_bot_id, response_text)

    except Exception:
        logger.exception("Error handling message %s", message.id)
        await groupme.send_message(
            settings.groupme_bot_id,
            "Sorry, something went wrong. Please try again.",
        )


async def _execute_action(
    action_type: ActionType,
    params: dict,
    default_response: str,
    message: GroupMeMessage,
    trip,
    items: list,
    container: ContainerProxy,
    credential: DefaultAzureCredential,
    settings: Settings,
) -> str:
    """Execute the action determined by the LLM and return response text."""

    if action_type == ActionType.NEW_TRIP:
        name = params.get("name", "Untitled Trip")
        new_trip = await storage.create_trip(container, message.group_id, name)
        return (
            f"🌴 New trip created: {new_trip.name}! Start brainstorming by telling me your ideas."
        )

    if action_type == ActionType.ARCHIVE_TRIP:
        if not trip:
            return "There's no active trip to archive."
        await storage.archive_trip(container, message.group_id, trip.id)
        return f"📦 Trip '{trip.name}' has been archived. Start a new trip anytime!"

    if action_type == ActionType.ADD_ITEM:
        if not trip:
            return (
                "No active trip. Create one first! Say something like 'start a new trip to Hawaii'."
            )
        stage_str = params.get("stage", "brainstorming")
        item = TripItem(
            groupId=message.group_id,
            tripId=trip.id,
            stage=Stage(stage_str),
            category=params.get("category", "other"),
            title=params.get("title", "Untitled"),
            details={"notes": params.get("notes")},
            addedBy=message.name,
        )
        await storage.add_item(container, item)
        return default_response

    if action_type == ActionType.MOVE_ITEM:
        if not trip:
            return "No active trip."
        title_search = params.get("item_title", "").lower()
        new_stage = Stage(params.get("new_stage", "planning"))
        matching = [i for i in items if title_search in i.title.lower()]
        if not matching:
            return (
                f"I couldn't find an item matching '{params.get('item_title')}'. "
                "Try 'show brainstorming' to see what's there."
            )
        target = matching[0]
        await storage.move_item(container, message.group_id, target.id, new_stage)
        return default_response

    if action_type == ActionType.UPDATE_ITEM:
        if not trip:
            return "No active trip."
        title_search = params.get("item_title", "").lower()
        matching = [i for i in items if title_search in i.title.lower()]
        if not matching:
            return f"I couldn't find an item matching '{params.get('item_title')}'."
        target = matching[0]
        await storage.update_item(container, message.group_id, target.id, params.get("updates", {}))
        return default_response

    if action_type == ActionType.DELETE_ITEM:
        if not trip:
            return "No active trip."
        title_search = params.get("item_title", "").lower()
        matching = [i for i in items if title_search in i.title.lower()]
        if not matching:
            return f"I couldn't find an item matching '{params.get('item_title')}'."
        await storage.delete_item(container, message.group_id, matching[0].id)
        return default_response

    if action_type == ActionType.GENERATE_ITINERARY:
        if not trip:
            return "No active trip."
        fmt = params.get("format", "summary")
        if fmt == "full":
            try:
                url = await itinerary.generate_pdf_url(credential, settings, trip, items)
                return f"📄 Here's your full itinerary: {url}"
            except Exception:
                logger.exception("PDF generation failed")
                return itinerary.generate_summary(trip, items)
        return itinerary.generate_summary(trip, items)

    if action_type in (
        ActionType.QUERY,
        ActionType.WEB_SEARCH,
        ActionType.HELP,
        ActionType.CLARIFY,
    ):
        return default_response

    return default_response
