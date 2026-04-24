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


class TestEnums:
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
