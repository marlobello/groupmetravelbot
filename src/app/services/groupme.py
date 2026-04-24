from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)
GROUPME_BOT_POST_URL = "https://api.groupme.com/v3/bots/post"
MAX_MESSAGE_LENGTH = 1000


async def send_message(bot_id: str, text: str) -> None:
    """Send a message to GroupMe, splitting if over 1000 chars."""
    chunks = _split_message(text, MAX_MESSAGE_LENGTH)
    async with httpx.AsyncClient() as client:
        for chunk in chunks:
            response = await client.post(
                GROUPME_BOT_POST_URL,
                json={"bot_id": bot_id, "text": chunk},
            )
            if response.status_code != 202:
                logger.warning("GroupMe API returned %s: %s", response.status_code, response.text)


def _split_message(text: str, max_length: int) -> list[str]:
    """Split text into chunks, preferring line breaks."""
    if len(text) <= max_length:
        return [text]
    chunks: list[str] = []
    while text:
        if len(text) <= max_length:
            chunks.append(text)
            break
        # Try to split at a newline
        split_idx = text.rfind("\n", 0, max_length)
        if split_idx == -1:
            # Try space
            split_idx = text.rfind(" ", 0, max_length)
        if split_idx == -1:
            split_idx = max_length
        chunks.append(text[:split_idx])
        text = text[split_idx:].lstrip()
    return chunks
