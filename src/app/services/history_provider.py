"""Blob-backed history provider for the Microsoft Agent Framework.

Stores conversation history as JSON in Azure Blob Storage, one file per group.
Integrates with the agent's session lifecycle (before_run loads, after_run saves).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from typing import Any

from agent_framework import HistoryProvider, Message
from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob.aio import ContainerClient

logger = logging.getLogger(__name__)

MAX_HISTORY_MESSAGES = 40  # Keep last 20 exchanges (user + assistant)


def _json_default(o: Any) -> Any:
    """Coerce objects that ``Message.to_dict()`` leaves as SDK models.

    Web Search replies embed citation annotations (e.g. pydantic
    ``AnnotationURLCitation``) that aren't plain JSON. Convert them to their
    canonical dict form so the history blob can be serialised and round-tripped.
    """
    for attr in ("model_dump", "to_dict", "as_dict", "dict"):
        fn = getattr(o, attr, None)
        if callable(fn):
            try:
                return fn(mode="json") if attr == "model_dump" else fn()
            except TypeError:
                try:
                    return fn()
                except Exception:
                    pass
            except Exception:
                pass
    if hasattr(o, "__dict__"):
        return {k: v for k, v in vars(o).items() if not k.startswith("_")}
    return str(o)


class BlobHistoryProvider(HistoryProvider):
    """Persists agent conversation history to Azure Blob Storage.

    Each group gets a single blob at `trips/{group_id}/session_history.json`
    containing serialised Message objects as JSON Lines.
    """

    def __init__(
        self,
        container: ContainerClient,
        group_id: str,
        *,
        source_id: str = "blob_history",
        load_messages: bool = True,
        store_inputs: bool = True,
        store_outputs: bool = True,
    ) -> None:
        super().__init__(
            source_id=source_id,
            load_messages=load_messages,
            store_inputs=store_inputs,
            store_outputs=store_outputs,
        )
        self._container = container
        self._group_id = group_id
        self._blob_path = f"trips/{group_id}/session_history.json"

    async def get_messages(
        self,
        session_id: str | None,
        *,
        state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> list[Message]:
        """Load conversation history from blob storage."""
        blob = self._container.get_blob_client(self._blob_path)
        try:
            data = await blob.download_blob()
            content = await data.readall()
            items = json.loads(content)
            if not isinstance(items, list):
                return []
            # Deserialise and trim to recent messages
            messages = [Message.from_dict(m) for m in items[-MAX_HISTORY_MESSAGES:]]
            logger.debug(
                "Loaded %d history messages for group %s",
                len(messages),
                self._group_id,
            )
            return messages
        except (ResourceNotFoundError, json.JSONDecodeError, KeyError):
            return []
        except Exception:
            logger.exception("Error loading history for group %s", self._group_id)
            return []

    async def save_messages(
        self,
        session_id: str | None,
        messages: Sequence[Message],
        *,
        state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Save conversation history to blob storage."""
        if not messages:
            return

        # Load existing, append new, trim
        existing = await self.get_messages(session_id)
        all_messages = existing + list(messages)
        trimmed = all_messages[-MAX_HISTORY_MESSAGES:]

        blob = self._container.get_blob_client(self._blob_path)
        serialised = json.dumps([m.to_dict() for m in trimmed], default=_json_default)
        await blob.upload_blob(serialised.encode(), overwrite=True)
        logger.debug(
            "Saved %d history messages for group %s",
            len(trimmed),
            self._group_id,
        )
