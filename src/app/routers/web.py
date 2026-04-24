"""Web routes for viewing trip documents as rendered HTML pages."""

from __future__ import annotations

import logging
import secrets

import markdown
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.services import storage

logger = logging.getLogger(__name__)
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

AUTH_COOKIE_NAME = "sensei_access"
AUTH_COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days

# Tabs in display order: label → filename
TABS = [
    ("Overview", "trip.md"),
    ("Brainstorming", "brainstorming.md"),
    ("Planning", "planning.md"),
    ("Itinerary", "itinerary.md"),
]

CSS = """\
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
  background:#f5f5f5;color:#1a1a1a;line-height:1.6}
.header{background:linear-gradient(135deg,#1e3a5f,#2d6a9f);color:#fff;padding:1.5rem 2rem}
.header h1{font-size:1.5rem;font-weight:600}
.header .subtitle{opacity:0.85;font-size:0.9rem;margin-top:0.25rem}
.tabs{display:flex;gap:0;background:#fff;
  border-bottom:2px solid #e0e0e0;padding:0 1rem;overflow-x:auto}
.tab{padding:0.75rem 1.25rem;cursor:pointer;border-bottom:3px solid transparent;font-size:0.9rem;
  color:#555;text-decoration:none;white-space:nowrap;transition:all 0.2s}
.tab:hover{color:#1e3a5f;background:#f0f4f8}
.tab.active{color:#1e3a5f;border-bottom-color:#2d6a9f;font-weight:600}
.content{max-width:900px;margin:1.5rem auto;padding:0 1.5rem}
.card{background:#fff;border-radius:8px;
  box-shadow:0 1px 3px rgba(0,0,0,0.1);padding:2rem;display:none}
.card.active{display:block}
.card h1{font-size:1.4rem;margin-bottom:1rem;color:#1e3a5f;
  border-bottom:1px solid #e8e8e8;padding-bottom:0.5rem}
.card h2{font-size:1.15rem;margin:1.5rem 0 0.5rem;color:#2d6a9f}
.card h3{font-size:1rem;margin:1rem 0 0.5rem}
.card ul,.card ol{padding-left:1.5rem;margin:0.5rem 0}
.card li{margin:0.3rem 0}
.card p{margin:0.5rem 0}
.card strong{color:#1a1a1a}
.card em{color:#666}
.card code{background:#f0f4f8;padding:0.15rem 0.4rem;border-radius:3px;font-size:0.85em}
.card blockquote{border-left:3px solid #2d6a9f;padding-left:1rem;margin:0.75rem 0;color:#555}
.empty{text-align:center;padding:3rem;color:#999}
.back{display:inline-block;margin:1rem 0;color:#2d6a9f;text-decoration:none;font-size:0.9rem}
.back:hover{text-decoration:underline}
.group-list{max-width:600px;margin:2rem auto;padding:0 1.5rem}
.group-list a{display:block;padding:1rem 1.25rem;background:#fff;border-radius:8px;
  margin-bottom:0.75rem;box-shadow:0 1px 3px rgba(0,0,0,0.1);text-decoration:none;color:#1e3a5f;
  font-weight:500;transition:box-shadow 0.2s}
.group-list a:hover{box-shadow:0 2px 8px rgba(0,0,0,0.15)}
.group-list .trip-name{font-size:0.85rem;color:#666;font-weight:400}
footer{text-align:center;padding:2rem;color:#999;font-size:0.8rem}
"""

TAB_JS = """\
document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', e => {
    e.preventDefault();
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.card').forEach(c => c.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById(tab.dataset.target).classList.add('active');
  });
});
"""

md = markdown.Markdown(extensions=["tables", "fenced_code", "nl2br"])


def _check_web_auth(request: Request) -> Response | None:
    """Return an error response if auth fails, or None if auth passes."""
    access_key = request.app.state.settings.web_access_key
    if not access_key:
        return None  # auth disabled

    # Check query param first — allows setting the cookie
    key_param = request.query_params.get("key", "")
    if key_param and secrets.compare_digest(key_param, access_key):
        # Redirect to strip key from URL and set cookie
        clean_url = str(request.url).split("?")[0]
        response = RedirectResponse(url=clean_url, status_code=302)
        response.set_cookie(
            AUTH_COOKIE_NAME,
            access_key,
            max_age=AUTH_COOKIE_MAX_AGE,
            httponly=True,
            samesite="lax",
            secure=True,
        )
        return response

    # Check cookie
    cookie_val = request.cookies.get(AUTH_COOKIE_NAME, "")
    if cookie_val and secrets.compare_digest(cookie_val, access_key):
        return None  # authorized

    return HTMLResponse(
        "<h1>403 Forbidden</h1><p>Access denied. Append ?key=YOUR_KEY to the URL.</p>",
        status_code=403,
    )


def _render_page(title: str, subtitle: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} — Sensei Travel</title>
<style>{CSS}</style>
</head><body>
<div class="header"><h1>🗺️ {title}</h1><div class="subtitle">{subtitle}</div></div>
{body}
<footer>Sensei Travel Bot</footer>
</body></html>"""


@router.get("/trips", response_class=HTMLResponse)
@limiter.limit("60/minute")
async def list_trips(request: Request):
    """List all groups that have an active trip."""
    auth_response = _check_web_auth(request)
    if auth_response is not None:
        return auth_response

    container = request.app.state.blob_container
    groups: list[dict] = []

    # Scan for active_trip.json files
    async for blob in container.list_blobs(name_starts_with="trips/"):
        if blob.name.endswith("/active_trip.json"):
            parts = blob.name.split("/")
            if len(parts) >= 3:
                group_id = parts[1]
                try:
                    client = container.get_blob_client(blob.name)
                    data = await client.download_blob()
                    import json

                    info = json.loads(await data.readall())
                    groups.append({"group_id": group_id, "trip_name": info.get("trip_name", "")})
                except Exception:
                    groups.append({"group_id": group_id, "trip_name": ""})

    if not groups:
        body = '<div class="empty">No active trips found.</div>'
    else:
        links = ""
        for g in sorted(groups, key=lambda x: x["trip_name"]):
            label = g["trip_name"] or g["group_id"]
            links += (
                f'<a href="/trips/{g["group_id"]}">{label}'
                f'<div class="trip-name">Group: {g["group_id"]}</div></a>'
            )
        body = f'<div class="group-list">{links}</div>'

    return _render_page("Active Trips", "Select a trip to view details", body)


@router.get("/trips/{group_id}", response_class=HTMLResponse)
@limiter.limit("60/minute")
async def view_trip(group_id: str, request: Request):
    """Render the active trip's markdown documents as a tabbed HTML page."""
    auth_response = _check_web_auth(request)
    if auth_response is not None:
        return auth_response

    container = request.app.state.blob_container

    active = await storage.get_active_trip(container, group_id)
    if not active:
        body = (
            '<div class="content"><div class="empty">'
            "No active trip found for this group."
            "</div></div>"
            '<div class="content"><a class="back" href="/trips">← Back to all trips</a></div>'
        )
        return HTMLResponse(_render_page("Trip Not Found", group_id, body), status_code=404)

    trip_id = active["trip_id"]
    trip_name = active.get("trip_name", "Trip")

    files = await storage.read_trip_files(container, group_id, trip_id)

    # Build tabs and cards
    tab_html = ""
    card_html = ""
    for i, (label, filename) in enumerate(TABS):
        active_cls = " active" if i == 0 else ""
        tab_id = filename.replace(".md", "")
        tab_html += f'<a class="tab{active_cls}" href="#" data-target="{tab_id}">{label}</a>'

        md.reset()
        content = files.get(filename, "")
        rendered = md.convert(content) if content else "<p><em>No content yet.</em></p>"
        card_html += f'<div id="{tab_id}" class="card{active_cls}">{rendered}</div>'

    body = f"""
<div class="tabs">{tab_html}</div>
<div class="content">
  {card_html}
  <a class="back" href="/trips">← Back to all trips</a>
</div>
<script>{TAB_JS}</script>"""

    return _render_page(trip_name, f"Group: {group_id}", body)
