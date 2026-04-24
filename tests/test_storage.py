from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.models.trip import Stage, Trip, TripItem, TripStatus
from app.services import storage


@pytest.mark.asyncio
async def test_get_active_trip_found():
    trip_data = Trip(groupId="g1", name="Test Trip").model_dump(by_alias=True)
    container = AsyncMock()

    async def mock_query(*args, **kwargs):
        yield trip_data

    container.query_items = mock_query

    result = await storage.get_active_trip(container, "g1")
    assert result is not None
    assert result.name == "Test Trip"
    assert result.group_id == "g1"


@pytest.mark.asyncio
async def test_get_active_trip_not_found():
    container = AsyncMock()

    async def mock_query(*args, **kwargs):
        return
        yield  # noqa: E501 — make it an async generator that yields nothing

    container.query_items = mock_query

    result = await storage.get_active_trip(container, "g1")
    assert result is None


@pytest.mark.asyncio
async def test_create_trip():
    container = AsyncMock()
    container.create_item = AsyncMock()

    trip = await storage.create_trip(container, "g1", "Hawaii Trip")
    assert trip.name == "Hawaii Trip"
    assert trip.group_id == "g1"
    assert trip.status == TripStatus.ACTIVE
    container.create_item.assert_called_once()


@pytest.mark.asyncio
async def test_add_item():
    container = AsyncMock()
    container.create_item = AsyncMock()

    item = TripItem(
        groupId="g1",
        tripId="t1",
        title="Beach Hotel",
        addedBy="Alice",
    )
    result = await storage.add_item(container, item)
    assert result.title == "Beach Hotel"
    container.create_item.assert_called_once()


@pytest.mark.asyncio
async def test_move_item():
    existing = TripItem(
        groupId="g1", tripId="t1", title="Hotel", addedBy="Alice", stage=Stage.BRAINSTORMING
    ).model_dump(by_alias=True)

    container = AsyncMock()
    container.read_item = AsyncMock(return_value=existing)
    updated = {**existing, "stage": "planning"}
    container.replace_item = AsyncMock(return_value=updated)

    result = await storage.move_item(container, "g1", existing["id"], Stage.PLANNING)
    assert result.stage == Stage.PLANNING
    container.replace_item.assert_called_once()


@pytest.mark.asyncio
async def test_check_message_processed_true():
    container = AsyncMock()
    container.read_item = AsyncMock(return_value={"id": "msg-123"})

    result = await storage.check_message_processed(container, "g1", "123")
    assert result is True


@pytest.mark.asyncio
async def test_check_message_processed_false():
    from azure.cosmos.exceptions import CosmosResourceNotFoundError

    container = AsyncMock()
    container.read_item = AsyncMock(
        side_effect=CosmosResourceNotFoundError(status_code=404, message="Not found")
    )

    result = await storage.check_message_processed(container, "g1", "123")
    assert result is False


@pytest.mark.asyncio
async def test_delete_item():
    container = AsyncMock()
    container.delete_item = AsyncMock()

    await storage.delete_item(container, "g1", "item-1")
    container.delete_item.assert_called_once_with("item-1", partition_key="g1")


@pytest.mark.asyncio
async def test_get_all_items():
    item_data = TripItem(groupId="g1", tripId="t1", title="Hotel", addedBy="Alice").model_dump(
        by_alias=True
    )

    container = AsyncMock()

    async def mock_query(*args, **kwargs):
        yield item_data

    container.query_items = mock_query

    result = await storage.get_all_items(container, "g1", "t1")
    assert len(result) == 1
    assert result[0].title == "Hotel"
