from __future__ import annotations

from app.models.trip import BookingDetails, Category, ItemDetails, Stage, Trip, TripItem
from app.services.itinerary import generate_summary


class TestGenerateSummary:
    def test_no_finalized_or_planning_items(self):
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
        assert "No finalized or planned items yet" in result

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
        assert "Confirmed" in result

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
        assert "No finalized or planned items yet" in result

    def test_mixed_stages_includes_planning(self):
        """Planning items should appear in itinerary under 'Planned' section."""
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
            TripItem(
                groupId="g1",
                tripId=trip.id,
                title="Planned Activity",
                addedBy="Carol",
                stage=Stage.PLANNING,
                category=Category.ACTIVITY,
                details={"notes": "Need to buy tickets"},
            ),
        ]
        result = generate_summary(trip, items)
        assert "Finalized Item" in result
        assert "Planned Activity" in result
        assert "Planned (not yet booked)" in result
        assert "Need to buy tickets" in result
        assert "Brainstorm Item" not in result

    def test_planning_only_no_finalized(self):
        """When only planning items exist, they should still show."""
        trip = Trip(groupId="g1", name="Early Trip")
        items = [
            TripItem(
                groupId="g1",
                tripId=trip.id,
                title="Colosseum Tour",
                addedBy="Alice",
                stage=Stage.PLANNING,
                category=Category.ACTIVITY,
                details={"notes": "Want to visit"},
            ),
        ]
        result = generate_summary(trip, items)
        assert "Colosseum Tour" in result
        assert "Planned (not yet booked)" in result
        assert "No finalized" not in result

    def test_address_in_summary(self):
        """Booking address should appear in the summary."""
        trip = Trip(groupId="g1", name="Trip")
        items = [
            TripItem(
                groupId="g1",
                tripId=trip.id,
                title="Hotel Artemide",
                addedBy="Alice",
                stage=Stage.FINALIZED,
                category=Category.LODGING,
                details=ItemDetails(
                    notes="Great location",
                    booking=BookingDetails(
                        confirmation_number="HA-4455",
                        address="Via Nazionale 22, Rome",
                    ),
                ),
            ),
        ]
        result = generate_summary(trip, items)
        assert "HA-4455" in result
        assert "Via Nazionale 22, Rome" in result

    def test_start_date_only(self):
        trip = Trip(groupId="g1", name="Trip")
        items = [
            TripItem(
                groupId="g1",
                tripId=trip.id,
                title="Flight",
                addedBy="Alice",
                stage=Stage.FINALIZED,
                category=Category.TRANSPORT,
                details={"dates": {"start": "2025-06-15"}},
            ),
        ]
        result = generate_summary(trip, items)
        assert "2025-06-15" in result
