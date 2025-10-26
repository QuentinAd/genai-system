"""Tests for HiRAGChatBot class."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

from app.services.hirag import HiRAGChatBot, HiRAGService


@dataclass
class FakeQueryParam:
    mode: str = "hi"
    only_need_context: bool = False
    response_type: str = "Multiple Paragraphs"
    level: int = 2
    top_k: int = 20
    top_m: int = 10


class StubHiRAG:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.aquery: AsyncMock = AsyncMock()

    def insert(self, documents: list[str]) -> None:
        pass


class StubChunk:
    def __init__(self, content: str | None = None, text: str | None = None) -> None:
        self.content = content
        self._text = text

    def text(self) -> str:
        return self._text or ""


class StubLLM:
    def __init__(self) -> None:
        self.astream_call_count = 0
        self.last_request: Any = None

    async def astream(self, input: Any, *, config=None, **kwargs):
        self.astream_call_count += 1
        self.last_request = input
        yield StubChunk(content="Response ", text="Response ")
        yield StubChunk(content="with context", text="with context")


def _make_hirag_service(monkeypatch) -> tuple[HiRAGService, StubHiRAG]:
    """Create a test HiRAGService with stub backend."""
    created: dict[str, StubHiRAG] = {}

    def factory(**kwargs: Any) -> StubHiRAG:
        created["instance"] = StubHiRAG(**kwargs)
        return created["instance"]

    monkeypatch.setattr(
        HiRAGService,
        "_local_storage_overrides",
        lambda self: {},
    )

    service = HiRAGService(hirag_cls=factory, query_param_cls=FakeQueryParam)
    return service, created["instance"]


@pytest.mark.asyncio
async def test_hirag_chatbot_initializes_with_service(monkeypatch):
    """Test HiRAGChatBot initialization."""
    from app.services import openai as openai_module

    monkeypatch.setattr(openai_module.settings, "openai_api_key", "test-key", raising=False)
    monkeypatch.setattr(
        openai_module.settings, "openai_api_base", "http://localhost", raising=False
    )

    def fake_chat_openai(*args, **kwargs):
        return StubLLM()

    monkeypatch.setattr(openai_module, "ChatOpenAI", fake_chat_openai)

    service, _ = _make_hirag_service(monkeypatch)
    bot = HiRAGChatBot(hirag_service=service, mode="hi")

    assert bot.hirag_service is service
    assert bot.mode == "hi"
    assert bot.llm is not None
    assert bot.model_name  # Should have default from OpenAIChatBot


@pytest.mark.asyncio
async def test_hirag_chatbot_retrieves_context_before_streaming(monkeypatch):
    """Test that HiRAGChatBot retrieves context and passes it to LLM."""
    from app.services import openai as openai_module

    monkeypatch.setattr(openai_module.settings, "openai_api_key", "test-key", raising=False)
    monkeypatch.setattr(
        openai_module.settings, "openai_api_base", "http://localhost", raising=False
    )

    stub_llm = StubLLM()

    def fake_chat_openai(*args, **kwargs):
        return stub_llm

    monkeypatch.setattr(openai_module, "ChatOpenAI", fake_chat_openai)

    service, stub_hirag = _make_hirag_service(monkeypatch)

    # Mock the aquery to return context
    retrieved_context = "This is the retrieved context from HiRAG"
    stub_hirag.aquery.return_value = retrieved_context

    bot = HiRAGChatBot(hirag_service=service, mode="hi")
    tokens = [token async for token in bot.stream_chat("What is the answer?")]

    # Verify context was retrieved
    assert stub_hirag.aquery.call_count == 1
    call_args = stub_hirag.aquery.call_args
    assert call_args.args[0] == "What is the answer?"
    # The param should have only_need_context=True
    assert call_args.args[1].only_need_context is True

    # Verify LLM received the request
    assert stub_llm.astream_call_count == 1
    assert stub_llm.last_request is not None

    # Verify the request contains context as a system message
    messages = stub_llm.last_request
    # First message should be system message with context
    assert len(messages) >= 2
    assert messages[0].type == "system"
    assert "Context:" in messages[0].content
    assert retrieved_context in messages[0].content
    # Last message should be the user message
    assert messages[-1].type == "human"
    assert messages[-1].content == "What is the answer?"

    # Verify tokens were streamed
    assert tokens == ["Response ", "with context"]


@pytest.mark.asyncio
async def test_hirag_chatbot_build_request_with_context(monkeypatch):
    """Test HiRAGChatBot.build_request includes context."""
    from app.services import openai as openai_module

    monkeypatch.setattr(openai_module.settings, "openai_api_key", "test-key", raising=False)

    def fake_chat_openai(*args, **kwargs):
        return StubLLM()

    monkeypatch.setattr(openai_module, "ChatOpenAI", fake_chat_openai)

    service, _ = _make_hirag_service(monkeypatch)
    bot = HiRAGChatBot(hirag_service=service, mode="hi")

    context = "Retrieved context about the topic"
    history = [
        {"role": "user", "content": "Previous question"},
        {"role": "assistant", "content": "Previous answer"},
    ]

    messages = bot.build_request(
        "Current question",
        history=history,
        context=context,
    )

    # Should have: system (context) + user + assistant + user
    assert len(messages) == 4
    assert messages[0].type == "system"
    assert "Context:" in messages[0].content
    assert context in messages[0].content
    assert messages[1].type == "human"
    assert messages[1].content == "Previous question"
    assert messages[2].type == "ai"
    assert messages[2].content == "Previous answer"
    assert messages[3].type == "human"
    assert messages[3].content == "Current question"


@pytest.mark.asyncio
async def test_hirag_chatbot_model_info(monkeypatch):
    """Test HiRAGChatBot.model_info includes hirag mode."""
    from app.services import openai as openai_module

    monkeypatch.setattr(openai_module.settings, "openai_api_key", "test-key", raising=False)

    def fake_chat_openai(*args, **kwargs):
        return StubLLM()

    monkeypatch.setattr(openai_module, "ChatOpenAI", fake_chat_openai)

    service, _ = _make_hirag_service(monkeypatch)
    bot = HiRAGChatBot(hirag_service=service, mode="naive")

    info = bot.model_info()
    assert info["type"] == "HiRAGChatBot"
    assert info["hirag_mode"] == "naive"
    assert "model_name" in info


@pytest.mark.asyncio
async def test_hirag_chatbot_aclose(monkeypatch):
    """Test HiRAGChatBot.aclose delegates to underlying client."""
    from app.services import openai as openai_module

    monkeypatch.setattr(openai_module.settings, "openai_api_key", "test-key", raising=False)

    def fake_chat_openai(*args, **kwargs):
        return StubLLM()

    monkeypatch.setattr(openai_module, "ChatOpenAI", fake_chat_openai)

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        service, _ = _make_hirag_service(monkeypatch)
        bot = HiRAGChatBot(hirag_service=service, mode="hi", client=client)
        # Should not raise
        await bot.aclose()
