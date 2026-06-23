"""Function tools for the Agent Framework — expose storage write operations as tools.

The agent reads trip documents from the system prompt (hybrid approach) but uses
these tools to write changes, create/archive trips.
"""

from __future__ import annotations

import json
import logging
from typing import Annotated
from uuid import uuid4

from agent_framework import tool
from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob.aio import ContainerClient
from pydantic import Field

logger = logging.getLogger(__name__)


VALID_FILES = {"trip.md", "brainstorming.md", "planning.md", "itinerary.md"}


class TripTools:
    """Stateful tool class that holds the blob container and group/trip context."""

    def __init__(
        self,
        container: ContainerClient,
        group_id: str,
        trip_id: str | None = None,
    ):
        self._container = container
        self._group_id = group_id
        self._trip_id = trip_id

    @tool(
        description="Update a trip document with new content. "
        "Use this when the group discusses changes to their trip plans.",
    )
    async def write_trip_file(
        self,
        filename: Annotated[
            str,
            Field(
                description="The file to update: trip.md, brainstorming.md, "
                "planning.md, or itinerary.md"
            ),
        ],
        content: Annotated[
            str,
            Field(
                description="The complete updated markdown content for the file. "
                "Must include ALL existing content — never omit unchanged sections."
            ),
        ],
    ) -> str:
        """Write a trip document, replacing its full content."""
        if filename not in VALID_FILES:
            valid = ", ".join(sorted(VALID_FILES))
            return f"Error: '{filename}' is not a valid file. Must be one of: {valid}"
        if not self._trip_id:
            return "Error: No active trip. Create a trip first."
        if len(content.encode("utf-8")) > 500 * 1024:
            return "Error: Content too large (max 500KB)."

        blob = self._container.get_blob_client(f"trips/{self._group_id}/{self._trip_id}/{filename}")
        await blob.upload_blob(content.encode(), overwrite=True)
        logger.info(
            "Agent wrote %s for group %s trip %s",
            filename,
            self._group_id,
            self._trip_id,
        )
        return f"Successfully updated {filename}."

    @tool(
        description="Create a new trip for the group. "
        "Use when someone wants to start planning a new trip.",
    )
    async def create_trip(
        self,
        trip_name: Annotated[
            str,
            Field(description="The name of the new trip, e.g. 'Hawaii 2026'"),
        ],
    ) -> str:
        """Create a new trip with template files and set it as active."""
        trip_id = str(uuid4())
        prefix = f"trips/{self._group_id}/{trip_id}"

        templates = {
            "trip.md": (
                f"# {trip_name}\n\n**Status:** Active\n\n"
                "## Details\n\n_Add trip details here — dates, "
                "destination, participants, budget._\n"
            ),
            "brainstorming.md": (
                f"# {trip_name} — Brainstorming\n\n"
                "_Ideas, wish-list items, and suggestions go here._\n"
            ),
            "planning.md": (
                f"# {trip_name} — Planning\n\n_Agreed-upon plans that aren't yet booked go here._\n"
            ),
            "itinerary.md": (
                f"# {trip_name} — Itinerary\n\n"
                "_Confirmed plans with dates, times, and "
                "reservation details go here._\n"
            ),
        }

        for fname, fcontent in templates.items():
            blob = self._container.get_blob_client(f"{prefix}/{fname}")
            await blob.upload_blob(fcontent.encode(), overwrite=True)

        pointer = {"trip_id": trip_id, "trip_name": trip_name}
        ptr_blob = self._container.get_blob_client(f"trips/{self._group_id}/active_trip.json")
        await ptr_blob.upload_blob(json.dumps(pointer).encode(), overwrite=True)

        self._trip_id = trip_id
        logger.info(
            "Agent created trip '%s' (id=%s) for group %s",
            trip_name,
            trip_id,
            self._group_id,
        )
        return f"Created new trip '{trip_name}'. The trip files are ready for planning!"

    @tool(
        description="Archive the current trip. "
        "Use when the group is done with their trip and wants to start fresh.",
    )
    async def archive_trip(self) -> str:
        """Archive the active trip by removing the pointer (files remain for history)."""
        blob = self._container.get_blob_client(f"trips/{self._group_id}/active_trip.json")
        try:
            await blob.delete_blob()
        except ResourceNotFoundError:
            return "No active trip to archive."

        self._trip_id = None
        logger.info("Agent archived trip for group %s", self._group_id)
        return "Trip archived! The group can start a new trip whenever they're ready."
