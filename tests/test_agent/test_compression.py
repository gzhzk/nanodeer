"""Tests for CompressionMiddleware — focuses on message compression logic."""
import pytest
from unittest.mock import MagicMock

from nanodeer.agent.compression import CompressionMiddleware
from nanodeer.agent.messages import AIMessage, HumanMessage, SystemMessage


LONG_USER_MESSAGE = """I need help setting up a comprehensive Python web application. The project should use FastAPI as the web framework because it offers excellent performance and automatic OpenAPI documentation generation. For the database layer, we need PostgreSQL with SQLAlchemy ORM for type-safe database operations and Pydantic for request/response validation. The application should support user authentication using JWT tokens with refresh token rotation for enhanced security. We also need Redis for caching frequently accessed data and managing user sessions efficiently. Please set up Docker and Docker Compose configuration for containerized development and production deployment. The project structure should follow clean architecture principles with separate modules for api endpoints, business logic services, data models and schemas, and comprehensive test suites using pytest and pytest-asyncio. Include proper logging configuration using structlog for structured JSON logging that can be easily parsed by log aggregation tools. Set up Alembic for database migrations and include GitHub Actions workflows for continuous integration that run tests, linting, and security scans on every pull request."""

LONG_AI_MESSAGE = """I'll help you set up this comprehensive Python web application. Let me break down the implementation plan:

First, I'll create the project structure with separate modules for api, core, models, schemas, services, and tests directories following clean architecture principles.

For the FastAPI setup, I'll configure the application with proper CORS middleware, rate limiting, and structured logging using structlog for JSON formatted logs that can be easily aggregated.

The PostgreSQL database layer will use SQLAlchemy 2.0 with async support for efficient database operations. I'll set up Pydantic v2 models for request validation and response serialization with automatic OpenAPI schema generation.

For authentication, I'll implement JWT access tokens with a 15-minute expiry and refresh tokens with 7-day expiry, stored securely in Redis for session management. The refresh token rotation ensures that stolen tokens can be detected and invalidated.

Docker Compose configuration will include services for the FastAPI application, PostgreSQL database, Redis cache, and nginx reverse proxy for production deployments.

Alembic migrations will be configured for incremental database schema changes with proper versioning strategy.

GitHub Actions workflows will run pytest with coverage reports, flake8 and black for code formatting, and safety and bandit for security scanning on every pull request before merging."""

LONG_USER_MESSAGE_2 = """Now let's add the user management module with role-based access control. I need to implement user registration with email verification, password reset functionality using secure token-based URLs, and user profile management with avatar upload support. The roles should include admin, moderator, and regular user with different permission levels. Add OAuth2 integration for Google and GitHub login options as well."""

LONG_AI_MESSAGE_2 = """I'll implement the complete user management system with role-based access control. The registration flow will include email verification using secure one-time tokens sent via email with 24-hour expiry. Password reset will use cryptographically secure tokens that are hashed before storage. User profiles will support avatar uploads stored in S3-compatible storage with automatic image resizing for thumbnails.

The RBAC system will define permissions at the resource level: users can read public content, moderators can edit and delete flagged content, and admins have full system access. I'll implement middleware for permission checking on protected routes.

OAuth2 integration will use the authlib library for Google and GitHub OAuth flows with proper state parameter validation to prevent CSRF attacks. Access tokens will be stored securely and refreshed automatically."""

LONG_USER_MESSAGE_3 = """Let's implement the API endpoints for content management. The content types include articles, comments, and reactions. Articles should support markdown content with syntax highlighting for code blocks, featured images, and tags for categorization. Comments support nested replies up to 3 levels deep. Reactions include like, bookmark, and share functionality. Add pagination for all list endpoints with cursor-based pagination for better performance on large datasets."""

LONG_AI_MESSAGE_3 = """I'll create the complete content management API. Articles will use markdown with frontmatter for metadata, stored in PostgreSQL with full-text search using tsvector columns for efficient content searching. Comments use a nested set model or materialized path for hierarchical data with efficient subtree queries limited to 3 levels. Reactions will be stored in a separate table with composite indexes for efficient aggregation queries counting reactions by type.

Cursor-based pagination will use the created_at timestamp and id for stable ordering even when new content is added during pagination. The API responses will follow consistent envelope format with metadata for pagination state including has_more and cursor for next page retrieval."""


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    response = MagicMock()
    response.content = "User set up FastAPI project with PostgreSQL, Docker, JWT auth, Redis caching, and comprehensive CI/CD pipeline."
    llm.get_num_tokens_from_messages.return_value = 100
    llm.invoke.return_value = response
    return llm


class TestCompressionMiddleware:
    def test_no_compression_below_threshold(self, mock_llm):
        """No compression when tokens below threshold."""
        mock_llm.get_num_tokens_from_messages.return_value = 1000

        mw = CompressionMiddleware(llm=mock_llm, context_window=200000, compression_ratio=0.7)
        mw._threshold = 140000

        messages = [
            HumanMessage(content="Hello"),
            AIMessage(content="Hi!"),
        ]

        result = mw.compress(messages)

        assert result is None

    def test_compression_triggers_above_threshold(self, mock_llm):
        """Compression triggers when tokens exceed threshold."""
        # Override the default 100 return value
        mock_llm.get_num_tokens_from_messages.return_value = 150000

        mw = CompressionMiddleware(llm=mock_llm, context_window=200000, compression_ratio=0.7, keep_recent=1)
        # threshold = 200000 * 0.7 = 140000
        # keep_recent=1 so messages[:-1] has content to summarize

        messages = [
            HumanMessage(content="Hello this is a test message"),
            AIMessage(content="Hi this is a response message"),
        ]

        result = mw.compress(messages)

        # With 150000 tokens > threshold 140000, compression should trigger
        assert result is not None

    def test_keeps_recent_messages(self, mock_llm):
        """Always keeps last N messages after the summary."""
        mock_llm.get_num_tokens_from_messages.return_value = 200000

        mw = CompressionMiddleware(llm=mock_llm, keep_recent=3)

        # Create messages with distinct content
        messages = [
            HumanMessage(content="First message content that will be summarized"),
            HumanMessage(content="Second message content that will be summarized"),
            HumanMessage(content="Third message that will be summarized away"),
            HumanMessage(content="Fourth recent message that should be preserved"),
            HumanMessage(content="Fifth recent message that should be preserved"),
        ]

        result = mw.compress(messages)

        assert result is not None
        # Result is [SystemMessage(summary), msg4, msg5]
        # Last 3 items are [summary, msg4, msg5]
        recent = result[-3:]
        assert len(recent) == 3
        # The last 2 (not including summary) should be the preserved messages
        recent_texts = [m.content for m in recent[-2:]]
        assert "Fourth recent message" in recent_texts[0]
        assert "Fifth recent message" in recent_texts[1]

    def test_summarizes_older_messages_with_long_content(self, mock_llm):
        """Older messages with substantial content get summarized."""
        mock_llm.get_num_tokens_from_messages.return_value = 200000

        mw = CompressionMiddleware(llm=mock_llm, keep_recent=2)

        messages = [
            HumanMessage(content=LONG_USER_MESSAGE),
            AIMessage(content=LONG_AI_MESSAGE),
            HumanMessage(content=LONG_USER_MESSAGE_2),
            AIMessage(content=LONG_AI_MESSAGE_2),
            HumanMessage(content=LONG_USER_MESSAGE_3),
            AIMessage(content=LONG_AI_MESSAGE_3),
        ]

        result = mw.compress(messages)

        assert result is not None
        assert isinstance(result[0], SystemMessage)
        assert "[Earlier conversation summarized:" in result[0].content
        # Original long content should not appear in full
        assert LONG_USER_MESSAGE[:50] not in result[0].content

    def test_compression_preserves_recent_long_messages(self, mock_llm):
        """Recent messages with substantial content are preserved."""
        mock_llm.get_num_tokens_from_messages.return_value = 200000

        mw = CompressionMiddleware(llm=mock_llm, keep_recent=2)

        messages = [
            HumanMessage(content="Old message that should be summarized away"),
            AIMessage(content="Another old message"),
            HumanMessage(content=LONG_USER_MESSAGE_3),
            AIMessage(content=LONG_AI_MESSAGE_3),
        ]

        result = mw.compress(messages)

        assert result is not None
        # Recent long messages should be preserved (not in summarized form)
        recent_contents = " ".join(m.content for m in result[-2:])
        assert LONG_USER_MESSAGE_3[:30] in recent_contents
        assert LONG_AI_MESSAGE_3[:30] in recent_contents

    def test_fallback_when_llm_unavailable(self):
        """Uses fallback token estimation when LLM unavailable."""
        mw = CompressionMiddleware(llm=None)

        messages = [HumanMessage(content="test")] * 100

        try:
            result = mw.compress(messages)
        except RuntimeError:
            pytest.fail("Should not raise when llm is None if below threshold")

    def test_threshold_calculation(self, mock_llm):
        """Threshold is correctly calculated from context_window and ratio."""
        mw = CompressionMiddleware(llm=mock_llm, context_window=100000, compression_ratio=0.8)
        assert mw._threshold == 80000

    def test_llm_property_lazy_init(self):
        """LLM property raises if not set."""
        mw = CompressionMiddleware(llm=None)
        with pytest.raises(RuntimeError, match="not set"):
            _ = mw.llm

    def test_set_llm(self, mock_llm):
        """set_llm updates the LLM."""
        mw = CompressionMiddleware(llm=None)
        mw.set_llm(mock_llm)
        assert mw.llm is mock_llm

    def test_no_compression_when_no_old_messages(self, mock_llm):
        """No compression if all messages are 'recent'."""
        mock_llm.get_num_tokens_from_messages.return_value = 200000

        mw = CompressionMiddleware(llm=mock_llm, keep_recent=10)

        messages = [HumanMessage(content=f"Message number {i}") for i in range(5)]

        result = mw.compress(messages)

        assert result is None

    def test_compression_maintains_message_order(self, mock_llm):
        """Compressed messages maintain correct order: summary first, then recent."""
        mock_llm.get_num_tokens_from_messages.return_value = 200000

        mw = CompressionMiddleware(llm=mock_llm, keep_recent=2)

        messages = [
            HumanMessage(content="First message in conversation"),
            AIMessage(content="Second message responding to first"),
            HumanMessage(content="Third message with new request"),
            AIMessage(content="Fourth message with detailed response"),
            HumanMessage(content=LONG_USER_MESSAGE_3),
            AIMessage(content=LONG_AI_MESSAGE_3),
        ]

        result = mw.compress(messages)

        assert result is not None
        assert isinstance(result[0], SystemMessage)
        assert "[Earlier conversation summarized:" in result[0].content
        recent = result[-2:]
        assert any(LONG_USER_MESSAGE_3[:20] in m.content for m in recent)
        assert any(LONG_AI_MESSAGE_3[:20] in m.content for m in recent)

    def test_full_conversation_compression_scenario(self, mock_llm):
        """Simulates a full conversation being compressed."""
        mock_llm.get_num_tokens_from_messages.return_value = 300000

        mw = CompressionMiddleware(llm=mock_llm, keep_recent=2)

        messages = [
            HumanMessage(content="I need help setting up a comprehensive Python web application with FastAPI, PostgreSQL, Docker, and comprehensive CI/CD pipeline"),
            AIMessage(content="I'll help you set up this comprehensive Python web application with all the components you mentioned"),
            HumanMessage(content="Now let's add user management with role-based access control, email verification, and OAuth2 integration"),
            AIMessage(content="I'll implement the complete user management system with RBAC, email verification, and OAuth2 integration"),
            HumanMessage(content="Let's implement the API endpoints for content management with articles, comments, and reactions"),
            AIMessage(content="I'll create the complete content management API with all the features you requested"),
            HumanMessage(content=LONG_USER_MESSAGE_3),
            AIMessage(content=LONG_AI_MESSAGE_3),
        ]

        result = mw.compress(messages)

        assert result is not None
        assert len(result) < len(messages)
        assert isinstance(result[0], SystemMessage)
        summary = result[0].content
        assert "[Earlier conversation summarized:" in summary
        # Original conversation topics should be compressed into summary
