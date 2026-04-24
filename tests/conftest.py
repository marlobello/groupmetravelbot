from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


@pytest.fixture
def sample_trip_files():
    return {
        "trip.md": "# Rome 2025\n\n**Status:** Active\n\n## Details\n\nJune 15-20, 2025\n",
        "brainstorming.md": "# Rome 2025 — Brainstorming\n\n- Colosseum tour\n- Try Roman pizza\n",
        "planning.md": (
            "# Rome 2025 — Planning\n\n## Activities\n- Colosseum: open 8:30am-7pm, €16\n"
        ),
        "itinerary.md": "# Rome 2025 — Itinerary\n\n_No confirmed plans yet._\n",
    }


@pytest.fixture
def mock_blob_container():
    return AsyncMock()
