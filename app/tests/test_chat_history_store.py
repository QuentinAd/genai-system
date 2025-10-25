from __future__ import annotations

import asyncio
import threading
from collections import defaultdict

import pytest

from app.services.chat_history_store import (
    ChatHistoryStore,
    DynamoChatHistoryBackend,
    SQLiteChatHistoryBackend,
)


class FakeDynamoAdapter:
    """In-memory adapter emulating DynamoDB table interactions."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, int] = defaultdict(int)
        self._items: dict[str, list[dict[str, object]]] = defaultdict(list)
        self._meta: dict[str, dict[str, object]] = {}

    def next_sequence(self, session_id: str) -> int:
        with self._lock:
            self._counters[session_id] += 1
            return self._counters[session_id]

    def put_item(self, item: dict[str, object]) -> None:
        with self._lock:
            self._items[item["session_id"]].append(item)

    def update_metadata(
        self,
        session_id: str,
        *,
        role: str,
        content: str,
        mode: str,
        sequence: int,
        timestamp: str,
    ) -> None:
        with self._lock:
            self._meta[session_id] = {
                "session_id": session_id,
                "updated_at": timestamp,
                "mode": mode,
                "last_message": {"role": role, "content": content},
                "preview": content[:200],
                "sequence": sequence,
            }

    def query_messages(self, session_id: str) -> list[dict[str, object]]:
        with self._lock:
            items = list(self._items.get(session_id, []))
        return sorted(items, key=lambda entry: entry["ts"])

    def list_sessions(self, cursor: str | None, limit: int):
        with self._lock:
            sessions = sorted(
                self._meta.values(),
                key=lambda entry: entry.get("updated_at") or "",
                reverse=True,
            )
        try:
            offset = int(cursor) if cursor else 0
        except ValueError:
            offset = 0
        page = sessions[offset : offset + limit]
        next_cursor = str(offset + len(page)) if offset + len(page) < len(sessions) else None
        return page, next_cursor

    def get_messages_paginated(self, session_id: str, cursor: str | None, limit: int):
        with self._lock:
            items = sorted(
                (entry for entry in self._items.get(session_id, []) if entry["ts"] != "__meta__"),
                key=lambda entry: entry["sequence"],
                reverse=True,
            )
        try:
            before_seq = int(cursor) if cursor else None
        except ValueError:
            before_seq = None
        if before_seq is not None:
            items = [item for item in items if item["sequence"] < before_seq]
        selected = items[:limit]
        next_cursor = str(selected[-1]["sequence"]) if len(items) > limit else None
        return selected, next_cursor

    def delete_session(self, session_id: str) -> bool:
        with self._lock:
            if session_id not in self._items:
                return False
            del self._items[session_id]
            self._meta.pop(session_id, None)
            self._counters.pop(session_id, None)
        return True


@pytest.mark.asyncio
async def test_sqlite_backend_round_trip(tmp_path):
    connection = f"sqlite:///{tmp_path / 'history.db'}"
    backend = SQLiteChatHistoryBackend(connection)
    store = ChatHistoryStore(backend=backend, run_in_executor=False)

    await store.append_message("session-1", "user", "hello", "llm")
    await store.append_message("session-1", "assistant", "hi there", "llm")

    history = await store.get_history("session-1")
    assert [entry["role"] for entry in history] == ["user", "assistant"]
    assert [entry["content"] for entry in history] == ["hello", "hi there"]
    assert all("timestamp" in entry for entry in history)


@pytest.mark.asyncio
async def test_dynamo_backend_assigns_monotonic_sequences():
    adapter = FakeDynamoAdapter()
    backend = DynamoChatHistoryBackend(adapter)
    store = ChatHistoryStore(backend=backend, run_in_executor=True)

    async def append(idx: int) -> None:
        await store.append_message(
            "session-2",
            "user" if idx % 2 == 0 else "assistant",
            f"message-{idx}",
            "llm",
        )

    await asyncio.gather(*[append(idx) for idx in range(10)])

    history = await store.get_history("session-2")
    sequences = [entry["sequence"] for entry in history]
    assert sequences == sorted(sequences)
    assert len(history) == 10
    assert len(set(sequences)) == 10


@pytest.mark.asyncio
async def test_sqlite_session_listing_and_pagination(tmp_path):
    connection = f"sqlite:///{tmp_path / 'history_list.db'}"
    store = ChatHistoryStore(
        backend=SQLiteChatHistoryBackend(connection),
        run_in_executor=False,
    )

    for idx in range(3):
        session_id = f"session-{idx}"
        await store.append_message(session_id, "user", f"greeting-{idx}", "llm")
        await store.append_message(session_id, "assistant", f"response-{idx}", "llm")

    page_one, next_cursor = await store.list_sessions(limit=1)
    assert len(page_one) == 1
    assert next_cursor == "1"

    page_two, last_cursor = await store.list_sessions(cursor=next_cursor, limit=2)
    assert len(page_two) == 2
    assert last_cursor is None
    assert all("last_message" in entry for entry in page_two)


@pytest.mark.asyncio
async def test_sqlite_session_messages_pagination(tmp_path):
    connection = f"sqlite:///{tmp_path / 'history_messages.db'}"
    store = ChatHistoryStore(
        backend=SQLiteChatHistoryBackend(connection),
        run_in_executor=False,
    )

    session_id = "session-x"
    await store.append_message(session_id, "user", "Hello", "llm")
    await store.append_message(session_id, "assistant", "Hi there", "llm")
    await store.append_message(session_id, "user", "How are you?", "llm")

    messages, next_cursor = await store.get_session_messages(session_id, limit=2)
    assert len(messages) == 2
    assert messages[-1]["content"] == "How are you?"
    assert next_cursor is not None

    more_messages, next_cursor_two = await store.get_session_messages(
        session_id,
        cursor=next_cursor,
        limit=2,
    )
    assert len(more_messages) == 1
    assert more_messages[0]["content"] == "Hello"
    assert next_cursor_two is None


@pytest.mark.asyncio
async def test_delete_session_clears_history(tmp_path):
    connection = f"sqlite:///{tmp_path / 'history_delete.db'}"
    store = ChatHistoryStore(
        backend=SQLiteChatHistoryBackend(connection),
        run_in_executor=False,
    )

    session_id = "session-delete"
    await store.append_message(session_id, "user", "Hello", "llm")
    deleted = await store.delete_session(session_id)
    assert deleted is True

    messages, _ = await store.get_session_messages(session_id)
    assert messages == []
    deleted_again = await store.delete_session(session_id)
    assert deleted_again is False
