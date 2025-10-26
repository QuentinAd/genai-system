import json

import pytest

from app import create_app
from app.services import ChatBotBase, DummyChatBot
from app.services import chat_history_store


@pytest.fixture(autouse=True)
def stub_chat_history(monkeypatch):
    calls: dict[str, list] = {"append": [], "get": [], "list": [], "messages": [], "clear": []}
    history: list[dict[str, str]] = []
    state = {
        "sessions_result": ([], None),
        "messages_map": {},
        "delete_existing": set(),
    }

    async def fake_get(session_id: str):
        calls["get"].append(session_id)
        # Return a copy to prevent in-place mutation by caller.
        return [dict(entry) for entry in history]

    async def fake_append(session_id: str, role: str, content: str, mode: str) -> None:
        calls["append"].append(
            {
                "session_id": session_id,
                "role": role,
                "content": content,
                "mode": mode,
            }
        )

    async def fake_list(cursor: str | None = None, limit: int = 20):
        calls["list"].append({"cursor": cursor, "limit": limit})
        sessions, next_cursor = state["sessions_result"]
        return sessions, next_cursor

    async def fake_get_messages(
        session_id: str,
        *,
        cursor: str | None = None,
        limit: int = 50,
    ):
        calls["messages"].append({"session_id": session_id, "cursor": cursor, "limit": limit})
        messages, next_cursor = state["messages_map"].get(session_id, ([], None))
        return messages, next_cursor

    async def fake_delete(session_id: str) -> bool:
        calls["clear"].append(session_id)
        if session_id in state["delete_existing"]:
            state["delete_existing"].remove(session_id)
            return True
        return False

    monkeypatch.setattr(chat_history_store, "get_history", fake_get)
    monkeypatch.setattr(chat_history_store, "append_message", fake_append)
    monkeypatch.setattr(chat_history_store, "list_sessions", fake_list)
    monkeypatch.setattr(chat_history_store, "get_session_messages", fake_get_messages)
    monkeypatch.setattr(chat_history_store, "delete_session", fake_delete)

    return {"calls": calls, "history": history, "state": state}


class StubHiRAGService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def chat(
        self,
        query: str,
        session_id: str,
        *,
        mode: str = "",
        history=None,
    ) -> dict[str, object]:
        self.calls.append(
            {
                "query": query,
                "session_id": session_id,
                "mode": mode,
                "history": history,
            }
        )
        return {
            "answer": "retrieved answer",
            "context": "retrieved context",
            "prompt": "prompt",
            "references": [{"title": "One"}],
        }


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


@pytest.mark.asyncio
async def test_chat_endpoint_hirag_mode_includes_retrieval_metadata(stub_chat_history):
    bot = DummyChatBot()
    service = StubHiRAGService()
    app = create_app(chatbot=bot, hirag_service=service)
    stub_chat_history["history"].append({"role": "assistant", "content": "persisted"})
    async with app.test_client() as client:
        resp = await client.post(
            "/chat?hirag&stream=events",
            json={
                "message": "hello world",
                "history": [{"role": "assistant", "content": "prev"}],
            },
            headers={"Session-Id": "abc123"},
        )
        payload = await resp.get_data(as_text=True)
        assert resp.status_code == 200
        events = [json.loads(line) for line in payload.splitlines() if line]
        retrieval = events[-1]
        assert retrieval == {
            "event": "retrieval_metadata",
            "data": {
                "mode": "hirag",
                "session_id": "abc123",
                "answer": "retrieved answer",
                "context": "retrieved context",
                "references": [{"title": "One"}],
            },
        }
        assert service.calls
        call = service.calls[0]
        assert call["mode"] == "hi"
        assert call["session_id"] == "abc123"
        assert call["history"] == [
            {"role": "assistant", "content": "persisted"},
            {"role": "assistant", "content": "prev"},
        ]
        append_calls = stub_chat_history["calls"]["append"]
        assert append_calls[0]["role"] == "user"
        assert append_calls[0]["content"] == "hello world"
        assert append_calls[0]["mode"] == "hirag"
        assert append_calls[1]["role"] == "assistant"
        assert append_calls[1]["content"] == "helloworld"
        assert append_calls[1]["mode"] == "hirag"


@pytest.mark.asyncio
async def test_chat_endpoint_rag_mode_uses_cookie_session_id(stub_chat_history):
    bot = DummyChatBot()
    service = StubHiRAGService()
    app = create_app(chatbot=bot, hirag_service=service)
    async with app.test_client() as client:
        client.set_cookie("localhost", "Session-Id", "cookie-session")
        resp = await client.post(
            "/chat?rag&stream=events",
            json={"message": "hello"},
        )
        payload = await resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert service.calls
        call = service.calls[0]
        assert call["mode"] == "naive"
        assert call["session_id"] == "cookie-session"
        events = [json.loads(line) for line in payload.splitlines() if line]
        assert events[-1]["data"]["mode"] == "rag"
        append_calls = stub_chat_history["calls"]["append"]
        assert append_calls[0]["mode"] == "rag"
        assert append_calls[1]["mode"] == "rag"


@pytest.mark.asyncio
async def test_chat_endpoint_llm_only_skips_hirag_service(stub_chat_history):
    bot = DummyChatBot()
    service = StubHiRAGService()
    app = create_app(chatbot=bot, hirag_service=service)
    async with app.test_client() as client:
        resp = await client.post(
            "/chat?stream=events",
            json={"message": "hello"},
            headers={"Session-Id": "llm-session"},
        )
        payload = await resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert not service.calls
        events = [json.loads(line) for line in payload.splitlines() if line]
        assert all(evt.get("event") != "retrieval_metadata" for evt in events)
        append_calls = stub_chat_history["calls"]["append"]
        assert len(append_calls) == 2
        assert {call["mode"] for call in append_calls} == {"llm"}
        assert append_calls[0]["content"] == "hello"
        assert append_calls[1]["content"] == "hello"


@pytest.mark.asyncio
async def test_list_chat_history_endpoint(stub_chat_history):
    bot = DummyChatBot()
    app = create_app(chatbot=bot)
    stub_chat_history["state"]["sessions_result"] = (
        [
            {
                "session_id": "abc",
                "updated_at": "2024-01-01T00:00:00Z",
                "mode": "llm",
                "preview": "Hi",
                "last_message": {"role": "assistant", "content": "Hi"},
            }
        ],
        "cursor-1",
    )

    async with app.test_client() as client:
        resp = await client.get("/chat_history?limit=5")
        data = await resp.get_json()
        assert resp.status_code == 200
        assert data["sessions"][0]["session_id"] == "abc"
        assert data["next"] == "cursor-1"
        calls = stub_chat_history["calls"]["list"]
        assert calls[0]["limit"] == 5


@pytest.mark.asyncio
async def test_fetch_chat_history_endpoint(stub_chat_history):
    bot = DummyChatBot()
    app = create_app(chatbot=bot)
    stub_chat_history["state"]["messages_map"]["abc"] = (
        [
            {
                "role": "user",
                "content": "Hello",
                "timestamp": "2024-01-01T00:00:00Z",
                "mode": "llm",
                "events": [],
            }
        ],
        None,
    )

    async with app.test_client() as client:
        resp = await client.get("/chat_history/abc")
        data = await resp.get_json()
        assert resp.status_code == 200
        assert data["messages"][0]["content"] == "Hello"
        assert data["next"] is None
        calls = stub_chat_history["calls"]["messages"]
        assert calls[0]["session_id"] == "abc"


@pytest.mark.asyncio
async def test_clear_chat_history_endpoint(stub_chat_history):
    bot = DummyChatBot()
    app = create_app(chatbot=bot)
    stub_chat_history["state"]["delete_existing"].add("abc")

    async with app.test_client() as client:
        resp = await client.delete("/chat_history/abc")
        assert resp.status_code == 204

        resp_missing = await client.delete("/chat_history/abc")
        assert resp_missing.status_code == 404


@pytest.mark.asyncio
async def test_chat_endpoint_passes_context_to_chatbot(stub_chat_history):
    """Test that HiRAG context is passed to the chatbot as a system message."""

    class ContextTrackingBot(ChatBotBase):
        """Bot that tracks the history it receives."""

        def __init__(self):
            super().__init__("tracker")
            self.received_history = None

        async def stream_events(self, message, *, config=None, include_events=None, history=None):
            self.received_history = history
            # Yield a simple token
            yield "response"

    bot = ContextTrackingBot()
    service = StubHiRAGService()
    app = create_app(chatbot=bot, hirag_service=service)

    async with app.test_client() as client:
        resp = await client.post(
            "/chat?hirag&stream=events",
            json={"message": "test question"},
            headers={"Session-Id": "session-1"},
        )
        assert resp.status_code == 200

        # Verify the bot received history with context
        assert bot.received_history is not None
        # First message should be system message with context
        assert len(bot.received_history) >= 1
        first_message = bot.received_history[0]
        assert first_message["role"] == "system"
        assert "Retrieved Context:" in first_message["content"]
        assert "retrieved context" in first_message["content"]
