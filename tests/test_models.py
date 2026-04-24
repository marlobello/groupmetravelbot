from __future__ import annotations

from app.models.groupme import GroupMeMessage
from app.models.llm import ActionType, BotAction
from app.models.trip import (
    BookingDetails,
    Category,
    ItemDetails,
    Stage,
    Trip,
    TripItem,
    TripStatus,
)


class TestTrip:
    def test_trip_defaults(self):
        trip = Trip(groupId="g1", name="Beach Vacation")
        assert trip.group_id == "g1"
        assert trip.name == "Beach Vacation"
        assert trip.status == TripStatus.ACTIVE
        assert trip.type == "trip"
        assert trip.id  # should be a UUID string

    def test_trip_alias_serialization(self):
        trip = Trip(groupId="g1", name="Test")
        dumped = trip.model_dump(by_alias=True)
        assert "groupId" in dumped
        assert "createdAt" in dumped
        assert "updatedAt" in dumped

    def test_trip_populate_by_name(self):
        trip = Trip(group_id="g1", name="Test")
        assert trip.group_id == "g1"


class TestTripItem:
    def test_item_defaults(self):
        item = TripItem(groupId="g1", tripId="t1", title="Hotel", addedBy="Alice")
        assert item.stage == Stage.BRAINSTORMING
        assert item.category == Category.OTHER
        assert item.details.notes is None
        assert item.details.booking.confirmation_number is None
        assert item.type == "item"

    def test_item_with_details(self):
        item = TripItem(
            groupId="g1",
            tripId="t1",
            title="Flight",
            addedBy="Bob",
            stage=Stage.FINALIZED,
            category=Category.TRANSPORT,
            details={
                "notes": "Direct flight",
                "booking": {"confirmation_number": "XYZ"},
            },
        )
        assert item.stage == Stage.FINALIZED
        assert item.details.booking.confirmation_number == "XYZ"

    def test_item_alias_serialization(self):
        item = TripItem(groupId="g1", tripId="t1", title="Hotel", addedBy="Alice")
        dumped = item.model_dump(by_alias=True)
        assert "groupId" in dumped
        assert "tripId" in dumped
        assert "addedBy" in dumped


class TestGroupMeMessage:
    def test_message_creation(self):
        msg = GroupMeMessage(
            id="msg1",
            group_id="g1",
            sender_id="u1",
            sender_type="user",
            name="Alice",
            text="Hello @tripbot",
            created_at=1700000000,
        )
        assert msg.id == "msg1"
        assert msg.text == "Hello @tripbot"
        assert msg.attachments == []

    def test_message_optional_text(self):
        msg = GroupMeMessage(
            id="msg2",
            group_id="g1",
            sender_id="u1",
            sender_type="user",
            name="Alice",
            created_at=1700000000,
        )
        assert msg.text is None


class TestItemDetails:
    def test_defaults(self):
        details = ItemDetails()
        assert details.notes is None
        assert details.links == []
        assert details.dates is None
        assert details.booking == BookingDetails()

    def test_booking_details(self):
        booking = BookingDetails(
            confirmation_number="ABC",
            provider="Hilton",
            address="123 Main St",
            contact_info="555-1234",
        )
        assert booking.confirmation_number == "ABC"


class TestBotAction:
    def test_action_creation(self):
        action = BotAction(
            action=ActionType.ADD_ITEM,
            parameters={"title": "Hotel"},
            response_text="Added Hotel!",
        )
        assert action.action == ActionType.ADD_ITEM
        assert action.parameters["title"] == "Hotel"


class TestBotResponse:
    def test_single_action_response(self):
        from app.models.llm import BotResponse

        resp = BotResponse(
            actions=[BotAction(action=ActionType.ADD_ITEM, parameters={"title": "Hotel"})],
            response_text="Added!",
        )
        assert len(resp.actions) == 1
        assert resp.suggested_items == []

    def test_multi_action_response(self):
        from app.models.llm import BotResponse

        resp = BotResponse(
            actions=[
                BotAction(action=ActionType.ADD_ITEM, parameters={"title": "Flight"}),
                BotAction(action=ActionType.ADD_ITEM, parameters={"title": "Hotel"}),
            ],
            response_text="Added both!",
        )
        assert len(resp.actions) == 2

    def test_with_suggested_items(self):
        from app.models.llm import BotResponse, SuggestedItem

        resp = BotResponse(
            actions=[BotAction(action=ActionType.QUERY, parameters={})],
            response_text="Here are ideas!",
            suggested_items=[
                SuggestedItem(title="Colosseum", category="activity", notes="Ancient arena"),
            ],
        )
        assert len(resp.suggested_items) == 1
        assert resp.suggested_items[0].title == "Colosseum"


class TestSuggestedItem:
    def test_defaults(self):
        from app.models.llm import SuggestedItem

        item = SuggestedItem(title="Test")
        assert item.category == "other"
        assert item.notes == ""


class TestParseLlmResponse:
    """Test the _parse_llm_response function."""

    def test_single_action_format(self):
        from app.services.llm import _parse_llm_response

        data = {
            "action": "add_item",
            "parameters": {"title": "Hotel"},
            "response_text": "Added!",
        }
        resp = _parse_llm_response(data)
        assert len(resp.actions) == 1
        assert resp.actions[0].action == ActionType.ADD_ITEM

    def test_array_action_format(self):
        from app.services.llm import _parse_llm_response

        data = {
            "actions": [
                {"action": "add_item", "parameters": {"title": "Flight"}},
                {"action": "add_item", "parameters": {"title": "Hotel"}},
            ],
            "response_text": "Added both!",
        }
        resp = _parse_llm_response(data)
        assert len(resp.actions) == 2

    def test_invalid_action_falls_back_to_clarify(self):
        from app.services.llm import _parse_llm_response

        data = {"action": "invalid_action", "response_text": "oops"}
        resp = _parse_llm_response(data)
        assert len(resp.actions) == 1
        assert resp.actions[0].action == ActionType.CLARIFY

    def test_suggested_items_parsed(self):
        from app.services.llm import _parse_llm_response

        data = {
            "action": "query",
            "parameters": {},
            "response_text": "Here are ideas",
            "suggested_items": [
                {"title": "Colosseum", "category": "activity", "notes": "Must see"},
                {"title": "Trevi Fountain", "category": "activity"},
            ],
        }
        resp = _parse_llm_response(data)
        assert len(resp.suggested_items) == 2
        assert resp.suggested_items[0].notes == "Must see"
        assert resp.suggested_items[1].notes == ""

    def test_suggested_items_capped_at_3(self):
        from app.services.llm import _parse_llm_response

        data = {
            "action": "query",
            "parameters": {},
            "response_text": "Ideas",
            "suggested_items": [
                {"title": f"Item {i}", "category": "activity"} for i in range(5)
            ],
        }
        resp = _parse_llm_response(data)
        assert len(resp.suggested_items) == 3

    def test_malformed_suggested_items_skipped(self):
        from app.services.llm import _parse_llm_response

        data = {
            "action": "query",
            "parameters": {},
            "response_text": "Ideas",
            "suggested_items": [
                {"title": "Valid", "category": "activity"},
                {"no_title": "invalid"},
                "not a dict",
            ],
        }
        resp = _parse_llm_response(data)
        assert len(resp.suggested_items) == 1

    def test_empty_actions_array_falls_back(self):
        from app.services.llm import _parse_llm_response

        data = {"actions": [], "response_text": "Nothing"}
        resp = _parse_llm_response(data)
        assert len(resp.actions) == 1
        assert resp.actions[0].action == ActionType.CLARIFY
    def test_stage_values(self):
        assert Stage.BRAINSTORMING == "brainstorming"
        assert Stage.PLANNING == "planning"
        assert Stage.FINALIZED == "finalized"

    def test_category_values(self):
        assert Category.LODGING == "lodging"
        assert Category.TRANSPORT == "transport"

    def test_action_type_values(self):
        assert ActionType.ADD_ITEM == "add_item"
        assert ActionType.GENERATE_ITINERARY == "generate_itinerary"
