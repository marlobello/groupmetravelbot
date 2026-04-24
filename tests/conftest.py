from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.models.trip import Category, Stage, Trip, TripItem


@pytest.fixture
def sample_trip():
    return Trip(groupId="group-123", name="Test Trip")


@pytest.fixture
def sample_items(sample_trip):
    return [
        TripItem(
            groupId="group-123",
            tripId=sample_trip.id,
            stage=Stage.BRAINSTORMING,
            category=Category.LODGING,
            title="Beach Hotel",
            details={"notes": "Looks nice"},
            addedBy="Alice",
        ),
        TripItem(
            groupId="group-123",
            tripId=sample_trip.id,
            stage=Stage.FINALIZED,
            category=Category.TRANSPORT,
            title="Flight to Cancun",
            details={
                "notes": "Direct flight",
                "booking": {"confirmation_number": "ABC123"},
            },
            addedBy="Bob",
        ),
    ]


@pytest.fixture
def mock_cosmos_container():
    return AsyncMock()
