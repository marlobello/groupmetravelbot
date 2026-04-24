from __future__ import annotations

from pydantic import BaseModel


class GroupMeMessage(BaseModel):
    id: str
    group_id: str
    sender_id: str
    sender_type: str
    name: str
    text: str | None = None
    attachments: list[dict] = []
    created_at: int
