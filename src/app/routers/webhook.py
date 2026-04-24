from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Request

from app.models.groupme import GroupMeMessage
from app.services.message_handler import handle_message

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.post("/webhook")
async def groupme_callback(
    message: GroupMeMessage,
    request: Request,
    background_tasks: BackgroundTasks,
):
    logger.info("Webhook received: sender_type=%s, text=%r", message.sender_type, message.text)

    # Ignore bot messages to prevent loops
    if message.sender_type == "bot":
        return {"status": "ignored"}

    settings = request.app.state.settings
    # Check if bot is mentioned
    if not message.text or settings.bot_trigger_keyword.lower() not in message.text.lower():
        logger.info("Not triggered (keyword=%s)", settings.bot_trigger_keyword)
        return {"status": "not_triggered"}

    logger.info("Triggered! Processing message from %s", message.name)
    # Process in background — return 200 immediately
    background_tasks.add_task(
        handle_message,
        message=message,
        cosmos_container=request.app.state.cosmos_container,
        credential=request.app.state.credential,
        settings=settings,
    )
    return {"status": "processing"}
