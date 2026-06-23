"""Tests for the agent framework integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent import get_agent_response


@pytest.fixture(autouse=True)
def _clear_client_cache():
    """Ensure the module-level client cache doesn't leak between tests."""
    from app.services import agent

    agent._client_cache.clear()
    yield
    agent._client_cache.clear()


@pytest.fixture
def mock_credential():
    cred = AsyncMock()
    token = MagicMock()
    token.token = "fake-token"
    cred.get_token = AsyncMock(return_value=token)
    return cred


@pytest.fixture
def mock_settings():
    s = MagicMock()
    s.azure_openai_endpoint = "https://fake.openai.azure.com/"
    s.azure_openai_deployment = "gpt-4.1"
    s.foundry_project_endpoint = "https://sensei-resource.services.ai.azure.com/api/projects/sensei"
    s.enable_web_search = False
    return s


@pytest.fixture
def trip_files():
    return {
        "trip.md": "# Rome 2025\nDates: June 1-8",
        "brainstorming.md": "- Visit Colosseum",
        "planning.md": "",
        "itinerary.md": "",
    }


class TestGetAgentResponse:
    """Test the get_agent_response function."""

    @pytest.mark.asyncio
    @patch("app.services.agent.FoundryChatClient")
    async def test_basic_response(
        self, mock_client_cls, mock_credential, mock_settings, trip_files
    ):
        """Agent returns a chat message."""
        mock_result = MagicMock()
        mock_result.text = "Rome is amazing! Let me help you plan."

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=mock_result)

        mock_client = MagicMock()
        mock_client.as_agent = MagicMock(return_value=mock_agent)
        mock_client_cls.return_value = mock_client

        result = await get_agent_response(
            credential=mock_credential,
            settings=mock_settings,
            user_message="What should we do in Rome?",
            user_name="Alice",
            trip_files=trip_files,
        )

        assert result["message"] == "Rome is amazing! Let me help you plan."
        mock_agent.run.assert_called_once()
        # Verify the input includes user name
        call_args = mock_agent.run.call_args[0][0]
        assert "Alice" in call_args
        assert "What should we do in Rome?" in call_args

    @pytest.mark.asyncio
    @patch("app.services.agent.FoundryChatClient")
    async def test_no_trip_uses_no_trip_prompt(
        self, mock_client_cls, mock_credential, mock_settings
    ):
        """When no trip files, uses the no-trip prompt."""
        mock_result = MagicMock()
        mock_result.text = "Hey! Want to start planning a trip?"

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=mock_result)

        mock_client = MagicMock()
        mock_client.as_agent = MagicMock(return_value=mock_agent)
        mock_client_cls.return_value = mock_client

        result = await get_agent_response(
            credential=mock_credential,
            settings=mock_settings,
            user_message="Hello!",
            user_name="Bob",
            trip_files=None,
        )

        assert result["message"] == "Hey! Want to start planning a trip?"
        # Verify no-trip instructions were used
        agent_kwargs = mock_client.as_agent.call_args[1]
        assert "no active trip" in agent_kwargs["instructions"]

    @pytest.mark.asyncio
    @patch("app.services.agent.FoundryChatClient")
    async def test_session_used_with_group_id(
        self, mock_client_cls, mock_credential, mock_settings, trip_files
    ):
        """When blob_container and group_id provided, a session is used."""
        mock_result = MagicMock()
        mock_result.text = "Great idea!"

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=mock_result)
        mock_session = MagicMock()
        mock_agent.create_session = MagicMock(return_value=mock_session)

        mock_client = MagicMock()
        mock_client.as_agent = MagicMock(return_value=mock_agent)
        mock_client_cls.return_value = mock_client

        mock_container = MagicMock()

        await get_agent_response(
            credential=mock_credential,
            settings=mock_settings,
            user_message="What about Naples?",
            user_name="Alice",
            trip_files=trip_files,
            blob_container=mock_container,
            group_id="g1",
            trip_id="t1",
        )

        # Session is created with group_id
        mock_agent.create_session.assert_called_once_with(session_id="g1")
        # Agent.run is called with session
        run_kwargs = mock_agent.run.call_args[1]
        assert run_kwargs["session"] == mock_session

    @pytest.mark.asyncio
    @patch("app.services.agent.FoundryChatClient")
    async def test_tools_provided_with_blob_container(
        self, mock_client_cls, mock_credential, mock_settings, trip_files
    ):
        """When blob_container is provided, tools are registered."""
        mock_result = MagicMock()
        mock_result.text = "Done!"

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=mock_result)

        mock_client = MagicMock()
        mock_client.as_agent = MagicMock(return_value=mock_agent)
        mock_client_cls.return_value = mock_client

        mock_container = AsyncMock()

        await get_agent_response(
            credential=mock_credential,
            settings=mock_settings,
            user_message="Add hotel to planning",
            user_name="Alice",
            trip_files=trip_files,
            blob_container=mock_container,
            group_id="g1",
            trip_id="t1",
        )

        # Verify the 3 function tools were passed to as_agent (web search disabled here)
        agent_kwargs = mock_client.as_agent.call_args[1]
        assert agent_kwargs["tools"] is not None
        assert len(agent_kwargs["tools"]) == 3

    @pytest.mark.asyncio
    @patch("app.services.agent.FoundryChatClient")
    async def test_web_search_tool_added_when_enabled(
        self, mock_client_cls, mock_credential, mock_settings, trip_files
    ):
        """With web search enabled, the hosted Web Search tool is registered first."""
        mock_settings.enable_web_search = True

        mock_result = MagicMock()
        mock_result.text = "Here's a current option."

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=mock_result)

        mock_client = MagicMock()
        mock_client.as_agent = MagicMock(return_value=mock_agent)
        mock_client_cls.return_value = mock_client
        web_tool = MagicMock(name="web_search_tool")
        mock_client_cls.get_web_search_tool = MagicMock(return_value=web_tool)

        mock_container = AsyncMock()

        await get_agent_response(
            credential=mock_credential,
            settings=mock_settings,
            user_message="What's the weather in Lisbon right now?",
            user_name="Alice",
            trip_files=trip_files,
            blob_container=mock_container,
            group_id="g1",
            trip_id="t1",
        )

        mock_client_cls.get_web_search_tool.assert_called_once()
        tools = mock_client.as_agent.call_args[1]["tools"]
        # web search tool + 3 function tools
        assert len(tools) == 4
        assert tools[0] is web_tool

    @pytest.mark.asyncio
    @patch("app.services.agent.FoundryChatClient")
    async def test_error_returns_fallback_message(
        self, mock_client_cls, mock_credential, mock_settings, trip_files
    ):
        """When agent raises an exception, returns a friendly fallback."""
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(side_effect=RuntimeError("API error"))

        mock_client = MagicMock()
        mock_client.as_agent = MagicMock(return_value=mock_agent)
        mock_client_cls.return_value = mock_client

        result = await get_agent_response(
            credential=mock_credential,
            settings=mock_settings,
            user_message="Hello",
            user_name="Alice",
            trip_files=trip_files,
        )

        assert "try again" in result["message"].lower()

    @pytest.mark.asyncio
    @patch("app.services.agent.FoundryChatClient")
    async def test_rate_limit_returns_friendly_message(
        self, mock_client_cls, mock_credential, mock_settings, trip_files
    ):
        """A 429/rate-limit error returns a distinct, friendly message."""

        class RateLimitError(Exception):
            status_code = 429

        wrapped = RuntimeError("service failed")
        wrapped.__cause__ = RateLimitError("Too Many Requests")

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(side_effect=wrapped)

        mock_client = MagicMock()
        mock_client.as_agent = MagicMock(return_value=mock_agent)
        mock_client_cls.return_value = mock_client

        result = await get_agent_response(
            credential=mock_credential,
            settings=mock_settings,
            user_message="Hello",
            user_name="Alice",
            trip_files=trip_files,
        )

        assert "rate limit" in result["message"].lower()
