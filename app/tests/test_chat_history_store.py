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

    def next_sequence(self, session_id: str) -> int:
        with self._lock:
            self._counters[session_id] += 1
            return self._counters[session_id]

    def put_item(self, item: dict[str, object]) -> None:
        with self._lock:
            self._items[item["session_id"]].append(item)

    def query_messages(self, session_id: str) -> list[dict[str, object]]:
        with self._lock:
            items = list(self._items.get(session_id, []))
        return sorted(items, key=lambda entry: entry["ts"])


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
