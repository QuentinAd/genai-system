from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Mapping, Sequence
from typing import Any, AsyncGenerator

import httpx

from langchain_core.language_models.base import BaseLanguageModel
from langchain_core.runnables.config import RunnableConfig


logger = logging.getLogger(__name__)

_TOKEN_EVENT_NAMES = {"on_chat_model_stream", "on_chat_token_stream"}
_TOKEN_INCLUDE_NAMES = _TOKEN_EVENT_NAMES | {"token"}


def _call_if_callable(value: Any) -> Any:
    if callable(value):
        try:
            return value()
        except TypeError:
            return value
    return value


def _chunk_to_text(chunk: Any) -> str:
    """Best-effort extraction of text content from LangChain chunks."""
    if chunk is None:
        return ""
    if isinstance(chunk, str):
        return chunk
    if isinstance(chunk, bytes):
        return chunk.decode()

    for attribute in ("content", "text"):
        value = getattr(chunk, attribute, None)
        if value is None:
            continue
        value = _call_if_callable(value)
        if isinstance(value, bytes):
            value = value.decode()
        if isinstance(value, str) and value:
            return value
        if value:
            return str(value)

    message = getattr(chunk, "message", None)
    if message is not None:
        text = _chunk_to_text(message)
        if text:
            return text

    return ""


def _ensure_newline(payload: str) -> str:
    return payload if payload.endswith("\n") else f"{payload}\n"


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value == ""
    if isinstance(value, (Sequence, set)) and not isinstance(value, (str, bytes)):
        return len(value) == 0
    if isinstance(value, Mapping):
        return len(value) == 0
    return False


def _clean_event_payload(value: Any) -> Any:
    if isinstance(value, Mapping):
        cleaned = {key: _clean_event_payload(val) for key, val in value.items()}
        return {key: val for key, val in cleaned.items() if not _is_empty(val)}
    if isinstance(value, (list, tuple)):
        cleaned_list = [_clean_event_payload(item) for item in value]
        return [item for item in cleaned_list if not _is_empty(item)]
    if isinstance(value, bytes):
        return value.decode()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value

    text = _chunk_to_text(value)
    if text:
        return text

    return str(value)


def _normalise_event(value: Any) -> Mapping | None:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    if isinstance(value, Mapping):
        return value
    return None


def _extract_token(data: Mapping[str, Any]) -> str:
    chunk = data.get("chunk")
    token_text = _chunk_to_text(chunk)
    if token_text:
        return token_text

    token_payload = data.get("token")
    if isinstance(token_payload, Mapping):
        for key in ("text", "content", "value"):
            field = token_payload.get(key)
            if isinstance(field, str) and field:
                return field
    elif isinstance(token_payload, (str, bytes)):
        return token_payload.decode() if isinstance(token_payload, bytes) else token_payload

    return ""


def _serialize_event(event: Any, include: set[str] | None) -> str | None:
    logger.debug("serialize_event include=%s", include)
    normalised = _normalise_event(event)
    if normalised is None:
        return None

    event_name = normalised.get("event")
    if isinstance(event_name, str) and event_name in _TOKEN_EVENT_NAMES:
        data = normalised.get("data")
        token = _extract_token(data) if isinstance(data, Mapping) else ""
        token_allowed = include is None or bool(
            (_TOKEN_INCLUDE_NAMES | {"all", "all_events"}) & include
        )
        if token and token_allowed:
            logger.debug("emitting token event: %s", token)
            return _ensure_newline(json.dumps({"event": "token", "data": token}))
        return None

    if include is not None and not {"all", "all_events"} & include:
        logger.debug("include filter active=%s", include)
        if not isinstance(event_name, str) or event_name not in include:
            return None

    cleaned = _clean_event_payload(normalised)
    return _ensure_newline(json.dumps(cleaned))


class ChatBotBase:
    """Base chatbot with streaming helpers and shared HTTP client."""

    def __init__(
        self,
        model_name: str,
        temperature: float = 0.0,
        client: httpx.AsyncClient | None = None,
        llm: BaseLanguageModel | None = None,
    ) -> None:
        self.model_name = model_name
        self.temperature = temperature
        self.client = client or httpx.AsyncClient()
        self.llm = llm

    def build_request(self, message: str) -> Any:
        """Prepare the request payload sent to the underlying LLM."""
        return message

    async def stream_chat(
        self,
        message: str,
        *,
        config: RunnableConfig | None = None,
    ) -> AsyncGenerator[str, None]:
        if self.llm is None:
            raise NotImplementedError("Subclasses without an LLM must override stream_chat")

        request = self.build_request(message)
        call_kwargs = {"config": config} if config is not None else {}

        stream_fn = getattr(self.llm, "astream", None)
        if callable(stream_fn):
            async for chunk in stream_fn(request, **call_kwargs):
                text = _chunk_to_text(chunk)
                if text:
                    yield text
            return

        sync_stream_fn = getattr(self.llm, "stream", None)
        if callable(sync_stream_fn):
            for chunk in sync_stream_fn(request, **call_kwargs):
                text = _chunk_to_text(chunk)
                if text:
                    yield text
            return

        invoke_fn = getattr(self.llm, "invoke", None)
        if callable(invoke_fn):
            result = invoke_fn(request, **call_kwargs)
            text = _chunk_to_text(result)
            if text:
                yield text
            return

        raise NotImplementedError("The provided LLM does not support streaming or invoke")

    async def stream_events(
        self,
        message: str,
        *,
        config: RunnableConfig | None = None,
        include_events: Sequence[str] | None = None,
    ) -> AsyncGenerator[str, None]:
        allowed = set(include_events) if include_events else None
        logger.info("stream_events start len=%s include=%s", len(message), allowed)

        if self.llm is not None:
            request = self.build_request(message)
            call_kwargs = {"config": config} if config is not None else {}
            event_stream = getattr(self.llm, "astream_events", None)
            if callable(event_stream):
                emitted = False
                async for event in event_stream(request, **call_kwargs):
                    serialized_event = _serialize_event(event, allowed)
                    logger.debug("raw event=%s serialized=%s", event, serialized_event)
                    if serialized_event:
                        emitted = True
                        yield serialized_event
                if emitted:
                    logger.info("stream_events emitted via llm events")
                    return

        def _event_allowed(name: str) -> bool:
            if allowed is None:
                return True
            if {"all", "all_events"} & allowed:
                return True
            return name in allowed

        should_stream_tokens = allowed is None or bool(_TOKEN_INCLUDE_NAMES & allowed)

        logger.info("fallback to stream_chat token streaming")
        collected_tokens: list[str] = []
        emitted = False

        if _event_allowed("on_chat_model_start"):
            payload = _ensure_newline(
                json.dumps({"event": "on_chat_model_start", "data": {"input": message}})
            )
            logger.debug("fallback start payload=%s", payload)
            yield payload
            emitted = True

        async for token in self.stream_chat(message, config=config):
            if not token:
                continue
            collected_tokens.append(token)
            if should_stream_tokens:
                logger.debug("fallback token=%s", token)
                yield token
                emitted = True

        if _event_allowed("on_chat_model_end"):
            payload = _ensure_newline(
                json.dumps(
                    {
                        "event": "on_chat_model_end",
                        "data": {"output": "".join(collected_tokens)},
                    }
                )
            )
            logger.debug("fallback end payload=%s", payload)
            yield payload
            emitted = True

        if emitted:
            logger.info("stream_events emitted via token fallback")
            return

        logger.info("no events emitted; tokens disabled by include filter")

    async def fetch_status(self, url: str) -> int:
        """Fetch a URL using httpx to demonstrate async HTTP calls."""
        response = await self.client.get(url)
        return response.status_code

    async def aclose(self) -> None:
        await self.client.aclose()

    def model_info(self) -> dict[str, Any]:
        """Return basic model configuration."""
        info = {
            "model_name": self.model_name,
            "temperature": self.temperature,
            "type": self.__class__.__name__,
        }
        if self.llm is not None:
            info["llm"] = self.llm.__class__.__name__
        return info

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(model_name={self.model_name!r})"


class DummyChatBot(ChatBotBase):
    """Simplified bot for tests."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        super().__init__("dummy", client=client)

    async def stream_chat(
        self,
        message: str,
        *,
        config: RunnableConfig | None = None,
    ) -> AsyncGenerator[str, None]:
        for word in message.split():
            yield word
            await asyncio.sleep(0)
