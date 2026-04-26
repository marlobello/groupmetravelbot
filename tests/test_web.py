"""Tests for the web trip-viewer routes."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
def mock_app_state():
    settings = MagicMock()
    settings.bot_trigger_keyword = "@sensei"
    settings.webhook_secret = "test-secret"
    settings.web_access_key = ""  # auth disabled by default in tests
    app.state.settings = settings
    # Use MagicMock (not AsyncMock) — get_blob_client and list_blobs are sync
    app.state.blob_container = MagicMock()
    app.state.credential = AsyncMock()
    return settings


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _blob_with_name(name: str):
    """Create a mock blob object with a .name attribute."""
    b = MagicMock()
    b.name = name
    return b


# ── /trips list page ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_trips_empty(client, mock_app_state):
    """No active trips → shows empty message."""
    container = app.state.blob_container
    container.list_blobs.return_value = _empty_async_iter()

    resp = await client.get("/trips")
    assert resp.status_code == 200
    assert "No active trips found" in resp.text


@pytest.mark.asyncio
async def test_list_trips_shows_active(client, mock_app_state):
    """Active trip shows up as a link."""
    container = app.state.blob_container
    container.list_blobs.return_value = _async_iter([_blob_with_name("trips/g1/active_trip.json")])

    blob_client = MagicMock()
    download_mock = AsyncMock()
    download_mock.readall.return_value = json.dumps(
        {"trip_id": "t1", "trip_name": "Rome 2025"}
    ).encode()
    blob_client.download_blob = AsyncMock(return_value=download_mock)
    container.get_blob_client.return_value = blob_client

    resp = await client.get("/trips")
    assert resp.status_code == 200
    assert "Rome 2025" in resp.text
    assert "/trips/g1" in resp.text


# ── /trips/{group_id} detail page ────────────────────────────────────


@pytest.mark.asyncio
async def test_view_trip_not_found(client, mock_app_state):
    """No active trip for group → 404."""
    from azure.core.exceptions import ResourceNotFoundError

    blob_client = MagicMock()
    blob_client.download_blob = AsyncMock(side_effect=ResourceNotFoundError("not found"))
    app.state.blob_container.get_blob_client.return_value = blob_client

    resp = await client.get("/trips/no-such-group")
    assert resp.status_code == 404
    assert "No active trip found" in resp.text


@pytest.mark.asyncio
async def test_view_trip_renders_markdown(client, mock_app_state, sample_trip_files):
    """Active trip renders all 4 tabs with converted markdown."""
    container = app.state.blob_container
    active_info = json.dumps({"trip_id": "t1", "trip_name": "Rome 2025"}).encode()

    def _make_blob_client(name):
        mock = MagicMock()
        dl = AsyncMock()
        if name.endswith("active_trip.json"):
            dl.readall.return_value = active_info
        elif name.endswith("trip.md"):
            dl.readall.return_value = sample_trip_files["trip.md"].encode()
        elif name.endswith("brainstorming.md"):
            dl.readall.return_value = sample_trip_files["brainstorming.md"].encode()
        elif name.endswith("planning.md"):
            dl.readall.return_value = sample_trip_files["planning.md"].encode()
        elif name.endswith("itinerary.md"):
            dl.readall.return_value = sample_trip_files["itinerary.md"].encode()
        mock.download_blob = AsyncMock(return_value=dl)
        return mock

    container.get_blob_client.side_effect = _make_blob_client

    resp = await client.get("/trips/g1")
    assert resp.status_code == 200
    html = resp.text

    # All 4 tabs present
    assert "Overview" in html
    assert "Brainstorming" in html
    assert "Planning" in html
    assert "Itinerary" in html

    # Markdown converted to HTML
    assert "<h1>" in html or "<h2>" in html
    assert "Rome 2025" in html
    assert "Colosseum" in html

    # Tab JS present
    assert "data-target=" in html
    assert "classList" in html


@pytest.mark.asyncio
async def test_view_trip_back_link(client, mock_app_state, sample_trip_files):
    """Page has a back link to /trips."""
    container = app.state.blob_container
    active_info = json.dumps({"trip_id": "t1", "trip_name": "Rome 2025"}).encode()

    def _make_blob_client(name):
        mock = MagicMock()
        dl = AsyncMock()
        if name.endswith("active_trip.json"):
            dl.readall.return_value = active_info
        else:
            dl.readall.return_value = b"# Test\n"
        mock.download_blob = AsyncMock(return_value=dl)
        return mock

    container.get_blob_client.side_effect = _make_blob_client

    resp = await client.get("/trips/g1")
    assert resp.status_code == 200
    assert '/trips"' in resp.text or "/trips'" in resp.text


# ── Helpers ───────────────────────────────────────────────────────────


async def _empty_async_iter():
    return
    yield  # noqa: E711 — makes this an async generator


async def _async_iter(items):
    for item in items:
        yield item


# ── Web auth tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_web_auth_rejects_without_key(client, mock_app_state):
    """When web_access_key is set, requests without key get 403."""
    mock_app_state.web_access_key = "my-secret-key"
    container = app.state.blob_container
    container.list_blobs.return_value = _empty_async_iter()

    resp = await client.get("/trips")
    assert resp.status_code == 403
    assert "Access denied" in resp.text


@pytest.mark.asyncio
async def test_web_auth_accepts_valid_key(client, mock_app_state):
    """Valid ?key= param redirects and sets cookie."""
    mock_app_state.web_access_key = "my-secret-key"

    resp = await client.get("/trips?key=my-secret-key", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "http://test/trips"
    assert "sensei_access" in resp.headers.get("set-cookie", "")


@pytest.mark.asyncio
async def test_web_auth_rejects_wrong_key(client, mock_app_state):
    """Wrong ?key= param still gets 403."""
    mock_app_state.web_access_key = "my-secret-key"

    resp = await client.get("/trips?key=wrong-key")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_web_auth_accepts_valid_cookie(client, mock_app_state):
    """Valid cookie passes auth."""
    mock_app_state.web_access_key = "my-secret-key"
    container = app.state.blob_container
    container.list_blobs.return_value = _empty_async_iter()

    resp = await client.get("/trips", cookies={"sensei_access": "my-secret-key"})
    assert resp.status_code == 200


# ── XSS prevention tests ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_xss_in_trip_name_escaped(client, mock_app_state):
    """Trip name with HTML/script tags is escaped in output."""
    container = app.state.blob_container
    malicious_name = '<script>alert("xss")</script>'
    active_info = json.dumps({"trip_id": "t1", "trip_name": malicious_name}).encode()

    def _make_blob_client(name):
        mock = MagicMock()
        dl = AsyncMock()
        if name.endswith("active_trip.json"):
            dl.readall.return_value = active_info
        else:
            dl.readall.return_value = b"# Test\n"
        mock.download_blob = AsyncMock(return_value=dl)
        return mock

    container.get_blob_client.side_effect = _make_blob_client

    resp = await client.get("/trips/g1")
    assert resp.status_code == 200
    # Raw script tags must NOT appear in output
    assert "<script>alert" not in resp.text
    # Escaped version should appear
    assert "&lt;script&gt;" in resp.text


@pytest.mark.asyncio
async def test_xss_in_markdown_content_escaped(client, mock_app_state):
    """Markdown content with raw HTML tags is escaped."""
    container = app.state.blob_container
    active_info = json.dumps({"trip_id": "t1", "trip_name": "Test Trip"}).encode()

    def _make_blob_client(name):
        mock = MagicMock()
        dl = AsyncMock()
        if name.endswith("active_trip.json"):
            dl.readall.return_value = active_info
        elif name.endswith("brainstorming.md"):
            dl.readall.return_value = b'<img src=x onerror="alert(1)">'
        else:
            dl.readall.return_value = b"# Safe content\n"
        mock.download_blob = AsyncMock(return_value=dl)
        return mock

    container.get_blob_client.side_effect = _make_blob_client

    resp = await client.get("/trips/g1")
    assert resp.status_code == 200
    assert 'onerror="alert(1)"' not in resp.text


@pytest.mark.asyncio
async def test_xss_in_group_list_escaped(client, mock_app_state):
    """Group list with malicious trip names is escaped."""
    container = app.state.blob_container
    container.list_blobs.return_value = _async_iter(
        [_blob_with_name("trips/g1/active_trip.json")]
    )

    malicious_name = '"><img src=x onerror=alert(1)>'
    blob_client = MagicMock()
    download_mock = AsyncMock()
    download_mock.readall.return_value = json.dumps(
        {"trip_id": "t1", "trip_name": malicious_name}
    ).encode()
    blob_client.download_blob = AsyncMock(return_value=download_mock)
    container.get_blob_client.return_value = blob_client

    resp = await client.get("/trips")
    assert resp.status_code == 200
    # Raw HTML tags must be escaped — no unescaped < or > around the payload
    assert "<img src=x" not in resp.text
    # The escaped version should be present as harmless text
    assert "&lt;img" in resp.text
