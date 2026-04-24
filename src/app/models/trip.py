from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class Stage(StrEnum):
    BRAINSTORMING = "brainstorming"
    PLANNING = "planning"
    FINALIZED = "finalized"


class Category(StrEnum):
    LODGING = "lodging"
    TRANSPORT = "transport"
    ACTIVITY = "activity"
    DINING = "dining"
    OTHER = "other"


class TripStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class BookingDetails(BaseModel):
    confirmation_number: str | None = None
    provider: str | None = None
    address: str | None = None
    contact_info: str | None = None


class ItemDetails(BaseModel):
    notes: str | None = None
    links: list[str] = []
    dates: dict | None = None  # {"start": "...", "end": "..."}
    booking: BookingDetails = BookingDetails()


class Trip(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    group_id: str = Field(alias="groupId")
    type: Literal["trip"] = "trip"
    name: str
    status: TripStatus = TripStatus.ACTIVE
    created_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(), alias="createdAt"
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(), alias="updatedAt"
    )
    model_config = ConfigDict(populate_by_name=True)


class TripItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    group_id: str = Field(alias="groupId")
    type: Literal["item"] = "item"
    trip_id: str = Field(alias="tripId")
    stage: Stage = Stage.BRAINSTORMING
    category: Category = Category.OTHER
    title: str
    details: ItemDetails = ItemDetails()
    added_by: str = Field(alias="addedBy")
    created_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(), alias="createdAt"
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(), alias="updatedAt"
    )
    model_config = ConfigDict(populate_by_name=True)
