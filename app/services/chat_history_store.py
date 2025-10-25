"""Persist chat history using DynamoDB with a SQLite fallback."""

from __future__ import annotations

import asyncio
import contextlib
import json
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
_SESSION_PAGE_SIZE = 20
_MESSAGE_PAGE_SIZE = 50

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
        preview = content[:200]
        self.table.update_item(
            Key={"session_id": session_id, "ts": _META_SORT_KEY},
            UpdateExpression=(
                "SET last_role = :role, last_content = :content, mode = :mode, "
                "updated_at = :updated_at, last_sequence = :sequence, preview = :preview"
            ),
            ExpressionAttributeValues={
                ":role": role,
                ":content": preview,
                ":mode": mode,
                ":updated_at": timestamp,
                ":sequence": sequence,
                ":preview": preview,
            },
        )

    def query_messages(self, session_id: str) -> list[dict[str, Any]]:
        from boto3.dynamodb.conditions import Key

        response = self.table.query(
            KeyConditionExpression=Key("session_id").eq(session_id),
            ScanIndexForward=True,
        )
        return [item for item in response.get("Items", []) if item.get("ts") != _META_SORT_KEY]

    def list_sessions(
        self, cursor: str | None, limit: int
    ) -> tuple[list[dict[str, Any]], str | None]:
        from boto3.dynamodb.conditions import Attr

        scan_kwargs: dict[str, Any] = {
            "FilterExpression": Attr("ts").eq(_META_SORT_KEY),
            "ProjectionExpression": "session_id, updated_at, last_role, last_content, mode, "
            "last_sequence, preview",
        }
        if cursor:
            try:
                scan_kwargs["ExclusiveStartKey"] = json.loads(cursor)
            except json.JSONDecodeError:  # pragma: no cover - defensive
                pass

        response = self.table.scan(**scan_kwargs)
        items = response.get("Items", [])
        sessions = [
            {
                "session_id": item.get("session_id", ""),
                "updated_at": item.get("updated_at"),
                "mode": item.get("mode", "llm"),
                "last_message": {
                    "role": str(item.get("last_role", "assistant")),
                    "content": str(item.get("last_content", "")),
                },
                "preview": item.get("preview") or str(item.get("last_content", ""))[:200],
                "sequence": _to_int(item.get("last_sequence")),
            }
            for item in items
        ]
        sessions.sort(key=lambda entry: entry.get("updated_at") or "", reverse=True)

        last_evaluated = response.get("LastEvaluatedKey")
        next_cursor = json.dumps(last_evaluated) if last_evaluated else None
        return sessions[:limit], next_cursor

    def get_messages_paginated(
        self,
        session_id: str,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[dict[str, Any]], str | None]:
        from boto3.dynamodb.conditions import Key

        query_kwargs: dict[str, Any] = {
            "KeyConditionExpression": Key("session_id").eq(session_id),
            "ScanIndexForward": False,
            "Limit": limit,
        }
        if cursor:
            try:
                query_kwargs["ExclusiveStartKey"] = json.loads(cursor)
            except json.JSONDecodeError:  # pragma: no cover - defensive
                pass

        response = self.table.query(**query_kwargs)
        items = [item for item in response.get("Items", []) if item.get("ts") != _META_SORT_KEY]
        last_evaluated = response.get("LastEvaluatedKey")
        next_cursor = json.dumps(last_evaluated) if last_evaluated else None
        return items, next_cursor

    def delete_session(self, session_id: str) -> bool:
        from boto3.dynamodb.conditions import Key

        response = self.table.query(
            KeyConditionExpression=Key("session_id").eq(session_id),
            ProjectionExpression="session_id, ts",
        )
        items = response.get("Items", [])
        if not items:
            return False
        with self.table.batch_writer() as batch:
            for item in items:
                batch.delete_item(Key={"session_id": item["session_id"], "ts": item["ts"]})
        return True


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
        self._adapter.update_metadata(
            session_id,
            role=role,
            content=content,
            mode=mode,
            sequence=sequence,
            timestamp=ts_str,
        )

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

    def list_sessions(
        self, cursor: str | None, limit: int
    ) -> tuple[list[dict[str, Any]], str | None]:
        sessions, next_cursor = self._adapter.list_sessions(cursor, limit)
        normalised: list[dict[str, Any]] = []
        for entry in sessions:
            last_message = entry.get("last_message") or {}
            role = str(last_message.get("role", "assistant"))
            content = str(last_message.get("content", ""))
            normalised.append(
                {
                    "session_id": entry.get("session_id", ""),
                    "updated_at": entry.get("updated_at"),
                    "mode": entry.get("mode", "llm"),
                    "preview": entry.get("preview") or content[:200],
                    "last_message": {"role": role, "content": content},
                }
            )
        return normalised, next_cursor

    def get_messages_paginated(
        self,
        session_id: str,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[dict[str, Any]], str | None]:
        items, next_cursor = self._adapter.get_messages_paginated(session_id, cursor, limit)
        if not items:
            return [], next_cursor
        messages: list[dict[str, Any]] = []
        for raw in reversed(items):
            events = raw.get("events") or []
            if not isinstance(events, list):
                events = [events]
            messages.append(
                {
                    "role": str(raw.get("role", "user")),
                    "content": str(raw.get("content", "")),
                    "mode": str(raw.get("mode", "")),
                    "timestamp": raw.get("timestamp") or str(raw.get("ts", "")),
                    "events": events,
                }
            )
        return messages, next_cursor

    def delete_session(self, session_id: str) -> bool:
        return self._adapter.delete_session(session_id)


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

    @contextlib.contextmanager
    def _with_session(self):
        history = SQLChatMessageHistory(
            session_id="__aggregate__",
            connection=self._connection,
        )
        model = history.sql_model_class
        session_field = getattr(model, history.session_id_field_name)
        with history._make_sync_session() as session:
            yield session, model, session_field, history

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

    def list_sessions(
        self, cursor: str | None, limit: int
    ) -> tuple[list[dict[str, Any]], str | None]:
        offset = 0
        if cursor:
            try:
                offset = max(int(cursor), 0)
            except ValueError:  # pragma: no cover - defensive
                offset = 0

        with self._lock:
            with self._with_session() as (session, model, session_field, history):
                from sqlalchemy import func

                subquery = (
                    session.query(
                        session_field.label("session_id"),
                        func.max(model.id).label("last_id"),
                    )
                    .group_by(session_field)
                    .subquery()
                )

                rows: list[Any] = (
                    session.query(model)
                    .join(subquery, model.id == subquery.c.last_id)
                    .order_by(model.id.desc())
                    .all()
                )

        sessions: list[dict[str, Any]] = []
        for row in rows:
            message = history.converter.from_sql_model(row)
            session_id = getattr(row, history.session_id_field_name)
            additional = getattr(message, "additional_kwargs", {}) or {}
            timestamp = str(additional.get("timestamp") or "")
            mode = str(additional.get("mode") or "llm")
            role = getattr(message, "type", "human")
            if role == "ai":
                role = "assistant"
            elif role == "human":
                role = "user"
            preview = message.content[:200]
            sessions.append(
                {
                    "session_id": session_id,
                    "updated_at": timestamp,
                    "mode": mode,
                    "preview": preview,
                    "last_message": {"role": role, "content": message.content},
                }
            )

        if offset >= len(sessions):
            return [], None

        upper = offset + max(limit, 1)
        page = sessions[offset:upper]
        next_cursor = str(upper) if upper < len(sessions) else None
        return page, next_cursor

    def get_messages_paginated(
        self,
        session_id: str,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[dict[str, Any]], str | None]:
        if not session_id:
            return [], None

        before_id: int | None = None
        if cursor:
            try:
                before_id = max(int(cursor), 0)
            except ValueError:  # pragma: no cover - defensive
                before_id = None

        with self._lock:
            with self._with_session() as (session, model, session_field, history):
                query = (
                    session.query(model)
                    .filter(session_field == session_id)
                    .order_by(model.id.desc())
                )
                if before_id:
                    query = query.filter(model.id < before_id)
                rows: list[Any] = query.limit(max(limit, 1) + 1).all()

        if not rows:
            return [], None

        has_more = len(rows) > limit
        rows = rows[:limit]
        converter_history = SQLChatMessageHistory(
            session_id=session_id,
            connection=self._connection,
        )
        converter = converter_history.converter

        messages = []
        for record in reversed(rows):
            message = converter.from_sql_model(record)
            role = getattr(message, "type", "human")
            if role == "ai":
                role = "assistant"
            elif role == "human":
                role = "user"
            additional = getattr(message, "additional_kwargs", {}) or {}
            events = additional.get("events") or []
            if not isinstance(events, list):
                events = [events]
            messages.append(
                {
                    "role": role,
                    "content": message.content,
                    "mode": additional.get("mode", ""),
                    "timestamp": additional.get("timestamp", ""),
                    "events": events,
                }
            )

        next_cursor = str(rows[-1].id) if has_more else None
        return messages, next_cursor

    def delete_session(self, session_id: str) -> bool:
        if not session_id:
            return False
        with self._lock:
            history = self._message_history(session_id)
            messages = list(history.messages)
            if not messages:
                return False
            history.clear()
        return True


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

    async def list_sessions(
        self,
        *,
        cursor: str | None = None,
        limit: int = _SESSION_PAGE_SIZE,
    ) -> tuple[list[dict[str, Any]], str | None]:
        page_size = limit if limit and limit > 0 else _SESSION_PAGE_SIZE
        return await self._call_backend("list_sessions", cursor, page_size)

    async def get_session_messages(
        self,
        session_id: str,
        *,
        cursor: str | None = None,
        limit: int = _MESSAGE_PAGE_SIZE,
    ) -> tuple[list[dict[str, Any]], str | None]:
        if not session_id:
            return [], None
        page_size = limit if limit and limit > 0 else _MESSAGE_PAGE_SIZE
        return await self._call_backend(
            "get_messages_paginated",
            session_id,
            cursor,
            page_size,
        )

    async def delete_session(self, session_id: str) -> bool:
        if not session_id:
            return False
        return await self._call_backend("delete_session", session_id)

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


async def list_sessions(
    *, cursor: str | None = None, limit: int = _SESSION_PAGE_SIZE
) -> tuple[list[dict[str, Any]], str | None]:
    try:
        return await _store().list_sessions(cursor=cursor, limit=limit)
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to list chat sessions")
        return [], None


async def get_session_messages(
    session_id: str,
    *,
    cursor: str | None = None,
    limit: int = _MESSAGE_PAGE_SIZE,
) -> tuple[list[dict[str, Any]], str | None]:
    if not session_id:
        return [], None
    try:
        return await _store().get_session_messages(
            session_id,
            cursor=cursor,
            limit=limit,
        )
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to load messages for session %s", session_id)
        return [], None


async def delete_session(session_id: str) -> bool:
    if not session_id:
        return False
    try:
        return await _store().delete_session(session_id)
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to delete session %s", session_id)
        return False
