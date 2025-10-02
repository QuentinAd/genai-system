import json

import httpx
import pytest
from pydantic import ValidationError

from app.schema import ChatInput
from app.services import ChatBotBase, DummyChatBot, OpenAIChatBot


class StubChunk:
    def __init__(self, content: str | None = None, text: str | None = None) -> None:
        self.content = content
        self._text = text

    def text(self) -> str:
        return self._text or ""


class StubLLM:
    def __init__(self) -> None:
        self.astream_call_count = 0

    def invoke(self, input: str, *, config=None, **kwargs) -> str:
        return f"echo:{input}"

    async def astream(self, input: str, *, config=None, **kwargs):
        self.astream_call_count += 1
        yield StubChunk(content="", text="")
        yield StubChunk(content="hello", text="hello")
        yield "!"

    async def astream_events(self, input: str, *, config=None, **kwargs):
        yield {"event": "on_chat_model_start", "data": {"input": input}}
        yield {
            "event": "on_chat_model_stream",
            "data": {"chunk": StubChunk(content="hello", text="hello")},
        }
        yield {
            "event": "on_chat_model_end",
            "data": {"output": StubChunk(content="hello", text="hello")},
        }


class StubLLMNoEvents(StubLLM):
    astream_events = None  # type: ignore[assignment]

    async def astream(self, input: str, *, config=None, **kwargs):
        self.astream_call_count += 1
        for token in ["hi", "there"]:
            yield StubChunk(content=token, text=token)


@pytest.mark.asyncio
async def test_chat_input_validation():
    data = ChatInput(message="hello")
    assert data.message == "hello"

    with pytest.raises(ValidationError):
        ChatInput(message="")


@pytest.mark.asyncio
async def test_dummy_chatbot_stream():
    bot = DummyChatBot()
    tokens = [token async for token in bot.stream_chat("foo bar")]
    assert tokens == ["foo", "bar"]


@pytest.mark.asyncio
async def test_fetch_status():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        bot = DummyChatBot(client=client)
        status = await bot.fetch_status("http://test")
        assert status == 200


@pytest.mark.asyncio
async def test_chatbot_base_streams_from_llm():
    bot = ChatBotBase("stub", llm=StubLLM())
    tokens = [token async for token in bot.stream_chat("hi")]
    assert tokens == ["hello", "!"]


@pytest.mark.asyncio
async def test_chatbot_base_stream_events_passthrough():
    bot = ChatBotBase("stub", llm=StubLLM())
    events = [json.loads(event) async for event in bot.stream_events("hi")]
    assert events[0]["event"] == "on_chat_model_start"
    assert events[1] == {"event": "token", "data": "hello"}
    assert events[-1]["event"] == "on_chat_model_end"


@pytest.mark.asyncio
async def test_chatbot_base_stream_events_fallback_to_tokens():
    bot = ChatBotBase("stub", llm=StubLLMNoEvents())
    events = [event async for event in bot.stream_events("hi there")]

    start = json.loads(events[0])
    assert start == {"event": "on_chat_model_start", "data": {"input": "hi there"}}

    assert events[1:-1] == ["hi", "there"]

    end = json.loads(events[-1])
    assert end == {"event": "on_chat_model_end", "data": {"output": "hithere"}}


@pytest.mark.asyncio
async def test_openai_chatbot_uses_settings_api_key(monkeypatch):
    from app.services import openai as openai_module

    monkeypatch.setattr(openai_module.settings, "openai_api_key", "test-key", raising=False)
    monkeypatch.setattr(
        openai_module.settings, "openai_api_base", "http://localhost", raising=False
    )

    captured: dict[str, dict[str, object]] = {}

    def fake_chat_openai(*args, **kwargs):
        captured["kwargs"] = kwargs
        return StubLLM()

    monkeypatch.setattr(openai_module, "ChatOpenAI", fake_chat_openai)

    bot = OpenAIChatBot()
    tokens = [token async for token in bot.stream_chat("hi")]
    assert tokens
    assert captured["kwargs"]["api_key"] == "test-key"
    assert captured["kwargs"]["base_url"] == "http://localhost"


@pytest.mark.asyncio
async def test_chatbot_stream_events_include_only_tokens():
    bot = ChatBotBase("stub", llm=StubLLM())
    events = [
        json.loads(event) async for event in bot.stream_events("hi", include_events=["token"])
    ]
    assert events == [{"event": "token", "data": "hello"}]


@pytest.mark.asyncio
async def test_chatbot_fallback_tokens_only_filter():
    bot = ChatBotBase("stub", llm=StubLLMNoEvents())
    tokens = [event async for event in bot.stream_events("hi there", include_events=["token"])]
    assert tokens == ["hi", "there"]


@pytest.mark.asyncio
async def test_chatbot_stream_events_excludes_when_not_allowed():
    bot = ChatBotBase("stub", llm=StubLLM())
    events = [
        json.loads(event)
        async for event in bot.stream_events("hi", include_events=["on_chat_model_end"])
    ]
    assert events == [{"event": "on_chat_model_end", "data": {"output": "hello"}}]


@pytest.mark.asyncio
async def test_chatbot_fallback_respects_include_end_only():
    bot = ChatBotBase("stub", llm=StubLLMNoEvents())
    events = [
        json.loads(event)
        async for event in bot.stream_events("hi", include_events=["on_chat_model_end"])
    ]
    assert events == [{"event": "on_chat_model_end", "data": {"output": "hi"}}]
