from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.groupme import GroupMeMessage
from app.services.message_handler import handle_message


def _make_message(**overrides) -> GroupMeMessage:
    defaults = {
        "id": "msg-1",
        "group_id": "g1",
        "sender_id": "u1",
        "sender_type": "user",
        "name": "Alice",
        "text": "@sensei what can we do in Rome?",
        "created_at": 1700000000,
    }
    defaults.update(overrides)
    return GroupMeMessage(**defaults)


def _make_settings():
    s = MagicMock()
    s.bot_trigger_keyword = "@sensei"
    s.groupme_bot_id = "bot-123"
    return s


def _make_storage_mock(*, claimed: bool = True, active=None, trip_files=None):
    """Build a patched-storage mock with a working async group lock."""
    mock_storage = MagicMock()
    mock_storage.claim_message_processed = AsyncMock(return_value=claimed)
    mock_storage.get_active_trip = AsyncMock(return_value=active)
    mock_storage.read_trip_files = AsyncMock(
        return_value=trip_files
        or {
            "trip.md": "",
            "brainstorming.md": "",
            "planning.md": "",
            "itinerary.md": "",
        }
    )

    lock = AsyncMock()
    lock.__aenter__ = AsyncMock(return_value=None)
    lock.__aexit__ = AsyncMock(return_value=False)
    mock_storage._get_group_lock = MagicMock(return_value=lock)
    return mock_storage


# ── Basic flow ────────────────────────────────────────────────────────


@pytest.mark.asyncio
@patch("app.services.message_handler.groupme")
@patch("app.services.message_handler.agent_service")
@patch("app.services.message_handler.storage")
async def test_basic_query_flow(mock_storage_mod, mock_agent, mock_groupme):
    """Agent returns a message — it gets sent to the group."""
    mock_storage = _make_storage_mock(active={"trip_id": "t1", "trip_name": "Rome 2025"})
    mock_storage_mod.claim_message_processed = mock_storage.claim_message_processed
    mock_storage_mod.get_active_trip = mock_storage.get_active_trip
    mock_storage_mod.read_trip_files = mock_storage.read_trip_files
    mock_storage_mod._get_group_lock = mock_storage._get_group_lock

    mock_agent.get_agent_response = AsyncMock(return_value={"message": "Rome has tons to see! 🏛️"})
    mock_groupme.send_message = AsyncMock()

    await handle_message(_make_message(), AsyncMock(), AsyncMock(), _make_settings())

    mock_groupme.send_message.assert_called_once_with("bot-123", "Rome has tons to see! 🏛️")
    # The agent received the active trip's id and files
    call = mock_agent.get_agent_response.call_args.kwargs
    assert call["trip_id"] == "t1"
    assert call["group_id"] == "g1"
    assert call["user_name"] == "Alice"


# ── Idempotency ───────────────────────────────────────────────────────


@pytest.mark.asyncio
@patch("app.services.message_handler.groupme")
@patch("app.services.message_handler.agent_service")
@patch("app.services.message_handler.storage")
async def test_duplicate_message_skipped(mock_storage_mod, mock_agent, mock_groupme):
    """A message that fails to claim (already processed) is skipped entirely."""
    mock_storage = _make_storage_mock(claimed=False)
    mock_storage_mod.claim_message_processed = mock_storage.claim_message_processed
    mock_storage_mod._get_group_lock = mock_storage._get_group_lock
    mock_agent.get_agent_response = AsyncMock()
    mock_groupme.send_message = AsyncMock()

    await handle_message(_make_message(), AsyncMock(), AsyncMock(), _make_settings())

    mock_agent.get_agent_response.assert_not_called()
    mock_groupme.send_message.assert_not_called()


@pytest.mark.asyncio
@patch("app.services.message_handler.groupme")
@patch("app.services.message_handler.agent_service")
@patch("app.services.message_handler.storage")
async def test_claim_happens_before_processing(mock_storage_mod, mock_agent, mock_groupme):
    """The idempotency claim is the first storage call (inside the lock)."""
    mock_storage = _make_storage_mock(active=None)
    mock_storage_mod.claim_message_processed = mock_storage.claim_message_processed
    mock_storage_mod.get_active_trip = mock_storage.get_active_trip
    mock_storage_mod.read_trip_files = mock_storage.read_trip_files
    mock_storage_mod._get_group_lock = mock_storage._get_group_lock
    mock_agent.get_agent_response = AsyncMock(return_value={"message": "Hi!"})
    mock_groupme.send_message = AsyncMock()

    await handle_message(_make_message(), AsyncMock(), AsyncMock(), _make_settings())

    mock_storage.claim_message_processed.assert_awaited_once()
    args = mock_storage.claim_message_processed.call_args[0]
    assert args[1] == "g1" and args[2] == "msg-1"


# ── No active trip ────────────────────────────────────────────────────


@pytest.mark.asyncio
@patch("app.services.message_handler.groupme")
@patch("app.services.message_handler.agent_service")
@patch("app.services.message_handler.storage")
async def test_no_trip_skips_file_read(mock_storage_mod, mock_agent, mock_groupme):
    """With no active trip, trip files are not read and agent gets trip_files=None."""
    mock_storage = _make_storage_mock(active=None)
    mock_storage_mod.claim_message_processed = mock_storage.claim_message_processed
    mock_storage_mod.get_active_trip = mock_storage.get_active_trip
    mock_storage_mod.read_trip_files = mock_storage.read_trip_files
    mock_storage_mod._get_group_lock = mock_storage._get_group_lock
    mock_agent.get_agent_response = AsyncMock(
        return_value={"message": "Hey! Want to start a trip? 🌍"}
    )
    mock_groupme.send_message = AsyncMock()

    await handle_message(_make_message(), AsyncMock(), AsyncMock(), _make_settings())

    mock_storage.read_trip_files.assert_not_called()
    assert mock_agent.get_agent_response.call_args.kwargs["trip_files"] is None
    assert mock_agent.get_agent_response.call_args.kwargs["trip_id"] is None
    mock_groupme.send_message.assert_called_once()


# ── Error handling ────────────────────────────────────────────────────


@pytest.mark.asyncio
@patch("app.services.message_handler.groupme")
@patch("app.services.message_handler.agent_service")
@patch("app.services.message_handler.storage")
async def test_error_sends_apology(mock_storage_mod, mock_agent, mock_groupme):
    """An unexpected error sends a generic apology to the group."""
    mock_storage = _make_storage_mock()
    mock_storage_mod.claim_message_processed = mock_storage.claim_message_processed
    mock_storage_mod._get_group_lock = mock_storage._get_group_lock
    mock_storage_mod.get_active_trip = AsyncMock(side_effect=Exception("boom"))
    mock_groupme.send_message = AsyncMock()

    await handle_message(_make_message(), AsyncMock(), AsyncMock(), _make_settings())

    mock_groupme.send_message.assert_called_once()
    assert "something went wrong" in mock_groupme.send_message.call_args[0][1].lower()


# ── Attachment processing ─────────────────────────────────────────────


@pytest.mark.asyncio
@patch("app.services.message_handler.attachment_processor")
@patch("app.services.message_handler.groupme")
@patch("app.services.message_handler.agent_service")
@patch("app.services.message_handler.storage")
async def test_attachment_text_appended_to_agent_message(
    mock_storage_mod, mock_agent, mock_groupme, mock_attachment
):
    """Attachment text is extracted and appended to the user message sent to the agent."""
    mock_storage = _make_storage_mock(active={"trip_id": "t1", "trip_name": "Rome 2025"})
    mock_storage_mod.claim_message_processed = mock_storage.claim_message_processed
    mock_storage_mod.get_active_trip = mock_storage.get_active_trip
    mock_storage_mod.read_trip_files = mock_storage.read_trip_files
    mock_storage_mod._get_group_lock = mock_storage._get_group_lock

    mock_attachment.process_attachments = AsyncMock(
        return_value="### Attached: flight.pdf\nFlight AA123 DFW→NRT Jan 15"
    )
    mock_agent.get_agent_response = AsyncMock(return_value={"message": "Got it! Flight AA123."})
    mock_groupme.send_message = AsyncMock()

    msg = _make_message(
        text="@sensei add this to the itinerary",
        attachments=[
            {"type": "file", "url": "https://i.groupme.com/flight.pdf", "file_name": "flight.pdf"}
        ],
    )
    await handle_message(msg, AsyncMock(), AsyncMock(), _make_settings())

    user_message = mock_agent.get_agent_response.call_args.kwargs["user_message"]
    assert "add this to the itinerary" in user_message
    assert "Flight AA123" in user_message


@pytest.mark.asyncio
@patch("app.services.message_handler.attachment_processor")
@patch("app.services.message_handler.groupme")
@patch("app.services.message_handler.agent_service")
@patch("app.services.message_handler.storage")
async def test_attachment_only_no_text(mock_storage_mod, mock_agent, mock_groupme, mock_attachment):
    """A message with an attachment but no text still sends extracted content to the agent."""
    mock_storage = _make_storage_mock(active={"trip_id": "t1", "trip_name": "Rome 2025"})
    mock_storage_mod.claim_message_processed = mock_storage.claim_message_processed
    mock_storage_mod.get_active_trip = mock_storage.get_active_trip
    mock_storage_mod.read_trip_files = mock_storage.read_trip_files
    mock_storage_mod._get_group_lock = mock_storage._get_group_lock

    mock_attachment.process_attachments = AsyncMock(
        return_value="### Attached: screenshot.jpg\nHotel booking #12345"
    )
    mock_agent.get_agent_response = AsyncMock(return_value={"message": "I see a hotel booking!"})
    mock_groupme.send_message = AsyncMock()

    msg = _make_message(
        text="@sensei",
        attachments=[{"type": "image", "url": "https://i.groupme.com/screenshot.jpg"}],
    )
    await handle_message(msg, AsyncMock(), AsyncMock(), _make_settings())

    user_message = mock_agent.get_agent_response.call_args.kwargs["user_message"]
    assert "Hotel booking #12345" in user_message
