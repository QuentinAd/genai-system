"""Lazy-loading facade for service modules."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

__all__ = [
    "ChatBotBase",
    "DummyChatBot",
    "HiRAGService",
    "OpenAIChatBot",
    "RAGChatBot",
    "load_retriever_tool",
    "ChatHistoryStore",
    "DynamoChatHistoryBackend",
    "SQLiteChatHistoryBackend",
    "get_history",
    "append_message",
]

_ATTR_MODULE_MAP = {
    "ChatBotBase": "app.services.base",
    "DummyChatBot": "app.services.base",
    "HiRAGService": "app.services.hirag",
    "OpenAIChatBot": "app.services.openai",
    "RAGChatBot": "app.services.rag",
    "load_retriever_tool": "app.services.rag",
    "ChatHistoryStore": "app.services.chat_history_store",
    "DynamoChatHistoryBackend": "app.services.chat_history_store",
    "SQLiteChatHistoryBackend": "app.services.chat_history_store",
    "get_history": "app.services.chat_history_store",
    "append_message": "app.services.chat_history_store",
}


def __getattr__(name: str) -> Any:
    try:
        module_name = _ATTR_MODULE_MAP[name]
    except KeyError as exc:  # pragma: no cover - protective fallback
        raise AttributeError(f"module 'app.services' has no attribute {name!r}") from exc
    module = import_module(module_name)
    value = getattr(module, name)
    globals()[name] = value
    return value


if TYPE_CHECKING:  # pragma: no cover - import for type checkers only
    from .base import ChatBotBase, DummyChatBot
    from .chat_history_store import (
        ChatHistoryStore,
        DynamoChatHistoryBackend,
        SQLiteChatHistoryBackend,
        append_message,
        get_history,
    )
    from .hirag import HiRAGService
    from .openai import OpenAIChatBot
    from .rag import RAGChatBot, load_retriever_tool
