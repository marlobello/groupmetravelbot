"""Message handler — thin orchestrator between GroupMe, Blob Storage, and the agent."""

from __future__ import annotations

import logging

from azure.identity.aio import DefaultAzureCredential
from azure.storage.blob.aio import ContainerClient

from app.config import Settings
from app.models.groupme import GroupMeMessage
from app.services import agent as agent_service
from app.services import attachment_processor, groupme, storage

logger = logging.getLogger(__name__)


async def handle_message(
    message: GroupMeMessage,
    blob_container: ContainerClient,
    credential: DefaultAzureCredential,
    settings: Settings,
) -> None:
    """Process an incoming GroupMe message.

    The per-group lock serialises processing within a replica, and the atomic
    idempotency claim (see ``storage.claim_message_processed``) guards against
    duplicate webhook deliveries both within and across replicas.
    """
    try:
        async with storage._get_group_lock(message.group_id):
            # Atomically claim the message — skips duplicate deliveries.
            claimed = await storage.claim_message_processed(
                blob_container, message.group_id, message.id
            )
            if not claimed:
                logger.info("Message %s already processed, skipping", message.id)
                return

            logger.info(
                "Processing message %s from group %s (length=%d, attachments=%d)",
                message.id,
                message.group_id,
                len(message.text or ""),
                len(message.attachments) if message.attachments else 0,
            )

            # Strip trigger keyword for cleaner agent input
            clean_text = (
                message.text.replace(settings.bot_trigger_keyword, "").strip()
                if message.text
                else ""
            )

            # Load active trip + documents
            active = await storage.get_active_trip(blob_container, message.group_id)
            trip_files: dict[str, str] | None = None
            if active:
                trip_files = await storage.read_trip_files(
                    blob_container, message.group_id, active["trip_id"]
                )

            # Process any file/image attachments
            attachment_text = None
            if message.attachments:
                attachment_text = await attachment_processor.process_attachments(
                    message.attachments, settings, credential
                )

            # Build the full user message for the agent
            agent_message = clean_text
            if attachment_text:
                agent_message = (
                    f"{clean_text}\n\n{attachment_text}" if clean_text else attachment_text
                )

            result = await agent_service.get_agent_response(
                credential=credential,
                settings=settings,
                user_message=agent_message,
                user_name=message.name,
                trip_files=trip_files,
                blob_container=blob_container,
                group_id=message.group_id,
                trip_id=active["trip_id"] if active else None,
            )

            # Send response
            chat_message = result.get("message", "")
            if chat_message:
                await groupme.send_message(settings.groupme_bot_id, chat_message)

    except Exception:
        logger.exception("Error handling message %s in group %s", message.id, message.group_id)
        await groupme.send_message(
            settings.groupme_bot_id,
            "Sorry, something went wrong. Please try again.",
        )
