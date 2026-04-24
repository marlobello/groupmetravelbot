from __future__ import annotations

import logging
from datetime import UTC, datetime

from azure.cosmos.aio import ContainerProxy
from azure.cosmos.exceptions import CosmosResourceNotFoundError

from app.models.trip import Stage, Trip, TripItem, TripStatus

logger = logging.getLogger(__name__)


async def get_active_trip(container: ContainerProxy, group_id: str) -> Trip | None:
    query = "SELECT * FROM c WHERE c.groupId = @groupId AND c.type = 'trip' AND c.status = 'active'"
    params: list[dict[str, str]] = [{"name": "@groupId", "value": group_id}]
    items = [
        item
        async for item in container.query_items(query, parameters=params, partition_key=group_id)
    ]
    return Trip(**items[0]) if items else None


async def create_trip(container: ContainerProxy, group_id: str, name: str) -> Trip:
    trip = Trip(groupId=group_id, name=name)
    await container.create_item(trip.model_dump(by_alias=True))
    return trip


async def archive_trip(container: ContainerProxy, group_id: str, trip_id: str) -> None:
    item = await container.read_item(trip_id, partition_key=group_id)
    item["status"] = TripStatus.ARCHIVED
    item["updatedAt"] = datetime.now(UTC).isoformat()
    await container.replace_item(trip_id, item, if_match=item.get("_etag"))


async def get_items_by_stage(
    container: ContainerProxy, group_id: str, trip_id: str, stage: Stage
) -> list[TripItem]:
    query = (
        "SELECT * FROM c WHERE c.groupId = @groupId "
        "AND c.tripId = @tripId AND c.stage = @stage AND c.type = 'item'"
    )
    params: list[dict[str, str]] = [
        {"name": "@groupId", "value": group_id},
        {"name": "@tripId", "value": trip_id},
        {"name": "@stage", "value": stage.value},
    ]
    items = [
        item
        async for item in container.query_items(query, parameters=params, partition_key=group_id)
    ]
    return [TripItem(**item) for item in items]


async def get_all_items(container: ContainerProxy, group_id: str, trip_id: str) -> list[TripItem]:
    query = "SELECT * FROM c WHERE c.groupId = @groupId AND c.tripId = @tripId AND c.type = 'item'"
    params: list[dict[str, str]] = [
        {"name": "@groupId", "value": group_id},
        {"name": "@tripId", "value": trip_id},
    ]
    items = [
        item
        async for item in container.query_items(query, parameters=params, partition_key=group_id)
    ]
    return [TripItem(**item) for item in items]


async def add_item(container: ContainerProxy, item: TripItem) -> TripItem:
    await container.create_item(item.model_dump(by_alias=True))
    return item


async def move_item(
    container: ContainerProxy, group_id: str, item_id: str, new_stage: Stage
) -> TripItem:
    item = await container.read_item(item_id, partition_key=group_id)
    item["stage"] = new_stage.value
    item["updatedAt"] = datetime.now(UTC).isoformat()
    result = await container.replace_item(item_id, item, if_match=item.get("_etag"))
    return TripItem(**result)


async def update_item(
    container: ContainerProxy, group_id: str, item_id: str, updates: dict
) -> TripItem:
    item = await container.read_item(item_id, partition_key=group_id)
    for key, value in updates.items():
        if key in item:
            item[key] = value
        elif key in item.get("details", {}):
            item["details"][key] = value
    item["updatedAt"] = datetime.now(UTC).isoformat()
    result = await container.replace_item(item_id, item, if_match=item.get("_etag"))
    return TripItem(**result)


async def delete_item(container: ContainerProxy, group_id: str, item_id: str) -> None:
    await container.delete_item(item_id, partition_key=group_id)


async def check_message_processed(
    container: ContainerProxy, group_id: str, message_id: str
) -> bool:
    """Check if a message has already been processed (idempotency)."""
    try:
        await container.read_item(f"msg-{message_id}", partition_key=group_id)
        return True
    except CosmosResourceNotFoundError:
        return False


async def mark_message_processed(container: ContainerProxy, group_id: str, message_id: str) -> None:
    """Mark a message as processed with a 24-hour TTL."""
    await container.create_item(
        {
            "id": f"msg-{message_id}",
            "groupId": group_id,
            "type": "processed_message",
            "ttl": 86400,  # 24 hours
        }
    )
