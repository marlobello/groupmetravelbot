from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.models.groupme import GroupMeMessage
from app.services.message_handler import handle_message

logger = logging.getLogger(__name__)
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.post("/webhook/{secret}")
@limiter.limit("30/minute")
async def groupme_callback(
    secret: str,
    message: GroupMeMessage,
    request: Request,
    background_tasks: BackgroundTasks,
):
    settings = request.app.state.settings

    # Validate webhook secret (constant-time comparison)
    if not settings.webhook_secret or not secrets.compare_digest(secret, settings.webhook_secret):
        raise HTTPException(status_code=404, detail="Not Found")

    logger.info("Webhook received: sender_type=%s, text=%r", message.sender_type, message.text)

    # Ignore bot messages to prevent loops
    if message.sender_type == "bot":
        return {"status": "ignored"}

    # Check if bot is mentioned
    if not message.text or settings.bot_trigger_keyword.lower() not in message.text.lower():
        logger.info("Not triggered (keyword=%s)", settings.bot_trigger_keyword)
        return {"status": "not_triggered"}

    logger.info("Triggered! Processing message from %s", message.name)
    # Process in background — return 200 immediately
    background_tasks.add_task(
        handle_message,
        message=message,
        blob_container=request.app.state.blob_container,
        credential=request.app.state.credential,
        settings=settings,
    )
    return {"status": "processing"}
