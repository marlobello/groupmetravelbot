"""Tests for the agent framework function tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.tools import TripTools


@pytest.fixture
def mock_container():
    container = MagicMock()
    # get_blob_client is sync, returns a blob client with async methods
    mock_blob = MagicMock()
    mock_blob.upload_blob = AsyncMock()
    mock_blob.delete_blob = AsyncMock()
    container.get_blob_client = MagicMock(return_value=mock_blob)
    return container


@pytest.fixture
def trip_tools(mock_container):
    return TripTools(container=mock_container, group_id="g1", trip_id="t1")


class TestWriteTripFile:
    """Test write_trip_file tool."""

    @pytest.mark.asyncio
    async def test_writes_valid_file(self, trip_tools, mock_container):
        """Successfully writes a valid trip file."""
        result = await trip_tools.write_trip_file(
            filename="brainstorming.md",
            content="# Brainstorming\n- Visit Colosseum",
        )

        assert "brainstorming.md" in result
        mock_container.get_blob_client.assert_called_with("trips/g1/t1/brainstorming.md")

    @pytest.mark.asyncio
    async def test_rejects_invalid_filename(self, trip_tools):
        """Rejects filenames not in the whitelist."""
        result = await trip_tools.write_trip_file(
            filename="secrets.md",
            content="shouldn't work",
        )

        assert "not a valid file" in result or "Invalid" in result

    @pytest.mark.asyncio
    async def test_rejects_when_no_trip(self):
        """Rejects writes when there's no active trip."""
        container = MagicMock()
        tools = TripTools(container=container, group_id="g1", trip_id=None)
        result = await tools.write_trip_file(
            filename="trip.md",
            content="content",
        )

        assert "No active trip" in result

    @pytest.mark.asyncio
    async def test_all_valid_filenames(self, trip_tools, mock_container):
        """All four valid filenames are accepted."""
        for filename in ["trip.md", "brainstorming.md", "planning.md", "itinerary.md"]:
            result = await trip_tools.write_trip_file(filename=filename, content="# Test")
            assert "updated" in result.lower()


class TestCreateTrip:
    """Test create_trip tool."""

    @pytest.mark.asyncio
    async def test_creates_trip(self, mock_container):
        """Creates a new trip and updates trip_id."""
        tools = TripTools(container=mock_container, group_id="g1", trip_id=None)

        result = await tools.create_trip(trip_name="Rome 2025")

        assert "Rome 2025" in result
        assert tools._trip_id is not None
        # Should have created 5 blobs: 4 templates + active_trip.json pointer
        assert mock_container.get_blob_client.call_count == 5


class TestArchiveTrip:
    """Test archive_trip tool."""

    @pytest.mark.asyncio
    async def test_archives_trip(self, trip_tools, mock_container):
        """Archives the active trip."""
        result = await trip_tools.archive_trip()

        assert "archived" in result.lower() or "Archived" in result
        mock_container.get_blob_client.assert_called_with("trips/g1/active_trip.json")

    @pytest.mark.asyncio
    async def test_archive_no_active_trip(self):
        """Returns error when no active trip exists."""
        from azure.core.exceptions import ResourceNotFoundError

        container = MagicMock()
        mock_blob = MagicMock()
        mock_blob.delete_blob = AsyncMock(side_effect=ResourceNotFoundError("not found"))
        container.get_blob_client = MagicMock(return_value=mock_blob)

        tools = TripTools(container=container, group_id="g1", trip_id=None)
        result = await tools.archive_trip()

        assert "No active trip" in result
