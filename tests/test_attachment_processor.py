from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.attachment_processor import (
    _get_file_extension,
    process_attachments,
)


def _make_settings():
    s = MagicMock()
    s.azure_openai_endpoint = "https://test.openai.azure.com/"
    s.azure_openai_deployment = "gpt-4o"
    s.azure_client_id = None
    return s


# ── _get_file_extension ──────────────────────────────────────────────


def test_extension_from_filename():
    assert _get_file_extension({"file_name": "booking.pdf"}) == ".pdf"


def test_extension_from_filename_uppercase():
    assert _get_file_extension({"file_name": "REPORT.DOCX"}) == ".docx"


def test_extension_image_png():
    att = {"type": "image", "url": "https://i.groupme.com/photo.png"}
    assert _get_file_extension(att) == ".png"


def test_extension_image_default_jpg():
    assert _get_file_extension({"type": "image", "url": "https://i.groupme.com/photo"}) == ".jpg"


def test_extension_no_info():
    assert _get_file_extension({}) == ""


# ── process_attachments ──────────────────────────────────────────────


@pytest.mark.asyncio
@patch("app.services.attachment_processor._build_converter")
@patch("app.services.attachment_processor._download_attachment")
async def test_process_file_attachment(mock_download, mock_converter):
    """Successfully process a PDF attachment."""
    mock_download.return_value = (b"fake pdf bytes", "application/pdf")

    mock_result = MagicMock()
    mock_result.text_content = "Flight AA123 from DFW to NRT on Jan 15"
    converter = MagicMock()
    converter.convert_stream.return_value = mock_result
    mock_converter.return_value = converter

    attachments = [
        {
            "type": "file",
            "url": "https://i.groupme.com/booking.pdf",
            "file_name": "booking.pdf",
        }
    ]
    result = await process_attachments(attachments, _make_settings(), AsyncMock())

    assert result is not None
    assert "Flight AA123" in result
    assert "booking.pdf" in result


@pytest.mark.asyncio
@patch("app.services.attachment_processor._build_converter")
@patch("app.services.attachment_processor._download_attachment")
async def test_process_image_attachment(mock_download, mock_converter):
    """Successfully process an image attachment."""
    mock_download.return_value = (b"fake jpg bytes", "image/jpeg")

    mock_result = MagicMock()
    mock_result.text_content = "Screenshot of hotel confirmation"
    converter = MagicMock()
    converter.convert_stream.return_value = mock_result
    mock_converter.return_value = converter

    attachments = [{"type": "image", "url": "https://i.groupme.com/photo.jpg"}]
    result = await process_attachments(attachments, _make_settings(), AsyncMock())

    assert result is not None
    assert "Screenshot of hotel confirmation" in result
    assert "image attachment" in result


@pytest.mark.asyncio
async def test_process_no_attachments():
    """No processable attachments returns None."""
    result = await process_attachments([], _make_settings(), AsyncMock())
    assert result is None


@pytest.mark.asyncio
async def test_process_unsupported_type():
    """Unsupported attachment types are skipped."""
    attachments = [{"type": "emoji", "placeholder": "🎉"}]
    result = await process_attachments(attachments, _make_settings(), AsyncMock())
    assert result is None


@pytest.mark.asyncio
@patch("app.services.attachment_processor._build_converter")
@patch("app.services.attachment_processor._download_attachment")
async def test_process_download_failure(mock_download, mock_converter):
    """Download failure produces a graceful error message."""
    mock_download.side_effect = Exception("Connection timeout")
    mock_converter.return_value = MagicMock()

    attachments = [{"type": "file", "url": "https://i.groupme.com/doc.pdf", "file_name": "doc.pdf"}]
    result = await process_attachments(attachments, _make_settings(), AsyncMock())

    assert result is not None
    assert "could not be read" in result


@pytest.mark.asyncio
@patch("app.services.attachment_processor._build_converter")
@patch("app.services.attachment_processor._download_attachment")
async def test_process_conversion_failure(mock_download, mock_converter):
    """Conversion failure produces a graceful error message."""
    mock_download.return_value = (b"corrupt data", "application/pdf")

    converter = MagicMock()
    converter.convert_stream.side_effect = Exception("Parse error")
    mock_converter.return_value = converter

    attachments = [{"type": "file", "url": "https://i.groupme.com/bad.pdf", "file_name": "bad.pdf"}]
    result = await process_attachments(attachments, _make_settings(), AsyncMock())

    assert result is not None
    assert "could not be read" in result


@pytest.mark.asyncio
@patch("app.services.attachment_processor._build_converter")
@patch("app.services.attachment_processor._download_attachment")
async def test_process_empty_extraction(mock_download, mock_converter):
    """Empty extraction result shows appropriate message."""
    mock_download.return_value = (b"blank image", "image/png")

    mock_result = MagicMock()
    mock_result.text_content = ""
    converter = MagicMock()
    converter.convert_stream.return_value = mock_result
    mock_converter.return_value = converter

    attachments = [{"type": "image", "url": "https://i.groupme.com/blank.png"}]
    result = await process_attachments(attachments, _make_settings(), AsyncMock())

    assert result is not None
    assert "no text could be extracted" in result


@pytest.mark.asyncio
@patch("app.services.attachment_processor._build_converter")
@patch("app.services.attachment_processor._download_attachment")
async def test_process_multiple_attachments(mock_download, mock_converter):
    """Multiple attachments are all processed and concatenated."""
    mock_download.return_value = (b"data", "application/pdf")

    mock_result = MagicMock()
    mock_result.text_content = "Extracted content"
    converter = MagicMock()
    converter.convert_stream.return_value = mock_result
    mock_converter.return_value = converter

    attachments = [
        {"type": "file", "url": "https://i.groupme.com/a.pdf", "file_name": "flight.pdf"},
        {"type": "file", "url": "https://i.groupme.com/b.pdf", "file_name": "hotel.pdf"},
    ]
    result = await process_attachments(attachments, _make_settings(), AsyncMock())

    assert result is not None
    assert "flight.pdf" in result
    assert "hotel.pdf" in result
    assert result.count("Extracted content") == 2
