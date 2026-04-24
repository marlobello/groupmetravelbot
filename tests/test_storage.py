from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from azure.core.exceptions import ResourceNotFoundError

from app.services import storage

# ── get_active_trip ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_active_trip_found():
    pointer = {"trip_id": "abc-123", "trip_name": "Rome 2025"}
    blob_client = AsyncMock()
    download = AsyncMock()
    download.readall = AsyncMock(return_value=json.dumps(pointer).encode())
    blob_client.download_blob = AsyncMock(return_value=download)

    container = AsyncMock()
    container.get_blob_client = MagicMock(return_value=blob_client)

    result = await storage.get_active_trip(container, "g1")
    assert result == pointer
    container.get_blob_client.assert_called_once_with("trips/g1/active_trip.json")


@pytest.mark.asyncio
async def test_get_active_trip_not_found():
    blob_client = AsyncMock()
    blob_client.download_blob = AsyncMock(side_effect=ResourceNotFoundError("Not found"))

    container = AsyncMock()
    container.get_blob_client = MagicMock(return_value=blob_client)

    result = await storage.get_active_trip(container, "g1")
    assert result is None


# ── create_trip ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_trip():
    blob_clients = {}

    def mock_get_blob_client(path):
        client = AsyncMock()
        blob_clients[path] = client
        return client

    container = AsyncMock()
    container.get_blob_client = MagicMock(side_effect=mock_get_blob_client)

    result = await storage.create_trip(container, "g1", "Rome 2025")

    assert result["trip_name"] == "Rome 2025"
    assert "trip_id" in result

    # Should create 4 template files + 1 pointer
    assert len(blob_clients) == 5
    paths = list(blob_clients.keys())
    assert any("trip.md" in p for p in paths)
    assert any("brainstorming.md" in p for p in paths)
    assert any("planning.md" in p for p in paths)
    assert any("itinerary.md" in p for p in paths)
    assert any("active_trip.json" in p for p in paths)


# ── archive_trip ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_archive_trip():
    blob_client = AsyncMock()
    container = AsyncMock()
    container.get_blob_client = MagicMock(return_value=blob_client)

    await storage.archive_trip(container, "g1")
    blob_client.delete_blob.assert_called_once()


@pytest.mark.asyncio
async def test_archive_trip_no_active():
    blob_client = AsyncMock()
    blob_client.delete_blob = AsyncMock(side_effect=ResourceNotFoundError("Not found"))
    container = AsyncMock()
    container.get_blob_client = MagicMock(return_value=blob_client)

    # Should not raise
    await storage.archive_trip(container, "g1")


# ── read_trip_files ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_read_trip_files():
    file_contents = {
        "trip.md": b"# My Trip",
        "brainstorming.md": b"# Ideas",
        "planning.md": b"# Plans",
        "itinerary.md": b"# Itinerary",
    }

    def mock_get_blob(path):
        fname = path.split("/")[-1]
        client = AsyncMock()
        download = AsyncMock()
        download.readall = AsyncMock(return_value=file_contents.get(fname, b""))
        client.download_blob = AsyncMock(return_value=download)
        return client

    container = AsyncMock()
    container.get_blob_client = MagicMock(side_effect=mock_get_blob)

    result = await storage.read_trip_files(container, "g1", "t1")
    assert result["trip.md"] == "# My Trip"
    assert result["brainstorming.md"] == "# Ideas"
    assert len(result) == 4


@pytest.mark.asyncio
async def test_read_trip_files_missing_file():
    """Missing files should return empty string, not raise."""
    def mock_get_blob(path):
        client = AsyncMock()
        client.download_blob = AsyncMock(side_effect=ResourceNotFoundError("Not found"))
        return client

    container = AsyncMock()
    container.get_blob_client = MagicMock(side_effect=mock_get_blob)

    result = await storage.read_trip_files(container, "g1", "t1")
    assert all(v == "" for v in result.values())


# ── write_trip_file ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_write_trip_file():
    blob_client = AsyncMock()
    container = AsyncMock()
    container.get_blob_client = MagicMock(return_value=blob_client)

    await storage.write_trip_file(container, "g1", "t1", "brainstorming.md", "# Updated")
    blob_client.upload_blob.assert_called_once()


@pytest.mark.asyncio
async def test_write_trip_file_invalid_name():
    blob_client = AsyncMock()
    container = AsyncMock()
    container.get_blob_client = MagicMock(return_value=blob_client)

    await storage.write_trip_file(container, "g1", "t1", "evil.md", "content")
    blob_client.upload_blob.assert_not_called()


# ── idempotency ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_check_message_processed_true():
    blob_client = AsyncMock()
    blob_client.get_blob_properties = AsyncMock(return_value={})
    container = AsyncMock()
    container.get_blob_client = MagicMock(return_value=blob_client)

    result = await storage.check_message_processed(container, "g1", "123")
    assert result is True


@pytest.mark.asyncio
async def test_check_message_processed_false():
    blob_client = AsyncMock()
    blob_client.get_blob_properties = AsyncMock(side_effect=ResourceNotFoundError("Not found"))
    container = AsyncMock()
    container.get_blob_client = MagicMock(return_value=blob_client)

    result = await storage.check_message_processed(container, "g1", "123")
    assert result is False


@pytest.mark.asyncio
async def test_mark_message_processed():
    blob_client = AsyncMock()
    container = AsyncMock()
    container.get_blob_client = MagicMock(return_value=blob_client)

    await storage.mark_message_processed(container, "g1", "123")
    blob_client.upload_blob.assert_called_once()
    container.get_blob_client.assert_called_with("processed/g1/msg-123")


# ── group_lock ────────────────────────────────────────────────────────

def test_get_group_lock_returns_same_lock():
    storage._group_locks.clear()
    lock1 = storage._get_group_lock("g1")
    lock2 = storage._get_group_lock("g1")
    assert lock1 is lock2

    lock3 = storage._get_group_lock("g2")
    assert lock3 is not lock1
