"""Message handler — thin orchestrator between GroupMe, Blob Storage, and Azure OpenAI."""

from __future__ import annotations

import logging

from azure.identity.aio import DefaultAzureCredential
from azure.storage.blob.aio import ContainerClient

from app.config import Settings
from app.models.groupme import GroupMeMessage
from app.services import groupme, llm, storage

logger = logging.getLogger(__name__)


async def handle_message(
    message: GroupMeMessage,
    blob_container: ContainerClient,
    credential: DefaultAzureCredential,
    settings: Settings,
) -> None:
    """Process an incoming GroupMe message."""
    try:
        # Idempotency check
        if await storage.check_message_processed(blob_container, message.group_id, message.id):
            logger.info("Message %s already processed, skipping", message.id)
            return

        # Strip trigger keyword for cleaner LLM input
        clean_text = (
            message.text.replace(settings.bot_trigger_keyword, "").strip() if message.text else ""
        )

        # Load active trip + documents
        active = await storage.get_active_trip(blob_container, message.group_id)
        trip_files: dict[str, str] | None = None
        if active:
            trip_files = await storage.read_trip_files(
                blob_container, message.group_id, active["trip_id"]
            )

        # Load conversation history
        chat_history = await storage.read_chat_history(blob_container, message.group_id)

        # Acquire per-group lock to serialise writes
        async with storage._get_group_lock(message.group_id):
            # Ask the LLM
            result = await llm.get_response(
                credential=credential,
                settings=settings,
                user_message=clean_text,
                user_name=message.name,
                trip_files=trip_files,
                chat_history=chat_history,
            )

            # Handle trip lifecycle commands
            if result.get("new_trip"):
                active = await storage.create_trip(
                    blob_container, message.group_id, result["new_trip"]
                )
                logger.info("Created new trip: %s", result["new_trip"])

            elif result.get("archive_trip") and active:
                await storage.archive_trip(blob_container, message.group_id)
                logger.info("Archived trip for group %s", message.group_id)

            elif result.get("file_updates") and active:
                for filename, content in result["file_updates"].items():
                    await storage.write_trip_file(
                        blob_container,
                        message.group_id,
                        active["trip_id"],
                        filename,
                        content,
                    )
                logger.info(
                    "Updated files: %s",
                    ", ".join(result["file_updates"].keys()),
                )

        # Mark processed
        await storage.mark_message_processed(blob_container, message.group_id, message.id)

        # Save conversation history (user message + assistant response)
        chat_message = result.get("message", "")
        if chat_message:
            chat_history.append({"role": "user", "content": f"{message.name}: {clean_text}"})
            chat_history.append({"role": "assistant", "content": chat_message})
            await storage.write_chat_history(blob_container, message.group_id, chat_history)

        # Send response
        if chat_message:
            await groupme.send_message(settings.groupme_bot_id, chat_message)

    except Exception:
        logger.exception("Error handling message %s", message.id)
        await groupme.send_message(
            settings.groupme_bot_id,
            "Sorry, something went wrong. Please try again.",
        )
