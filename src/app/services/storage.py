"""Blob Storage layer for markdown trip documents.

Each group's trip data lives under:
    trips/{group_id}/active_trip.json          — pointer to current trip
    trips/{group_id}/{trip_id}/trip.md          — high-level trip details
    trips/{group_id}/{trip_id}/brainstorming.md — ideas and wish-list
    trips/{group_id}/{trip_id}/planning.md      — agreed plans (not yet booked)
    trips/{group_id}/{trip_id}/itinerary.md     — confirmed, finalized plans
"""

from __future__ import annotations

import asyncio
import json
import logging
from uuid import uuid4

from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob.aio import ContainerClient

logger = logging.getLogger(__name__)

TRIP_FILES = ("trip.md", "brainstorming.md", "planning.md", "itinerary.md")

# Per-group locks to serialise writes within the same replica.
_group_locks: dict[str, asyncio.Lock] = {}


def _get_group_lock(group_id: str) -> asyncio.Lock:
    if group_id not in _group_locks:
        _group_locks[group_id] = asyncio.Lock()
    return _group_locks[group_id]


# ── Trip lifecycle ─────────────────────────────────────────────────────

async def get_active_trip(
    container: ContainerClient, group_id: str
) -> dict | None:
    """Return {trip_id, trip_name} for the group's active trip, or None."""
    blob = container.get_blob_client(f"trips/{group_id}/active_trip.json")
    try:
        data = await blob.download_blob()
        content = await data.readall()
        return json.loads(content)
    except ResourceNotFoundError:
        return None


async def create_trip(
    container: ContainerClient, group_id: str, name: str
) -> dict:
    """Create a new trip folder with template files and set it as active."""
    trip_id = str(uuid4())
    prefix = f"trips/{group_id}/{trip_id}"

    templates = {
        "trip.md": (
            f"# {name}\n\n**Status:** Active\n\n"
            "## Details\n\n_Add trip details here — dates, "
            "destination, participants, budget._\n"
        ),
        "brainstorming.md": (
            f"# {name} — Brainstorming\n\n"
            "_Ideas, wish-list items, and suggestions go here._\n"
        ),
        "planning.md": (
            f"# {name} — Planning\n\n"
            "_Agreed-upon plans that aren't yet booked go here._\n"
        ),
        "itinerary.md": (
            f"# {name} — Itinerary\n\n"
            "_Confirmed plans with dates, times, and reservation details go here._\n"
        ),
    }

    for filename, content in templates.items():
        blob = container.get_blob_client(f"{prefix}/{filename}")
        await blob.upload_blob(content.encode(), overwrite=True)

    pointer = {"trip_id": trip_id, "trip_name": name}
    ptr_blob = container.get_blob_client(f"trips/{group_id}/active_trip.json")
    await ptr_blob.upload_blob(json.dumps(pointer).encode(), overwrite=True)

    return pointer


async def archive_trip(
    container: ContainerClient, group_id: str
) -> None:
    """Remove the active trip pointer (files remain for history)."""
    blob = container.get_blob_client(f"trips/{group_id}/active_trip.json")
    try:
        await blob.delete_blob()
    except ResourceNotFoundError:
        pass


# ── Read / write trip documents ───────────────────────────────────────

async def read_trip_files(
    container: ContainerClient, group_id: str, trip_id: str
) -> dict[str, str]:
    """Read all 4 markdown files for a trip. Returns {filename: content}."""
    prefix = f"trips/{group_id}/{trip_id}"
    result: dict[str, str] = {}
    for filename in TRIP_FILES:
        blob = container.get_blob_client(f"{prefix}/{filename}")
        try:
            data = await blob.download_blob()
            result[filename] = (await data.readall()).decode()
        except ResourceNotFoundError:
            result[filename] = ""
    return result


async def write_trip_file(
    container: ContainerClient,
    group_id: str,
    trip_id: str,
    filename: str,
    content: str,
) -> None:
    """Write a single markdown file, overwriting previous content."""
    if filename not in TRIP_FILES:
        logger.warning("Attempted to write unknown file: %s", filename)
        return
    blob = container.get_blob_client(f"trips/{group_id}/{trip_id}/{filename}")
    await blob.upload_blob(content.encode(), overwrite=True)


# ── Idempotency ───────────────────────────────────────────────────────

async def check_message_processed(
    container: ContainerClient, group_id: str, message_id: str
) -> bool:
    blob = container.get_blob_client(f"processed/{group_id}/msg-{message_id}")
    try:
        await blob.get_blob_properties()
        return True
    except ResourceNotFoundError:
        return False


async def mark_message_processed(
    container: ContainerClient, group_id: str, message_id: str
) -> None:
    blob = container.get_blob_client(f"processed/{group_id}/msg-{message_id}")
    await blob.upload_blob(b"1", overwrite=True)

