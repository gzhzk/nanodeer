"""Tests for TitleMiddleware — focuses on state.title read/write."""
import pytest
from unittest.mock import MagicMock, AsyncMock

from nanodeer.agent.middlewares.title import TitleMiddleware
from nanodeer.agent.state import ThreadState, TurnSignals
from nanodeer.agent.messages import AIMessage, HumanMessage


LONG_USER_MESSAGE = (
    "I need help setting up a complete Python project from scratch. The project should use FastAPI as the web framework, "
    "PostgreSQL as the primary database with SQLAlchemy ORM for data modeling, Redis for caching and session management, "
    "Docker and Docker Compose for containerization and local development environment, "
    "GitHub Actions for continuous integration and deployment, "
    "pytest and pytest-asyncio for unit and integration testing with coverage reports, "
    "Pydantic for request/response validation and settings management, "
    "JWT authentication with refresh tokens for secure API access, "
    " Alembic for database migrations, "
    "and proper logging configuration with structlog. "
    "Please also set up the project structure following best practices with separate modules for api, core, models, schemas, services, and tests."
)

LONG_GIT_MESSAGE = (
    "Please analyze our company's large-scale Git repository to understand overall codebase health, "
    "commit frequency patterns over the past 6 months, contributor activity and distribution across teams, "
    "average code review turnaround time and merge latency metrics, "
    "branching strategy effectiveness and feature flag usage patterns, "
    "identification of technical debt hotspots through git history analysis, "
    "patterns in commit message quality and adherence to conventional commits specification, "
    "frequency and causes of merge conflicts, "
    "CI/CD pipeline execution times and bottleneck identification, "
    "and recommendations for improving overall development workflow efficiency based on the data."
)


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    response = MagicMock()
    response.content = "Setup FastAPI project with Docker and PostgreSQL"
    llm.ainvoke = AsyncMock(return_value=response)
    return llm


@pytest.fixture
def middleware(mock_llm):
    return TitleMiddleware(llm=mock_llm)


@pytest.fixture
def signals():
    return TurnSignals()


class TestTitleMiddleware:
    async def test_generates_title_from_long_first_message(self, middleware, mock_llm):
        """Sets state.title from first HumanMessage content even with very long messages."""
        state = ThreadState()
        state.messages = [
            HumanMessage(content=LONG_USER_MESSAGE),
        ]

        await middleware.after_llm(state, TurnSignals())

        assert state.title is not None
        assert state.title == "Setup FastAPI project with Docker and PostgreSQL"
        mock_llm.ainvoke.assert_called_once()

    async def test_skips_if_title_already_set(self, middleware, mock_llm):
        """Does not regenerate if title already exists."""
        state = ThreadState()
        state.title = "Existing title for this conversation about project setup"
        state.messages = [
            HumanMessage(content=LONG_USER_MESSAGE),
        ]

        await middleware.after_llm(state, TurnSignals())

        mock_llm.ainvoke.assert_not_called()
        assert state.title == "Existing title for this conversation about project setup"

    async def test_no_llm_noop(self):
        """No LLM → no-op, title remains None."""
        mw = TitleMiddleware(llm=None)
        state = ThreadState()
        state.messages = [HumanMessage(content=LONG_USER_MESSAGE)]

        await mw.after_llm(state, TurnSignals())

        assert state.title is None

    async def test_no_human_message_noop(self, middleware, mock_llm):
        """No HumanMessage → no-op."""
        state = ThreadState()
        state.messages = [
            AIMessage(content="Hello! I'll help you set up your project. This is a detailed explanation of what we will accomplish together."),
        ]

        await middleware.after_llm(state, TurnSignals())

        mock_llm.ainvoke.assert_not_called()

    async def test_truncates_to_max_length(self, middleware, mock_llm):
        """Title truncated to max_length (default 50)."""
        response = MagicMock()
        response.content = "A" * 100  # 100 chars, way over limit
        mock_llm.ainvoke = AsyncMock(return_value=response)

        mw = TitleMiddleware(llm=mock_llm, max_length=50)
        state = ThreadState()
        state.messages = [HumanMessage(content=LONG_USER_MESSAGE)]

        await mw.after_llm(state, TurnSignals())

        assert len(state.title) <= 50

    async def test_fallback_on_llm_error(self):
        """LLM error → fallback to truncated user message."""
        llm = MagicMock()
        llm.ainvoke = AsyncMock(side_effect=Exception("LLM error"))

        mw = TitleMiddleware(llm=llm, max_length=50)
        state = ThreadState()
        state.messages = [HumanMessage(content=LONG_USER_MESSAGE)]

        await mw.after_llm(state, TurnSignals())

        assert state.title is not None
        assert len(state.title) <= 50

    async def test_finds_human_message_regardless_of_position(self, middleware, mock_llm):
        """HumanMessage may not be first in messages list."""
        response = MagicMock()
        response.content = "Git repository analysis and recommendations"
        mock_llm.ainvoke = AsyncMock(return_value=response)

        state = ThreadState()
        state.messages = [
            AIMessage(content="Hello! I'll help you analyze the codebase. This is a comprehensive analysis that will cover many aspects."),
            HumanMessage(content=LONG_GIT_MESSAGE),
            AIMessage(content="I'll analyze the repository now using multiple metrics and provide detailed recommendations."),
        ]

        await middleware.after_llm(state, TurnSignals())

        assert state.title == "Git repository analysis and recommendations"

    async def test_custom_max_length(self):
        """Custom max_length is respected."""
        llm = MagicMock()
        response = MagicMock()
        response.content = "A" * 100
        llm.ainvoke = AsyncMock(return_value=response)

        mw = TitleMiddleware(llm=llm, max_length=30)
        state = ThreadState()
        state.messages = [HumanMessage(content=LONG_USER_MESSAGE)]

        await mw.after_llm(state, TurnSignals())

        assert len(state.title) <= 30

    async def test_git_repository_analysis_title(self, mock_llm):
        """Tests title generation for git repository analysis scenario."""
        response = MagicMock()
        response.content = "Git repository health and workflow analysis"
        mock_llm.ainvoke = AsyncMock(return_value=response)

        mw = TitleMiddleware(llm=mock_llm, max_length=50)
        state = ThreadState()
        state.messages = [HumanMessage(content=LONG_GIT_MESSAGE)]

        await mw.after_llm(state, TurnSignals())

        assert state.title == "Git repository health and workflow analysis"
        assert len(state.title) <= 50
