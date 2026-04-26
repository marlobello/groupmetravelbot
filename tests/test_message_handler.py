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


# ── Basic flow ────────────────────────────────────────────────────────


@pytest.mark.asyncio
@patch("app.services.message_handler.groupme")
@patch("app.services.message_handler.llm")
@patch("app.services.message_handler.storage")
async def test_basic_query_flow(mock_storage, mock_llm, mock_groupme):
    """LLM returns a message with no file updates — just sends chat reply."""
    mock_storage.check_message_processed = AsyncMock(return_value=False)
    mock_storage.get_active_trip = AsyncMock(
        return_value={"trip_id": "t1", "trip_name": "Rome 2025"}
    )
    mock_storage.read_trip_files = AsyncMock(
        return_value={
            "trip.md": "# Rome",
            "brainstorming.md": "",
            "planning.md": "",
            "itinerary.md": "",
        }
    )
    mock_storage.read_chat_history = AsyncMock(return_value=[])
    mock_storage.write_chat_history = AsyncMock()
    mock_storage.mark_message_processed = AsyncMock()

    lock = AsyncMock()
    lock.__aenter__ = AsyncMock(return_value=None)
    lock.__aexit__ = AsyncMock(return_value=False)
    mock_storage._get_group_lock = MagicMock(return_value=lock)

    mock_llm.get_response = AsyncMock(return_value={"message": "Rome has tons to see! 🏛️"})
    mock_groupme.send_message = AsyncMock()

    await handle_message(_make_message(), AsyncMock(), AsyncMock(), _make_settings())

    mock_groupme.send_message.assert_called_once_with("bot-123", "Rome has tons to see! 🏛️")
    mock_storage.write_trip_file.assert_not_called()


@pytest.mark.asyncio
@patch("app.services.message_handler.groupme")
@patch("app.services.message_handler.llm")
@patch("app.services.message_handler.storage")
async def test_file_update_flow(mock_storage, mock_llm, mock_groupme):
    """LLM returns file updates — they get written to blob storage."""
    container = AsyncMock()

    mock_storage.check_message_processed = AsyncMock(return_value=False)
    mock_storage.get_active_trip = AsyncMock(
        return_value={"trip_id": "t1", "trip_name": "Rome 2025"}
    )
    mock_storage.read_trip_files = AsyncMock(
        return_value={
            "trip.md": "",
            "brainstorming.md": "",
            "planning.md": "",
            "itinerary.md": "",
        }
    )
    mock_storage.write_trip_file = AsyncMock()
    mock_storage.read_chat_history = AsyncMock(return_value=[])
    mock_storage.write_chat_history = AsyncMock()
    mock_storage.mark_message_processed = AsyncMock()

    lock = AsyncMock()
    lock.__aenter__ = AsyncMock(return_value=None)
    lock.__aexit__ = AsyncMock(return_value=False)
    mock_storage._get_group_lock = MagicMock(return_value=lock)

    mock_llm.get_response = AsyncMock(
        return_value={
            "message": "Added to brainstorming!",
            "file_updates": {"brainstorming.md": "# Ideas\n- Colosseum"},
        }
    )
    mock_groupme.send_message = AsyncMock()

    await handle_message(_make_message(), container, AsyncMock(), _make_settings())

    mock_storage.write_trip_file.assert_called_once_with(
        container, "g1", "t1", "brainstorming.md", "# Ideas\n- Colosseum"
    )
    mock_groupme.send_message.assert_called_once()


# ── New trip ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
@patch("app.services.message_handler.groupme")
@patch("app.services.message_handler.llm")
@patch("app.services.message_handler.storage")
async def test_new_trip_creation(mock_storage, mock_llm, mock_groupme):
    container = AsyncMock()

    mock_storage.check_message_processed = AsyncMock(return_value=False)
    mock_storage.get_active_trip = AsyncMock(return_value=None)
    mock_storage.create_trip = AsyncMock(
        return_value={"trip_id": "new-1", "trip_name": "Tokyo 2025"}
    )
    mock_storage.read_chat_history = AsyncMock(return_value=[])
    mock_storage.write_chat_history = AsyncMock()
    mock_storage.mark_message_processed = AsyncMock()

    lock = AsyncMock()
    lock.__aenter__ = AsyncMock(return_value=None)
    lock.__aexit__ = AsyncMock(return_value=False)
    mock_storage._get_group_lock = MagicMock(return_value=lock)

    mock_llm.get_response = AsyncMock(
        return_value={
            "message": "🌴 Let's plan Tokyo 2025!",
            "new_trip": "Tokyo 2025",
        }
    )
    mock_groupme.send_message = AsyncMock()

    await handle_message(
        _make_message(text="@sensei start a trip to Tokyo"),
        container,
        AsyncMock(),
        _make_settings(),
    )

    mock_storage.create_trip.assert_called_once_with(container, "g1", "Tokyo 2025")
    mock_groupme.send_message.assert_called_once()


# ── Archive trip ──────────────────────────────────────────────────────


@pytest.mark.asyncio
@patch("app.services.message_handler.groupme")
@patch("app.services.message_handler.llm")
@patch("app.services.message_handler.storage")
async def test_archive_trip(mock_storage, mock_llm, mock_groupme):
    container = AsyncMock()

    mock_storage.check_message_processed = AsyncMock(return_value=False)
    mock_storage.get_active_trip = AsyncMock(
        return_value={"trip_id": "t1", "trip_name": "Rome 2025"}
    )
    mock_storage.read_trip_files = AsyncMock(
        return_value={
            "trip.md": "",
            "brainstorming.md": "",
            "planning.md": "",
            "itinerary.md": "",
        }
    )
    mock_storage.archive_trip = AsyncMock()
    mock_storage.read_chat_history = AsyncMock(return_value=[])
    mock_storage.write_chat_history = AsyncMock()
    mock_storage.mark_message_processed = AsyncMock()

    lock = AsyncMock()
    lock.__aenter__ = AsyncMock(return_value=None)
    lock.__aexit__ = AsyncMock(return_value=False)
    mock_storage._get_group_lock = MagicMock(return_value=lock)

    mock_llm.get_response = AsyncMock(
        return_value={
            "message": "📦 Trip archived!",
            "archive_trip": True,
        }
    )
    mock_groupme.send_message = AsyncMock()

    await handle_message(
        _make_message(text="@sensei archive the trip"),
        container,
        AsyncMock(),
        _make_settings(),
    )

    mock_storage.archive_trip.assert_called_once_with(container, "g1")


# ── Idempotency ───────────────────────────────────────────────────────


@pytest.mark.asyncio
@patch("app.services.message_handler.groupme")
@patch("app.services.message_handler.llm")
@patch("app.services.message_handler.storage")
async def test_duplicate_message_skipped(mock_storage, mock_llm, mock_groupme):
    mock_storage.check_message_processed = AsyncMock(return_value=True)

    await handle_message(_make_message(), AsyncMock(), AsyncMock(), _make_settings())

    mock_llm.get_response.assert_not_called()
    mock_groupme.send_message.assert_not_called()


# ── Error handling ────────────────────────────────────────────────────


@pytest.mark.asyncio
@patch("app.services.message_handler.groupme")
@patch("app.services.message_handler.llm")
@patch("app.services.message_handler.storage")
async def test_error_sends_apology(mock_storage, mock_llm, mock_groupme):
    mock_storage.check_message_processed = AsyncMock(return_value=False)
    mock_storage.get_active_trip = AsyncMock(side_effect=Exception("boom"))
    mock_groupme.send_message = AsyncMock()

    await handle_message(_make_message(), AsyncMock(), AsyncMock(), _make_settings())

    mock_groupme.send_message.assert_called_once()
    assert "something went wrong" in mock_groupme.send_message.call_args[0][1].lower()


# ── No trip, no new_trip → just chat ──────────────────────────────────


@pytest.mark.asyncio
@patch("app.services.message_handler.groupme")
@patch("app.services.message_handler.llm")
@patch("app.services.message_handler.storage")
async def test_no_trip_just_chat(mock_storage, mock_llm, mock_groupme):
    mock_storage.check_message_processed = AsyncMock(return_value=False)
    mock_storage.get_active_trip = AsyncMock(return_value=None)
    mock_storage.read_chat_history = AsyncMock(return_value=[])
    mock_storage.write_chat_history = AsyncMock()
    mock_storage.mark_message_processed = AsyncMock()

    lock = AsyncMock()
    lock.__aenter__ = AsyncMock(return_value=None)
    lock.__aexit__ = AsyncMock(return_value=False)
    mock_storage._get_group_lock = MagicMock(return_value=lock)

    mock_llm.get_response = AsyncMock(
        return_value={"message": "Hey! Want to start planning a trip? 🌍"}
    )
    mock_groupme.send_message = AsyncMock()

    await handle_message(_make_message(), AsyncMock(), AsyncMock(), _make_settings())

    mock_storage.read_trip_files.assert_not_called()
    mock_groupme.send_message.assert_called_once()


# ── Conversation history ──────────────────────────────────────────────


@pytest.mark.asyncio
@patch("app.services.message_handler.groupme")
@patch("app.services.message_handler.llm")
@patch("app.services.message_handler.storage")
async def test_chat_history_passed_to_llm(mock_storage, mock_llm, mock_groupme):
    """Chat history is loaded and passed to the LLM, then updated after response."""
    container = AsyncMock()
    prior_history = [
        {"role": "user", "content": "Alice: what about Rome?"},
        {"role": "assistant", "content": "Rome sounds great!"},
    ]

    mock_storage.check_message_processed = AsyncMock(return_value=False)
    mock_storage.get_active_trip = AsyncMock(
        return_value={"trip_id": "t1", "trip_name": "Rome 2025"}
    )
    mock_storage.read_trip_files = AsyncMock(
        return_value={
            "trip.md": "# Rome",
            "brainstorming.md": "",
            "planning.md": "",
            "itinerary.md": "",
        }
    )
    mock_storage.read_chat_history = AsyncMock(return_value=prior_history)
    mock_storage.write_chat_history = AsyncMock()
    mock_storage.mark_message_processed = AsyncMock()

    lock = AsyncMock()
    lock.__aenter__ = AsyncMock(return_value=None)
    lock.__aexit__ = AsyncMock(return_value=False)
    mock_storage._get_group_lock = MagicMock(return_value=lock)

    mock_llm.get_response = AsyncMock(return_value={"message": "Yes, add it to brainstorming!"})
    mock_groupme.send_message = AsyncMock()

    await handle_message(
        _make_message(text="@sensei yes put that on the list"),
        container,
        AsyncMock(),
        _make_settings(),
    )

    # Verify history was passed to LLM
    llm_call = mock_llm.get_response.call_args
    assert llm_call.kwargs["chat_history"] == prior_history

    # Verify updated history was saved (prior + new user + new assistant)
    save_call = mock_storage.write_chat_history.call_args
    saved_history = save_call[0][2]
    assert len(saved_history) == 4
    assert saved_history[-2]["role"] == "user"
    assert saved_history[-1]["role"] == "assistant"
    assert saved_history[-1]["content"] == "Yes, add it to brainstorming!"


# ── Attachment processing ─────────────────────────────────────────────


@pytest.mark.asyncio
@patch("app.services.message_handler.attachment_processor")
@patch("app.services.message_handler.groupme")
@patch("app.services.message_handler.llm")
@patch("app.services.message_handler.storage")
async def test_attachment_text_appended_to_llm_message(
    mock_storage, mock_llm, mock_groupme, mock_attachment
):
    """Attachment text is extracted and appended to the user message sent to the LLM."""
    container = AsyncMock()

    mock_storage.check_message_processed = AsyncMock(return_value=False)
    mock_storage.get_active_trip = AsyncMock(
        return_value={"trip_id": "t1", "trip_name": "Rome 2025"}
    )
    mock_storage.read_trip_files = AsyncMock(
        return_value={
            "trip.md": "# Rome",
            "brainstorming.md": "",
            "planning.md": "",
            "itinerary.md": "",
        }
    )
    mock_storage.read_chat_history = AsyncMock(return_value=[])
    mock_storage.write_chat_history = AsyncMock()
    mock_storage.mark_message_processed = AsyncMock()

    lock = AsyncMock()
    lock.__aenter__ = AsyncMock(return_value=None)
    lock.__aexit__ = AsyncMock(return_value=False)
    mock_storage._get_group_lock = MagicMock(return_value=lock)

    mock_attachment.process_attachments = AsyncMock(
        return_value="### Attached: flight.pdf\nFlight AA123 DFW→NRT Jan 15"
    )
    mock_llm.get_response = AsyncMock(return_value={"message": "Got it! I see flight AA123."})
    mock_groupme.send_message = AsyncMock()

    msg = _make_message(
        text="@sensei add this to the itinerary",
        attachments=[
            {
                "type": "file",
                "url": "https://i.groupme.com/flight.pdf",
                "file_name": "flight.pdf",
            }
        ],
    )
    await handle_message(msg, container, AsyncMock(), _make_settings())

    # Verify the LLM received both the user text and attachment content
    llm_call = mock_llm.get_response.call_args
    assert "add this to the itinerary" in llm_call.kwargs["user_message"]
    assert "Flight AA123" in llm_call.kwargs["user_message"]


@pytest.mark.asyncio
@patch("app.services.message_handler.attachment_processor")
@patch("app.services.message_handler.groupme")
@patch("app.services.message_handler.llm")
@patch("app.services.message_handler.storage")
async def test_attachment_only_no_text(mock_storage, mock_llm, mock_groupme, mock_attachment):
    """Message with attachment but no text still sends extracted content to LLM."""
    container = AsyncMock()

    mock_storage.check_message_processed = AsyncMock(return_value=False)
    mock_storage.get_active_trip = AsyncMock(
        return_value={"trip_id": "t1", "trip_name": "Rome 2025"}
    )
    mock_storage.read_trip_files = AsyncMock(
        return_value={
            "trip.md": "# Rome",
            "brainstorming.md": "",
            "planning.md": "",
            "itinerary.md": "",
        }
    )
    mock_storage.read_chat_history = AsyncMock(return_value=[])
    mock_storage.write_chat_history = AsyncMock()
    mock_storage.mark_message_processed = AsyncMock()

    lock = AsyncMock()
    lock.__aenter__ = AsyncMock(return_value=None)
    lock.__aexit__ = AsyncMock(return_value=False)
    mock_storage._get_group_lock = MagicMock(return_value=lock)

    mock_attachment.process_attachments = AsyncMock(
        return_value="### Attached: screenshot.jpg\nHotel booking #12345"
    )
    mock_llm.get_response = AsyncMock(return_value={"message": "I see a hotel booking!"})
    mock_groupme.send_message = AsyncMock()

    msg = _make_message(
        text="@sensei",
        attachments=[{"type": "image", "url": "https://i.groupme.com/screenshot.jpg"}],
    )
    await handle_message(msg, container, AsyncMock(), _make_settings())

    llm_call = mock_llm.get_response.call_args
    assert "Hotel booking #12345" in llm_call.kwargs["user_message"]
