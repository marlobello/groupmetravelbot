"""Tests for the BlobHistoryProvider."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from azure.core.exceptions import ResourceNotFoundError

from app.services.history_provider import BlobHistoryProvider


@pytest.fixture
def mock_container():
    container = MagicMock()
    mock_blob = MagicMock()
    mock_blob.upload_blob = AsyncMock()
    mock_blob.download_blob = AsyncMock()
    container.get_blob_client = MagicMock(return_value=mock_blob)
    return container


@pytest.fixture
def provider(mock_container):
    return BlobHistoryProvider(container=mock_container, group_id="g1")


class TestGetMessages:
    """Test loading messages from blob storage."""

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_blob(self, mock_container):
        """Returns empty list when history blob doesn't exist."""
        mock_blob = MagicMock()
        mock_blob.download_blob = AsyncMock(side_effect=ResourceNotFoundError("not found"))
        mock_container.get_blob_client = MagicMock(return_value=mock_blob)
        provider = BlobHistoryProvider(container=mock_container, group_id="g1")

        messages = await provider.get_messages("g1")

        assert messages == []

    @pytest.mark.asyncio
    async def test_loads_messages_from_blob(self, provider, mock_container):
        """Deserialises messages from blob JSON."""
        from agent_framework import Message

        stored = [
            Message("user", ["Hello"], author_name="Alice").to_dict(),
            Message("assistant", ["Hi there!"]).to_dict(),
        ]
        blob_content = json.dumps(stored).encode()

        mock_data = AsyncMock()
        mock_data.readall = AsyncMock(return_value=blob_content)
        mock_blob = MagicMock()
        mock_blob.download_blob = AsyncMock(return_value=mock_data)
        mock_container.get_blob_client = MagicMock(return_value=mock_blob)

        messages = await provider.get_messages("g1")

        assert len(messages) == 2
        assert messages[0].text == "Hello"
        assert messages[1].text == "Hi there!"

    @pytest.mark.asyncio
    async def test_trims_to_max_messages(self, provider, mock_container):
        """Trims history to MAX_HISTORY_MESSAGES."""
        from agent_framework import Message

        from app.services.history_provider import MAX_HISTORY_MESSAGES

        stored = [Message("user", [f"msg {i}"]).to_dict() for i in range(MAX_HISTORY_MESSAGES + 20)]
        blob_content = json.dumps(stored).encode()

        mock_data = AsyncMock()
        mock_data.readall = AsyncMock(return_value=blob_content)
        mock_blob = MagicMock()
        mock_blob.download_blob = AsyncMock(return_value=mock_data)
        mock_container.get_blob_client = MagicMock(return_value=mock_blob)

        messages = await provider.get_messages("g1")

        assert len(messages) == MAX_HISTORY_MESSAGES


class TestSaveMessages:
    """Test saving messages to blob storage."""

    @pytest.mark.asyncio
    async def test_saves_messages_to_blob(self, mock_container):
        """Serialises and uploads messages."""
        from agent_framework import Message

        # Empty existing history (ResourceNotFoundError on load)
        mock_blob = MagicMock()
        mock_blob.download_blob = AsyncMock(side_effect=ResourceNotFoundError("not found"))
        mock_blob.upload_blob = AsyncMock()
        mock_container.get_blob_client = MagicMock(return_value=mock_blob)

        provider = BlobHistoryProvider(container=mock_container, group_id="g1")
        new_msgs = [
            Message("user", ["Plan a trip"], author_name="Alice"),
            Message("assistant", ["Let's do it!"]),
        ]

        await provider.save_messages("g1", new_msgs)

        mock_blob.upload_blob.assert_called_once()
        saved_data = mock_blob.upload_blob.call_args[0][0]
        parsed = json.loads(saved_data)
        assert len(parsed) == 2
        assert parsed[0]["role"] == "user"

    @pytest.mark.asyncio
    async def test_skips_save_when_empty(self, provider, mock_container):
        """Doesn't write blob when no messages to save."""
        mock_blob = MagicMock()
        mock_blob.upload_blob = AsyncMock()
        mock_container.get_blob_client = MagicMock(return_value=mock_blob)

        await provider.save_messages("g1", [])

        mock_blob.upload_blob.assert_not_called()

    @pytest.mark.asyncio
    async def test_blob_path_uses_group_id(self, mock_container):
        """Blob path is trips/{group_id}/session_history.json."""
        provider = BlobHistoryProvider(container=mock_container, group_id="test-group")
        assert provider._blob_path == "trips/test-group/session_history.json"
