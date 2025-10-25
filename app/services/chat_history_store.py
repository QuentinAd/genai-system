"""Persist chat history using DynamoDB with a SQLite fallback."""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_community.chat_message_histories.sql import SQLChatMessageHistory

from app.settings import settings

logger = logging.getLogger(__name__)

_META_SORT_KEY = "__meta__"
_DEFAULT_SQLITE_FILENAME = "chat_history.sqlite3"
_MessageFactory = Callable[[str], BaseMessage]

_ROLE_TO_MESSAGE: dict[str, _MessageFactory] = {
    "assistant": AIMessage,
    "system": SystemMessage,
    "user": HumanMessage,
}


def _default_sqlite_path() -> str:
    root = settings.chat_history_sqlite_path
    if root:
        return root
    data_dir = os.getenv("CHAT_HISTORY_DIR")
    if data_dir:
        return os.path.join(data_dir, _DEFAULT_SQLITE_FILENAME)
    return os.path.join(os.getcwd(), _DEFAULT_SQLITE_FILENAME)


def _ensure_iso_timestamp(ts: datetime | None = None) -> str:
    value = ts or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _to_int(value: Any | None) -> int:
    if value is None:
        return 0
    if isinstance(value, Decimal):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    try:
        return int(str(value))
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return 0


@dataclass(slots=True)
class DynamoHistoryTableAdapter:
    """Adapter that wraps a boto3 DynamoDB table."""

    table: Any

    def next_sequence(self, session_id: str) -> int:
        timestamp = _ensure_iso_timestamp()
        response = self.table.update_item(
            Key={"session_id": session_id, "ts": _META_SORT_KEY},
            UpdateExpression=(
                "SET counter = if_not_exists(counter, :zero) + :inc, updated_at = :updated_at"
            ),
            ExpressionAttributeValues={
                ":zero": 0,
                ":inc": 1,
                ":updated_at": timestamp,
            },
            ReturnValues="UPDATED_NEW",
        )
        return _to_int(response.get("Attributes", {}).get("counter"))

    def put_item(self, item: dict[str, Any]) -> None:
        self.table.put_item(
            Item=item,
            ConditionExpression=("attribute_not_exists(session_id) AND attribute_not_exists(ts)"),
        )

    def query_messages(self, session_id: str) -> list[dict[str, Any]]:
        from boto3.dynamodb.conditions import Key

        response = self.table.query(
            KeyConditionExpression=Key("session_id").eq(session_id),
            ScanIndexForward=True,
        )
        return [item for item in response.get("Items", []) if item.get("ts") != _META_SORT_KEY]


class DynamoChatHistoryBackend:
    """Store backed by DynamoDB with per-session monotonic sequence numbers."""

    def __init__(
        self,
        adapter: DynamoHistoryTableAdapter,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._adapter = adapter
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def append_message(self, session_id: str, role: str, content: str, mode: str) -> None:
        if not session_id:
            return
        sequence = self._adapter.next_sequence(session_id)
        timestamp = self._clock()
        ts_str = _ensure_iso_timestamp(timestamp)
        sort_key = f"{ts_str}#{sequence:020d}"
        item = {
            "session_id": session_id,
            "ts": sort_key,
            "role": role,
            "content": content,
            "mode": mode,
            "sequence": sequence,
            "timestamp": ts_str,
        }
        self._adapter.put_item(item)

    def get_history(self, session_id: str) -> list[dict[str, Any]]:
        if not session_id:
            return []
        items = self._adapter.query_messages(session_id)
        payload: list[dict[str, Any]] = []
        for item in items:
            payload.append(
                {
                    "role": str(item.get("role", "user")),
                    "content": str(item.get("content", "")),
                    "mode": str(item.get("mode", "")),
                    "timestamp": item.get("timestamp") or str(item.get("ts", "")),
                    "sequence": _to_int(item.get("sequence")),
                }
            )
        payload.sort(key=lambda entry: entry["sequence"])
        return payload


class SQLiteChatHistoryBackend:
    """SQLite-backed history using LangChain's SQL chat history helper."""

    def __init__(self, connection_string: str | None = None) -> None:
        path = connection_string or f"sqlite:///{_default_sqlite_path()}"
        self._connection = path
        self._lock = threading.Lock()

    def _message_history(self, session_id: str) -> SQLChatMessageHistory:
        return SQLChatMessageHistory(
            session_id=session_id,
            connection=self._connection,
        )

    def append_message(self, session_id: str, role: str, content: str, mode: str) -> None:
        if not session_id:
            return
        message_class = _ROLE_TO_MESSAGE.get(role, HumanMessage)
        timestamp = _ensure_iso_timestamp()
        message = message_class(
            content=content,
            additional_kwargs={"mode": mode, "timestamp": timestamp},
        )
        with self._lock:
            history = self._message_history(session_id)
            history.add_message(message)

    def get_history(self, session_id: str) -> list[dict[str, Any]]:
        if not session_id:
            return []
        with self._lock:
            history = self._message_history(session_id)
            messages = list(history.messages)
        results: list[dict[str, Any]] = []
        for idx, message in enumerate(messages, start=1):
            role = getattr(message, "type", "human")
            if role == "ai":
                role = "assistant"
            elif role == "human":
                role = "user"
            results.append(
                {
                    "role": role,
                    "content": message.content,
                    "mode": message.additional_kwargs.get("mode", ""),
                    "timestamp": message.additional_kwargs.get("timestamp", ""),
                    "sequence": idx,
                }
            )
        return results


class ChatHistoryStore:
    """Facade providing async wrappers around history backends."""

    def __init__(
        self,
        backend: Any | None = None,
        *,
        run_in_executor: bool = True,
    ) -> None:
        self._backend = backend or _create_backend()
        self._run_in_executor = run_in_executor

    async def get_history(self, session_id: str) -> list[dict[str, Any]]:
        if not session_id:
            return []
        return await self._call_backend("get_history", session_id)

    async def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        mode: str,
    ) -> None:
        if not session_id:
            return
        await self._call_backend("append_message", session_id, role, content, mode)

    async def _call_backend(self, method: str, *args) -> Any:
        func = getattr(self._backend, method)
        if not self._run_in_executor:
            return func(*args)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, func, *args)


_default_store: ChatHistoryStore | None = None


def _create_backend() -> Any:
    table_name = settings.chat_history_table or os.getenv("CHAT_HISTORY_TABLE")
    if table_name:
        try:
            dynamodb = boto3.resource(
                "dynamodb",
                region_name=settings.aws_region or os.getenv("AWS_REGION"),
                endpoint_url=settings.chat_history_endpoint_url,
            )
            table = dynamodb.Table(table_name)
            adapter = DynamoHistoryTableAdapter(table)
            return DynamoChatHistoryBackend(adapter)
        except (BotoCoreError, ClientError) as exc:  # pragma: no cover - network/env specific
            logger.warning("Falling back to SQLite chat history store: %s", exc)
    connection = settings.chat_history_sqlite_path
    if connection and not connection.startswith("sqlite:///"):
        connection = f"sqlite:///{connection}"
    return SQLiteChatHistoryBackend(connection)


def _store() -> ChatHistoryStore:
    global _default_store
    if _default_store is None:
        _default_store = ChatHistoryStore()
    return _default_store


async def get_history(session_id: str) -> list[dict[str, Any]]:
    """Return persisted chat history for a session."""
    try:
        return await _store().get_history(session_id)
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to load chat history for session %s", session_id)
        return []


async def append_message(session_id: str, role: str, content: str, mode: str) -> None:
    """Persist a chat message."""
    if not session_id:
        return
    try:
        await _store().append_message(session_id, role, content, mode)
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to append chat history for session %s", session_id)
