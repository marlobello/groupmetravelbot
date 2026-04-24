from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
def mock_app_state():
    """Set up mock app state for testing."""
    settings = MagicMock()
    settings.bot_trigger_keyword = "@sensei"
    settings.webhook_secret = "test-secret-token"
    settings.web_access_key = ""
    app.state.settings = settings
    app.state.blob_container = AsyncMock()
    app.state.credential = AsyncMock()
    return settings


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_bot_message_ignored(client, mock_app_state):
    payload = {
        "id": "msg1",
        "group_id": "g1",
        "sender_id": "bot1",
        "sender_type": "bot",
        "name": "Sensei",
        "text": "@sensei hello",
        "created_at": 1700000000,
    }
    response = await client.post("/webhook/test-secret-token", json=payload)
    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}


@pytest.mark.asyncio
async def test_non_triggered_message(client, mock_app_state):
    payload = {
        "id": "msg2",
        "group_id": "g1",
        "sender_id": "u1",
        "sender_type": "user",
        "name": "Alice",
        "text": "Just a regular message",
        "created_at": 1700000000,
    }
    response = await client.post("/webhook/test-secret-token", json=payload)
    assert response.status_code == 200
    assert response.json() == {"status": "not_triggered"}


@pytest.mark.asyncio
@patch("app.routers.webhook.handle_message")
async def test_triggered_message_returns_processing(mock_handle, client, mock_app_state):
    payload = {
        "id": "msg3",
        "group_id": "g1",
        "sender_id": "u1",
        "sender_type": "user",
        "name": "Alice",
        "text": "Hey @sensei plan a trip",
        "created_at": 1700000000,
    }
    response = await client.post("/webhook/test-secret-token", json=payload)
    assert response.status_code == 200
    assert response.json() == {"status": "processing"}


@pytest.mark.asyncio
async def test_message_with_no_text(client, mock_app_state):
    payload = {
        "id": "msg4",
        "group_id": "g1",
        "sender_id": "u1",
        "sender_type": "user",
        "name": "Alice",
        "text": None,
        "created_at": 1700000000,
    }
    response = await client.post("/webhook/test-secret-token", json=payload)
    assert response.status_code == 200
    assert response.json() == {"status": "not_triggered"}


@pytest.mark.asyncio
async def test_webhook_wrong_secret_returns_404(client, mock_app_state):
    """Wrong webhook secret should return 404."""
    payload = {
        "id": "msg5",
        "group_id": "g1",
        "sender_id": "u1",
        "sender_type": "user",
        "name": "Alice",
        "text": "@sensei hello",
        "created_at": 1700000000,
    }
    response = await client.post("/webhook/wrong-secret", json=payload)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_webhook_empty_secret_setting_returns_404(client, mock_app_state):
    """If webhook_secret is not configured, all requests should be rejected."""
    mock_app_state.webhook_secret = ""
    payload = {
        "id": "msg6",
        "group_id": "g1",
        "sender_id": "u1",
        "sender_type": "user",
        "name": "Alice",
        "text": "@sensei hello",
        "created_at": 1700000000,
    }
    response = await client.post("/webhook/anything", json=payload)
    assert response.status_code == 404
