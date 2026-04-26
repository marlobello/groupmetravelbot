"""Attachment processor — download GroupMe attachments and convert to markdown via markitdown."""

from __future__ import annotations

import asyncio
import io
import ipaddress
import logging
import socket
from typing import Any
from urllib.parse import urlparse

import httpx
from markitdown import MarkItDown

from app.config import Settings

logger = logging.getLogger(__name__)

MAX_DOWNLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_CONVERTED_BYTES = 1 * 1024 * 1024  # 1 MB text output cap
DOWNLOAD_TIMEOUT = 30.0  # seconds
CONVERSION_TIMEOUT = 30.0  # seconds

# Supported GroupMe attachment types
_PROCESSABLE_TYPES = {"image", "file", "linked_image"}

# Allowlisted domains for attachment downloads (GroupMe CDN)
_ALLOWED_DOMAINS = {
    "i.groupme.com",
    "v.groupme.com",
    "image.groupme.com",
    "files.groupme.com",
}


def _is_safe_url(url: str) -> bool:
    """Validate that a URL is safe to fetch — HTTPS only, no private/internal IPs."""
    try:
        parsed = urlparse(url)
    except Exception:
        return False

    if parsed.scheme != "https":
        return False

    hostname = parsed.hostname
    if not hostname:
        return False

    # Block obvious internal hostnames
    if hostname in ("localhost", "metadata.google.internal"):
        return False

    # Allow known GroupMe domains without further checks
    if hostname in _ALLOWED_DOMAINS:
        return True

    # For unknown domains, resolve and check for private IPs
    try:
        for info in socket.getaddrinfo(hostname, None):
            addr = info[4][0]
            ip = ipaddress.ip_address(addr)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                logger.warning("Blocked attachment URL resolving to private IP: %s → %s", url, addr)
                return False
    except socket.gaierror:
        return False

    return True


def _build_converter(settings: Settings, credential: Any) -> MarkItDown:
    """Build a MarkItDown instance with LLM support for image OCR."""
    try:
        from azure.identity import DefaultAzureCredential as SyncCredential

        sync_credential = SyncCredential(managed_identity_client_id=settings.azure_client_id)
        token = sync_credential.get_token("https://cognitiveservices.azure.com/.default")

        from openai import AzureOpenAI

        llm_client = AzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            azure_ad_token=token.token,
            api_version="2024-12-01-preview",
        )
        return MarkItDown(
            enable_plugins=True,
            llm_client=llm_client,
            llm_model=settings.azure_openai_deployment,
        )
    except Exception:
        logger.warning("Could not create LLM-backed converter, falling back to basic")
        return MarkItDown()


async def _download_attachment(url: str) -> tuple[bytes, str]:
    """Download an attachment, respecting size and timeout limits.

    Returns (content_bytes, content_type).
    Raises ValueError for unsafe URLs or oversized content.
    """
    if not _is_safe_url(url):
        raise ValueError(f"Blocked unsafe attachment URL: {url}")

    async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT, follow_redirects=False) as client:
        response = await client.get(url)
        response.raise_for_status()

        content_type = response.headers.get("content-type", "application/octet-stream")
        content = response.content

        if len(content) > MAX_DOWNLOAD_BYTES:
            raise ValueError(
                f"Attachment too large: {len(content)} bytes (max {MAX_DOWNLOAD_BYTES})"
            )

        return content, content_type


def _get_file_extension(attachment: dict) -> str:
    """Infer a file extension from attachment metadata."""
    file_name = attachment.get("file_name", "")
    if file_name and "." in file_name:
        return "." + file_name.rsplit(".", 1)[-1].lower()

    att_type = attachment.get("type", "")
    if att_type == "image":
        url = attachment.get("url", "")
        if ".png" in url.lower():
            return ".png"
        return ".jpg"
    return ""


async def process_attachments(
    attachments: list[dict],
    settings: Settings,
    credential: Any,
) -> str | None:
    """Process all attachments in a message and return extracted markdown text.

    Returns None if no attachments could be processed, or a combined markdown string.
    """
    processable = [a for a in attachments if a.get("type") in _PROCESSABLE_TYPES]
    if not processable:
        return None

    converter = _build_converter(settings, credential)
    results: list[str] = []

    for attachment in processable:
        url = attachment.get("url", "")
        att_type = attachment.get("type", "unknown")
        file_name = attachment.get("file_name", "attachment")

        try:
            content, content_type = await _download_attachment(url)
            ext = _get_file_extension(attachment)

            # Run synchronous conversion in a thread with timeout
            def _convert(data: bytes, extension: str) -> str:
                result = converter.convert_stream(io.BytesIO(data), file_extension=extension)
                return (result.text_content or "").strip()

            text = await asyncio.wait_for(
                asyncio.to_thread(_convert, content, ext),
                timeout=CONVERSION_TIMEOUT,
            )

            # Cap output size to prevent memory exhaustion from decompression bombs
            if len(text.encode("utf-8")) > MAX_CONVERTED_BYTES:
                text = text[: MAX_CONVERTED_BYTES // 4]  # rough char limit
                text += "\n\n_(Content truncated — file was too large to fully extract)_"

            if text:
                label = file_name if att_type == "file" else f"{att_type} attachment"
                results.append(f"### Attached: {label}\n{text}")
            else:
                results.append(
                    f"### Attached: {file_name}\n_(File was shared but no text could be extracted)_"
                )

        except Exception:
            logger.exception("Failed to process %s attachment", att_type)
            results.append(f"### Attached: {file_name}\n_(File was shared but could not be read)_")

    if not results:
        return None

    return "\n\n".join(results)
