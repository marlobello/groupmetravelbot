"""Tests for LLM response parsing."""

from __future__ import annotations

import json

from app.services.llm import _parse_response


class TestParseResponse:
    def test_valid_message_only(self):
        raw = json.dumps({"message": "Hello there!"})
        result = _parse_response(raw)
        assert result["message"] == "Hello there!"
        assert "file_updates" not in result

    def test_valid_with_file_updates(self):
        raw = json.dumps(
            {
                "message": "Updated brainstorming!",
                "file_updates": {
                    "brainstorming.md": "# Ideas\n- Colosseum",
                    "trip.md": None,
                    "planning.md": None,
                    "itinerary.md": None,
                },
            }
        )
        result = _parse_response(raw)
        assert result["message"] == "Updated brainstorming!"
        assert result["file_updates"] == {"brainstorming.md": "# Ideas\n- Colosseum"}

    def test_all_null_file_updates_excluded(self):
        raw = json.dumps(
            {
                "message": "No changes needed.",
                "file_updates": {
                    "brainstorming.md": None,
                    "trip.md": None,
                    "planning.md": None,
                    "itinerary.md": None,
                },
            }
        )
        result = _parse_response(raw)
        assert "file_updates" not in result

    def test_new_trip(self):
        raw = json.dumps({"message": "Let's go!", "new_trip": "Rome 2025"})
        result = _parse_response(raw)
        assert result["new_trip"] == "Rome 2025"
        assert "file_updates" not in result  # new_trip returns early

    def test_archive_trip(self):
        raw = json.dumps({"message": "Archived!", "archive_trip": True})
        result = _parse_response(raw)
        assert result["archive_trip"] is True

    def test_unknown_filename_rejected(self):
        raw = json.dumps(
            {
                "message": "ok",
                "file_updates": {
                    "brainstorming.md": "# Ideas",
                    "evil.md": "hacked!",
                    "../../etc/passwd": "root",
                },
            }
        )
        result = _parse_response(raw)
        assert result["file_updates"] == {"brainstorming.md": "# Ideas"}

    def test_invalid_json_returns_raw_text(self):
        result = _parse_response("This is not JSON at all")
        assert result["message"] == "This is not JSON at all"
        assert "file_updates" not in result

    def test_empty_string(self):
        result = _parse_response("")
        assert "trouble" in result["message"].lower()

    def test_none_input(self):
        result = _parse_response(None)
        assert "trouble" in result["message"].lower()

    def test_non_dict_json(self):
        result = _parse_response(json.dumps(["a", "list"]))
        assert isinstance(result["message"], str)

    def test_missing_message_key(self):
        raw = json.dumps({"file_updates": {"trip.md": "# Trip"}})
        result = _parse_response(raw)
        assert result["message"] == ""
        assert result["file_updates"] == {"trip.md": "# Trip"}

    def test_multiple_file_updates(self):
        raw = json.dumps(
            {
                "message": "Updated both!",
                "file_updates": {
                    "brainstorming.md": "# Brain",
                    "planning.md": "# Plan",
                    "trip.md": None,
                    "itinerary.md": None,
                },
            }
        )
        result = _parse_response(raw)
        assert len(result["file_updates"]) == 2
        assert "brainstorming.md" in result["file_updates"]
        assert "planning.md" in result["file_updates"]

    def test_oversized_file_update_truncated(self):
        """File updates exceeding MAX_FILE_UPDATE_BYTES are truncated."""
        huge_content = "x" * (600 * 1024)  # 600 KB
        raw = json.dumps(
            {
                "message": "Big update",
                "file_updates": {"brainstorming.md": huge_content},
            }
        )
        result = _parse_response(raw)
        assert "brainstorming.md" in result["file_updates"]
        assert len(result["file_updates"]["brainstorming.md"]) < len(huge_content)
