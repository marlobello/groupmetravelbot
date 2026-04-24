from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class ActionType(StrEnum):
    ADD_ITEM = "add_item"
    MOVE_ITEM = "move_item"
    UPDATE_ITEM = "update_item"
    DELETE_ITEM = "delete_item"
    QUERY = "query"
    GENERATE_ITINERARY = "generate_itinerary"
    WEB_SEARCH = "web_search"
    NEW_TRIP = "new_trip"
    ARCHIVE_TRIP = "archive_trip"
    HELP = "help"
    CLARIFY = "clarify"


class SuggestedItem(BaseModel):
    """An item the LLM suggests saving to brainstorming."""

    title: str
    category: str = "other"
    notes: str = ""


class BotAction(BaseModel):
    action: ActionType
    parameters: dict = {}
    response_text: str = ""


class BotResponse(BaseModel):
    """Normalized LLM response — always contains a list of actions."""

    actions: list[BotAction]
    response_text: str
    suggested_items: list[SuggestedItem] = []
