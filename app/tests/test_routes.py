import json

import pytest

from app import create_app
from app.services import ChatBotBase, DummyChatBot


class StubChunk:
    def __init__(self, content: str | None = None, text: str | None = None) -> None:
        self.content = content
        self._text = text

    def text(self) -> str:
        return self._text or ""


class StubLLM:
    def invoke(self, input: str, *, config=None, **kwargs) -> str:
        return f"echo:{input}"

    async def astream(self, input: str, *, config=None, **kwargs):
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


@pytest.mark.asyncio
async def test_chat_endpoint_streams_events_by_default():
    bot = DummyChatBot()
    app = create_app(chatbot=bot)
    async with app.test_client() as client:
        resp = await client.post("/chat", json={"message": "hello world"})
        payload = await resp.get_data(as_text=True)
        assert resp.status_code == 200
        events = [json.loads(line) for line in payload.splitlines() if line]
        assert events == [
            {"event": "on_chat_model_start", "data": {"input": "hello world"}},
            {"event": "token", "data": "hello"},
            {"event": "token", "data": "world"},
            {"event": "on_chat_model_end", "data": {"output": "helloworld"}},
        ]


@pytest.mark.asyncio
async def test_chat_endpoint_invalid_json():
    bot = DummyChatBot()
    app = create_app(chatbot=bot)
    async with app.test_client() as client:
        resp = await client.post("/chat", json={"foo": "bar"})
        assert resp.status_code == 400


@pytest.mark.asyncio
async def test_models_endpoint():
    bot = DummyChatBot()
    app = create_app(chatbot=bot)
    async with app.test_client() as client:
        resp = await client.get("/models")
        data = await resp.get_json()
        assert resp.status_code == 200
        assert data["model_name"] == "dummy"


@pytest.mark.asyncio
async def test_chat_endpoint_streams_events_ndjson():
    bot = DummyChatBot()
    app = create_app(chatbot=bot)
    async with app.test_client() as client:
        resp = await client.post("/chat?stream=events", json={"message": "foo bar"})
        payload = await resp.get_data(as_text=True)
        assert resp.status_code == 200
        lines = [line for line in payload.splitlines() if line]
        assert lines
        events = [json.loads(line) for line in lines]
        assert events == [
            {"event": "on_chat_model_start", "data": {"input": "foo bar"}},
            {"event": "token", "data": "foo"},
            {"event": "token", "data": "bar"},
            {"event": "on_chat_model_end", "data": {"output": "foobar"}},
        ]


@pytest.mark.asyncio
async def test_chat_endpoint_events_include_additional_streams():
    bot = ChatBotBase("stub", llm=StubLLM())
    app = create_app(chatbot=bot)
    async with app.test_client() as client:
        resp = await client.post(
            "/chat?stream=events&include=on_chat_model_end",
            json={"message": "hi"},
        )
        payload = await resp.get_data(as_text=True)
        assert resp.status_code == 200
        lines = [json.loads(line) for line in payload.splitlines() if line]
        assert lines == [
            {"event": "token", "data": "hello"},
            {"event": "on_chat_model_end", "data": {"output": "hello"}},
        ]


@pytest.mark.asyncio
async def test_chat_endpoint_stream_tokens_mode():
    bot = DummyChatBot()
    app = create_app(chatbot=bot)
    async with app.test_client() as client:
        resp = await client.post("/chat?stream=tokens", json={"message": "foo bar"})
        text = await resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert text == "foobar"
