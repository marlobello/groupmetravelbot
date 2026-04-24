from __future__ import annotations

import io
import logging
from datetime import UTC, datetime, timedelta

from azure.identity.aio import DefaultAzureCredential
from azure.storage.blob import BlobSasPermissions, ContentSettings, generate_blob_sas
from azure.storage.blob.aio import BlobServiceClient
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.config import Settings
from app.models.trip import Stage, Trip, TripItem

logger = logging.getLogger(__name__)

TEMPLATE_DIR = "app/templates"


def generate_summary(trip: Trip, items: list[TripItem]) -> str:
    """Generate a plain-text itinerary summary for chat."""
    finalized = [i for i in items if i.stage == Stage.FINALIZED]
    planning = [i for i in items if i.stage == Stage.PLANNING]

    if not finalized and not planning:
        return (
            f"📋 {trip.name}\n\n"
            "No finalized or planned items yet. Move items to 'planning' or 'finalized' "
            "to build the itinerary."
        )

    lines = [f"📋 {trip.name} — Itinerary Summary\n"]

    # Finalized items (confirmed)
    if finalized:
        lines.append("✅ Confirmed")
        by_category: dict[str, list[TripItem]] = {}
        for item in finalized:
            by_category.setdefault(item.category, []).append(item)

        for category, cat_items in by_category.items():
            lines.append(f"\n{_category_emoji(category)} {category.title()}")
            for item in cat_items:
                lines.append(_format_item(item))

    # Planning items (not yet booked)
    if planning:
        if finalized:
            lines.append("")
        lines.append("📝 Planned (not yet booked)")
        by_category_p: dict[str, list[TripItem]] = {}
        for item in planning:
            by_category_p.setdefault(item.category, []).append(item)

        for category, cat_items in by_category_p.items():
            lines.append(f"\n{_category_emoji(category)} {category.title()}")
            for item in cat_items:
                lines.append(_format_item(item))

    return "\n".join(lines)


def _format_item(item: TripItem) -> str:
    """Format a single trip item for the summary."""
    line = f"  • {item.title}"
    if item.details.dates:
        start = item.details.dates.get("start", "")
        end = item.details.dates.get("end", "")
        if start and end:
            line += f" ({start} → {end})"
        elif start:
            line += f" ({start})"
    if item.details.booking and item.details.booking.confirmation_number:
        line += f" [Conf: {item.details.booking.confirmation_number}]"
    if item.details.booking and item.details.booking.address:
        line += f"\n    📍 {item.details.booking.address}"
    result = line
    if item.details.notes:
        result += f"\n    {item.details.notes}"
    return result


async def generate_pdf_url(
    credential: DefaultAzureCredential,
    settings: Settings,
    trip: Trip,
    items: list[TripItem],
) -> str:
    """Generate a PDF itinerary and return a SAS URL."""
    finalized = [i for i in items if i.stage == Stage.FINALIZED]

    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("itinerary.html")
    html_content = template.render(trip=trip, items=finalized, generated_at=datetime.now(UTC))

    # Import weasyprint only when needed (heavy dependency)
    from weasyprint import HTML

    pdf_bytes = HTML(string=html_content).write_pdf()

    # Upload to Azure Blob Storage
    now = datetime.now(UTC)
    blob_name = f"{trip.group_id}/{trip.id}/itinerary-{now.strftime('%Y%m%d-%H%M%S')}.pdf"
    blob_url = f"https://{settings.storage_account_name}.blob.core.windows.net"

    blob_service = BlobServiceClient(blob_url, credential=credential)
    try:
        container_client = blob_service.get_container_client(settings.storage_container_name)
        blob_client = container_client.get_blob_client(blob_name)
        await blob_client.upload_blob(
            io.BytesIO(pdf_bytes),
            overwrite=True,
            content_settings=ContentSettings(content_type="application/pdf"),
        )

        # Generate a 7-day read-only SAS URL using user delegation key
        expiry_time = now + timedelta(days=7)
        udk = await blob_service.get_user_delegation_key(
            key_start_time=now,
            key_expiry_time=expiry_time,
        )
        sas_token = generate_blob_sas(
            account_name=settings.storage_account_name,
            container_name=settings.storage_container_name,
            blob_name=blob_name,
            user_delegation_key=udk,
            permission=BlobSasPermissions(read=True),
            expiry=expiry_time,
        )
        return f"{blob_client.url}?{sas_token}"
    finally:
        await blob_service.close()


def _category_emoji(category: str) -> str:
    return {
        "lodging": "🏨",
        "transport": "✈️",
        "activity": "🎯",
        "dining": "🍽️",
        "other": "📌",
    }.get(category, "📌")
