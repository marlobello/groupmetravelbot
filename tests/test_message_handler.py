from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.groupme import GroupMeMessage
from app.models.llm import ActionType, BotAction, BotResponse, SuggestedItem
from app.models.trip import Stage, Trip, TripItem
from app.services.message_handler import _parse_booking, _parse_dates, handle_message


def _make_message(text: str = "@sensei add hotel") -> GroupMeMessage:
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
    settings.bot_trigger_keyword = "@sensei"
    settings.groupme_bot_id = "bot-id-123"
    return settings


def _make_bot_response(action, params=None, response_text="Done!", suggested_items=None):
    """Helper to create a BotResponse with a single action."""
    return BotResponse(
        actions=[BotAction(action=action, parameters=params or {}, response_text=response_text)],
        response_text=response_text,
        suggested_items=suggested_items or [],
    )


def _make_multi_action_response(actions_list, response_text="Done!", suggested_items=None):
    """Helper to create a BotResponse with multiple actions."""
    actions = [
        BotAction(action=a["action"], parameters=a.get("parameters", {}), response_text=response_text)
        for a in actions_list
    ]
    return BotResponse(
        actions=actions,
        response_text=response_text,
        suggested_items=suggested_items or [],
    )


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

    mock_llm.get_bot_response.assert_not_called()
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

    mock_llm.get_bot_response = AsyncMock(
        return_value=_make_bot_response(
            ActionType.NEW_TRIP,
            {"name": "Hawaii Trip"},
            "Creating Hawaii Trip!",
        )
    )
    mock_groupme.send_message = AsyncMock()

    await handle_message(
        message=_make_message("@sensei start a new trip to Hawaii"),
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

    mock_llm.get_bot_response = AsyncMock(
        return_value=_make_bot_response(
            ActionType.ADD_ITEM,
            {
                "title": "Beach Hotel",
                "category": "lodging",
                "notes": "5 stars",
                "booking": {"confirmation_number": "BH-123", "provider": "Hilton"},
                "dates": {"start": "2025-06-15", "end": "2025-06-20"},
            },
            "Added Beach Hotel!",
        )
    )
    mock_groupme.send_message = AsyncMock()

    await handle_message(
        message=_make_message("@sensei add Beach Hotel"),
        cosmos_container=AsyncMock(),
        credential=AsyncMock(),
        settings=_make_settings(),
    )

    mock_storage.add_item.assert_called_once()
    saved_item = mock_storage.add_item.call_args[0][1]
    assert saved_item.details.booking.confirmation_number == "BH-123"
    assert saved_item.details.booking.provider == "Hilton"
    assert saved_item.details.dates == {"start": "2025-06-15", "end": "2025-06-20"}
    assert saved_item.details.notes == "5 stars"
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

    mock_llm.get_bot_response = AsyncMock(
        return_value=_make_bot_response(
            ActionType.MOVE_ITEM,
            {"item_title": "Beach Hotel", "new_stage": "planning"},
            "Moved Beach Hotel to planning!",
        )
    )
    mock_groupme.send_message = AsyncMock()

    await handle_message(
        message=_make_message("@sensei move Beach Hotel to planning"),
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

    mock_llm.get_bot_response = AsyncMock(
        return_value=_make_bot_response(
            ActionType.ADD_ITEM,
            {"title": "Hotel"},
            "Added!",
        )
    )
    mock_groupme.send_message = AsyncMock()

    await handle_message(
        message=_make_message("@sensei add hotel"),
        cosmos_container=AsyncMock(),
        credential=AsyncMock(),
        settings=_make_settings(),
    )

    call_text = mock_groupme.send_message.call_args[0][1]
    assert "No active trip" in call_text


@pytest.mark.asyncio
@patch("app.services.message_handler.groupme")
@patch("app.services.message_handler.llm")
@patch("app.services.message_handler.storage")
async def test_multi_action_adds_two_items(mock_storage, mock_llm, mock_groupme):
    """Test that multiple actions in one message are all executed."""
    trip = Trip(groupId="group-123", name="Rome Trip")
    mock_storage.check_message_processed = AsyncMock(return_value=False)
    mock_storage.get_active_trip = AsyncMock(return_value=trip)
    mock_storage.get_all_items = AsyncMock(return_value=[])
    mock_storage.add_item = AsyncMock(side_effect=lambda c, item: item)
    mock_storage.mark_message_processed = AsyncMock()

    mock_llm.get_bot_response = AsyncMock(
        return_value=_make_multi_action_response(
            [
                {"action": ActionType.ADD_ITEM, "parameters": {
                    "title": "Flight to Rome", "category": "transport", "stage": "finalized",
                    "notes": "Delta DL123",
                    "booking": {"confirmation_number": "DL789"},
                }},
                {"action": ActionType.ADD_ITEM, "parameters": {
                    "title": "Hotel Artemide", "category": "lodging", "stage": "finalized",
                    "notes": "Via Nazionale 22",
                    "booking": {"confirmation_number": "HA-4455", "address": "Via Nazionale 22, Rome"},
                }},
            ],
            "Added your flight and hotel! ✈️🏨",
        )
    )
    mock_groupme.send_message = AsyncMock()

    await handle_message(
        message=_make_message("@sensei add flight and hotel"),
        cosmos_container=AsyncMock(),
        credential=AsyncMock(),
        settings=_make_settings(),
    )

    assert mock_storage.add_item.call_count == 2
    first_item = mock_storage.add_item.call_args_list[0][0][1]
    second_item = mock_storage.add_item.call_args_list[1][0][1]
    assert first_item.title == "Flight to Rome"
    assert first_item.details.booking.confirmation_number == "DL789"
    assert second_item.title == "Hotel Artemide"
    assert second_item.details.booking.address == "Via Nazionale 22, Rome"


@pytest.mark.asyncio
@patch("app.services.message_handler.groupme")
@patch("app.services.message_handler.llm")
@patch("app.services.message_handler.storage")
async def test_suggested_items_saved_to_brainstorming(mock_storage, mock_llm, mock_groupme):
    """Test that suggested_items from LLM are auto-saved to brainstorming."""
    trip = Trip(groupId="group-123", name="Rome Trip")
    mock_storage.check_message_processed = AsyncMock(return_value=False)
    mock_storage.get_active_trip = AsyncMock(return_value=trip)
    mock_storage.get_all_items = AsyncMock(return_value=[])
    mock_storage.add_item = AsyncMock(side_effect=lambda c, item: item)
    mock_storage.mark_message_processed = AsyncMock()

    mock_llm.get_bot_response = AsyncMock(
        return_value=BotResponse(
            actions=[BotAction(
                action=ActionType.QUERY,
                parameters={"question": "What to do in Rome?"},
                response_text="Here are top things to do in Rome!",
            )],
            response_text="Here are top things to do in Rome!",
            suggested_items=[
                SuggestedItem(title="Colosseum Tour", category="activity", notes="Ancient arena"),
                SuggestedItem(title="Vatican Museums", category="activity", notes="Sistine Chapel"),
            ],
        )
    )
    mock_groupme.send_message = AsyncMock()

    await handle_message(
        message=_make_message("@sensei what to do in Rome?"),
        cosmos_container=AsyncMock(),
        credential=AsyncMock(),
        settings=_make_settings(),
    )

    # 2 suggested items should be saved
    assert mock_storage.add_item.call_count == 2
    saved = [call[0][1] for call in mock_storage.add_item.call_args_list]
    assert saved[0].title == "Colosseum Tour"
    assert saved[0].stage == Stage.BRAINSTORMING
    assert saved[0].added_by == "Sensei"
    assert "AI suggestion" in saved[0].details.notes

    # Response should mention saved items
    response = mock_groupme.send_message.call_args[0][1]
    assert "Saved 2 ideas" in response


@pytest.mark.asyncio
@patch("app.services.message_handler.groupme")
@patch("app.services.message_handler.llm")
@patch("app.services.message_handler.storage")
async def test_suggested_items_deduplicated(mock_storage, mock_llm, mock_groupme):
    """Test that suggested items already in the trip are not re-added."""
    trip = Trip(groupId="group-123", name="Rome Trip")
    existing_item = TripItem(
        groupId="group-123",
        tripId=trip.id,
        title="Colosseum Tour",
        addedBy="Alice",
        stage=Stage.BRAINSTORMING,
    )
    mock_storage.check_message_processed = AsyncMock(return_value=False)
    mock_storage.get_active_trip = AsyncMock(return_value=trip)
    mock_storage.get_all_items = AsyncMock(return_value=[existing_item])
    mock_storage.add_item = AsyncMock(side_effect=lambda c, item: item)
    mock_storage.mark_message_processed = AsyncMock()

    mock_llm.get_bot_response = AsyncMock(
        return_value=BotResponse(
            actions=[BotAction(
                action=ActionType.QUERY,
                parameters={},
                response_text="Here are things to do!",
            )],
            response_text="Here are things to do!",
            suggested_items=[
                SuggestedItem(title="Colosseum Tour", category="activity", notes="Already exists"),
                SuggestedItem(title="Pantheon Visit", category="activity", notes="Free entry"),
            ],
        )
    )
    mock_groupme.send_message = AsyncMock()

    await handle_message(
        message=_make_message("@sensei suggestions?"),
        cosmos_container=AsyncMock(),
        credential=AsyncMock(),
        settings=_make_settings(),
    )

    # Only 1 new item saved (Pantheon, not Colosseum)
    assert mock_storage.add_item.call_count == 1
    saved = mock_storage.add_item.call_args[0][1]
    assert saved.title == "Pantheon Visit"


class TestParseBooking:
    def test_full_booking(self):
        params = {"booking": {
            "confirmation_number": "ABC123",
            "provider": "Hilton",
            "address": "123 Main St",
            "contact_info": "555-1234",
        }}
        b = _parse_booking(params)
        assert b.confirmation_number == "ABC123"
        assert b.provider == "Hilton"
        assert b.address == "123 Main St"
        assert b.contact_info == "555-1234"

    def test_empty_booking(self):
        b = _parse_booking({})
        assert b.confirmation_number is None
        assert b.provider is None

    def test_partial_booking(self):
        params = {"booking": {"confirmation_number": "XYZ"}}
        b = _parse_booking(params)
        assert b.confirmation_number == "XYZ"
        assert b.provider is None

    def test_invalid_booking_type(self):
        params = {"booking": "not a dict"}
        b = _parse_booking(params)
        assert b.confirmation_number is None

    def test_empty_string_fields_become_none(self):
        params = {"booking": {"confirmation_number": "", "provider": ""}}
        b = _parse_booking(params)
        assert b.confirmation_number is None
        assert b.provider is None


class TestParseDates:
    def test_full_dates(self):
        params = {"dates": {"start": "2025-06-15", "end": "2025-06-20"}}
        d = _parse_dates(params)
        assert d == {"start": "2025-06-15", "end": "2025-06-20"}

    def test_start_only(self):
        params = {"dates": {"start": "2025-06-15"}}
        d = _parse_dates(params)
        assert d == {"start": "2025-06-15", "end": None}

    def test_empty_dates(self):
        d = _parse_dates({})
        assert d is None

    def test_null_dates(self):
        params = {"dates": {"start": None, "end": None}}
        d = _parse_dates(params)
        assert d is None

    def test_invalid_dates_type(self):
        params = {"dates": "not a dict"}
        d = _parse_dates(params)
        assert d is None
