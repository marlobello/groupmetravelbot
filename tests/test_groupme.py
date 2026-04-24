from __future__ import annotations

from app.services.groupme import _split_message


class TestSplitMessage:
    def test_short_message_no_split(self):
        result = _split_message("Hello world", 1000)
        assert result == ["Hello world"]

    def test_exact_length(self):
        text = "a" * 1000
        result = _split_message(text, 1000)
        assert result == [text]

    def test_split_at_newline(self):
        text = "Line 1\nLine 2\nLine 3"
        result = _split_message(text, 14)
        assert len(result) == 2
        assert result[0] == "Line 1\nLine 2"
        assert result[1] == "Line 3"

    def test_split_at_space(self):
        text = "word1 word2 word3"
        result = _split_message(text, 12)
        assert len(result) == 2
        assert result[0] == "word1 word2"
        assert result[1] == "word3"

    def test_split_long_word(self):
        text = "a" * 20
        result = _split_message(text, 10)
        assert len(result) == 2
        assert result[0] == "a" * 10
        assert result[1] == "a" * 10

    def test_empty_message(self):
        result = _split_message("", 1000)
        assert result == [""]

    def test_multiple_splits(self):
        text = "a" * 30
        result = _split_message(text, 10)
        assert len(result) == 3
        for chunk in result:
            assert len(chunk) == 10

    def test_prefers_newline_over_space(self):
        text = "Hello world\nSecond line here"
        result = _split_message(text, 20)
        assert result[0] == "Hello world"
        assert result[1] == "Second line here"
