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
    # Ignore bot messages to prevent loops
    if message.sender_type == "bot":
        return {"status": "ignored"}

    settings = request.app.state.settings
    # Check if bot is mentioned
    if not message.text or settings.bot_trigger_keyword.lower() not in message.text.lower():
        return {"status": "not_triggered"}

    # Process in background — return 200 immediately
    background_tasks.add_task(
        handle_message,
        message=message,
        cosmos_container=request.app.state.cosmos_container,
        credential=request.app.state.credential,
        settings=settings,
    )
    return {"status": "processing"}
