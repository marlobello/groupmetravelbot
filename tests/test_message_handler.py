from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.groupme import GroupMeMessage
from app.models.llm import ActionType, BotAction
from app.models.trip import Stage, Trip, TripItem
from app.services.message_handler import handle_message


def _make_message(text: str = "@tripbot add hotel") -> GroupMeMessage:
    return GroupMeMessage(
        id="msg-100",
        group_id="group-123",
        sender_id="user-1",
        sender_type="user",
        name="Alice",
        text=text,
        created_at=1700000000,
    )


def _make_settings():
    settings = MagicMock()
    settings.bot_trigger_keyword = "@tripbot"
    settings.groupme_bot_id = "bot-id-123"
    return settings


@pytest.mark.asyncio
@patch("app.services.message_handler.groupme")
@patch("app.services.message_handler.llm")
@patch("app.services.message_handler.storage")
async def test_idempotency_skips_duplicate(mock_storage, mock_llm, mock_groupme):
    mock_storage.check_message_processed = AsyncMock(return_value=True)

    await handle_message(
        message=_make_message(),
        cosmos_container=AsyncMock(),
        credential=AsyncMock(),
        settings=_make_settings(),
    )

    mock_llm.get_bot_action.assert_not_called()
    mock_groupme.send_message.assert_not_called()


@pytest.mark.asyncio
@patch("app.services.message_handler.groupme")
@patch("app.services.message_handler.llm")
@patch("app.services.message_handler.storage")
async def test_new_trip_action(mock_storage, mock_llm, mock_groupme):
    mock_storage.check_message_processed = AsyncMock(return_value=False)
    mock_storage.get_active_trip = AsyncMock(return_value=None)
    mock_storage.create_trip = AsyncMock(return_value=Trip(groupId="group-123", name="Hawaii Trip"))
    mock_storage.mark_message_processed = AsyncMock()

    mock_llm.get_bot_action = AsyncMock(
        return_value=BotAction(
            action=ActionType.NEW_TRIP,
            parameters={"name": "Hawaii Trip"},
            response_text="Creating Hawaii Trip!",
        )
    )
    mock_groupme.send_message = AsyncMock()

    await handle_message(
        message=_make_message("@tripbot start a new trip to Hawaii"),
        cosmos_container=AsyncMock(),
        credential=AsyncMock(),
        settings=_make_settings(),
    )

    mock_storage.create_trip.assert_called_once()
    mock_groupme.send_message.assert_called_once()
    call_text = mock_groupme.send_message.call_args[0][1]
    assert "Hawaii Trip" in call_text


@pytest.mark.asyncio
@patch("app.services.message_handler.groupme")
@patch("app.services.message_handler.llm")
@patch("app.services.message_handler.storage")
async def test_add_item_action(mock_storage, mock_llm, mock_groupme):
    trip = Trip(groupId="group-123", name="Beach Trip")
    mock_storage.check_message_processed = AsyncMock(return_value=False)
    mock_storage.get_active_trip = AsyncMock(return_value=trip)
    mock_storage.get_all_items = AsyncMock(return_value=[])
    mock_storage.add_item = AsyncMock(side_effect=lambda c, item: item)
    mock_storage.mark_message_processed = AsyncMock()

    mock_llm.get_bot_action = AsyncMock(
        return_value=BotAction(
            action=ActionType.ADD_ITEM,
            parameters={"title": "Beach Hotel", "category": "lodging", "notes": "5 stars"},
            response_text="Added Beach Hotel!",
        )
    )
    mock_groupme.send_message = AsyncMock()

    await handle_message(
        message=_make_message("@tripbot add Beach Hotel"),
        cosmos_container=AsyncMock(),
        credential=AsyncMock(),
        settings=_make_settings(),
    )

    mock_storage.add_item.assert_called_once()
    mock_groupme.send_message.assert_called_once()


@pytest.mark.asyncio
@patch("app.services.message_handler.groupme")
@patch("app.services.message_handler.llm")
@patch("app.services.message_handler.storage")
async def test_move_item_action(mock_storage, mock_llm, mock_groupme):
    trip = Trip(groupId="group-123", name="Beach Trip")
    item = TripItem(
        groupId="group-123",
        tripId=trip.id,
        title="Beach Hotel",
        addedBy="Alice",
        stage=Stage.BRAINSTORMING,
    )

    mock_storage.check_message_processed = AsyncMock(return_value=False)
    mock_storage.get_active_trip = AsyncMock(return_value=trip)
    mock_storage.get_all_items = AsyncMock(return_value=[item])
    mock_storage.move_item = AsyncMock(return_value=item)
    mock_storage.mark_message_processed = AsyncMock()

    mock_llm.get_bot_action = AsyncMock(
        return_value=BotAction(
            action=ActionType.MOVE_ITEM,
            parameters={"item_title": "Beach Hotel", "new_stage": "planning"},
            response_text="Moved Beach Hotel to planning!",
        )
    )
    mock_groupme.send_message = AsyncMock()

    await handle_message(
        message=_make_message("@tripbot move Beach Hotel to planning"),
        cosmos_container=AsyncMock(),
        credential=AsyncMock(),
        settings=_make_settings(),
    )

    mock_storage.move_item.assert_called_once()
    mock_groupme.send_message.assert_called_once()


@pytest.mark.asyncio
@patch("app.services.message_handler.groupme")
@patch("app.services.message_handler.llm")
@patch("app.services.message_handler.storage")
async def test_add_item_no_active_trip(mock_storage, mock_llm, mock_groupme):
    mock_storage.check_message_processed = AsyncMock(return_value=False)
    mock_storage.get_active_trip = AsyncMock(return_value=None)
    mock_storage.mark_message_processed = AsyncMock()

    mock_llm.get_bot_action = AsyncMock(
        return_value=BotAction(
            action=ActionType.ADD_ITEM,
            parameters={"title": "Hotel"},
            response_text="Added!",
        )
    )
    mock_groupme.send_message = AsyncMock()

    await handle_message(
        message=_make_message("@tripbot add hotel"),
        cosmos_container=AsyncMock(),
        credential=AsyncMock(),
        settings=_make_settings(),
    )

    call_text = mock_groupme.send_message.call_args[0][1]
    assert "No active trip" in call_text
