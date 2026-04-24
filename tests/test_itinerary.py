from __future__ import annotations

from app.models.trip import Category, Stage, Trip, TripItem
from app.services.itinerary import generate_summary


class TestGenerateSummary:
    def test_no_finalized_items(self):
        trip = Trip(groupId="g1", name="Beach Trip")
        items = [
            TripItem(
                groupId="g1",
                tripId=trip.id,
                title="Hotel",
                addedBy="Alice",
                stage=Stage.BRAINSTORMING,
            ),
        ]
        result = generate_summary(trip, items)
        assert "Beach Trip" in result
        assert "No finalized items yet" in result

    def test_with_finalized_items(self):
        trip = Trip(groupId="g1", name="Hawaii Trip")
        items = [
            TripItem(
                groupId="g1",
                tripId=trip.id,
                title="Hilton Waikiki",
                addedBy="Alice",
                stage=Stage.FINALIZED,
                category=Category.LODGING,
                details={"notes": "Ocean view room"},
            ),
            TripItem(
                groupId="g1",
                tripId=trip.id,
                title="Flight LAX-HNL",
                addedBy="Bob",
                stage=Stage.FINALIZED,
                category=Category.TRANSPORT,
                details={
                    "notes": "United Airlines",
                    "booking": {"confirmation_number": "UA123"},
                },
            ),
        ]
        result = generate_summary(trip, items)
        assert "Hawaii Trip" in result
        assert "Itinerary Summary" in result
        assert "Hilton Waikiki" in result
        assert "Ocean view room" in result
        assert "Flight LAX-HNL" in result
        assert "UA123" in result

    def test_with_dates(self):
        trip = Trip(groupId="g1", name="Trip")
        items = [
            TripItem(
                groupId="g1",
                tripId=trip.id,
                title="Resort Stay",
                addedBy="Alice",
                stage=Stage.FINALIZED,
                category=Category.LODGING,
                details={"dates": {"start": "2025-01-01", "end": "2025-01-07"}},
            ),
        ]
        result = generate_summary(trip, items)
        assert "2025-01-01" in result
        assert "2025-01-07" in result

    def test_empty_items(self):
        trip = Trip(groupId="g1", name="Empty Trip")
        result = generate_summary(trip, [])
        assert "No finalized items yet" in result

    def test_mixed_stages(self):
        trip = Trip(groupId="g1", name="Mixed Trip")
        items = [
            TripItem(
                groupId="g1",
                tripId=trip.id,
                title="Brainstorm Item",
                addedBy="Alice",
                stage=Stage.BRAINSTORMING,
            ),
            TripItem(
                groupId="g1",
                tripId=trip.id,
                title="Finalized Item",
                addedBy="Bob",
                stage=Stage.FINALIZED,
                category=Category.ACTIVITY,
            ),
        ]
        result = generate_summary(trip, items)
        assert "Finalized Item" in result
        assert "Brainstorm Item" not in result
