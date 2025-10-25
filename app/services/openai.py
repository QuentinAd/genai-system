from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import httpx
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from .base import ChatBotBase
from app.settings import settings


def _normalise_history_entry(
    entry: Mapping[str, Any] | Sequence[Any] | str,
) -> tuple[str, str]:
    if isinstance(entry, Mapping):
        role = str(entry.get("role", "user")).strip().lower() or "user"
        content = str(entry.get("content", "")).strip()
        return role, content
    if isinstance(entry, Sequence) and not isinstance(entry, (str, bytes)):
        role = str(entry[0] if entry else "user").strip().lower() or "user"
        content = str(entry[1] if len(entry) > 1 else "").strip()
        return role, content
    return "user", str(entry).strip()


class OpenAIChatBot(ChatBotBase):
    """Chatbot using OpenAI via LangChain."""

    def __init__(
        self,
        model_name: str = "gpt-4.1",
        temperature: float = 0.0,
        client: httpx.AsyncClient | None = None,
        **llm_kwargs: Any,
    ) -> None:
        if settings.openai_api_key and "api_key" not in llm_kwargs:
            llm_kwargs["api_key"] = settings.openai_api_key
        if settings.openai_api_base and "base_url" not in llm_kwargs:
            llm_kwargs["base_url"] = settings.openai_api_base
        llm = ChatOpenAI(
            model_name=model_name,
            temperature=temperature,
            streaming=True,
            **llm_kwargs,
        )
        super().__init__(model_name, temperature, client, llm=llm)

    def build_request(
        self,
        message: str,
        *,
        history: Sequence[Mapping[str, Any] | Sequence[Any] | str] | None = None,
    ) -> list[BaseMessage]:
        messages: list[BaseMessage] = []
        for entry in history or []:
            role, content = _normalise_history_entry(entry)
            if not content:
                continue
            if role == "assistant":
                message_cls: type[BaseMessage] = AIMessage
            elif role == "system":
                message_cls = SystemMessage
            else:
                message_cls = HumanMessage
            messages.append(message_cls(content=content))
        messages.append(HumanMessage(content=message))
        return messages
