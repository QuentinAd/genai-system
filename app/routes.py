from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, AsyncGenerator

from quart import Blueprint, Response, current_app, jsonify, request

from .decorators import log_call, validate
from .schema import ChatInput
from .services import ChatBotBase, HiRAGService, chat_history_store


def _route_config(route: str) -> dict[str, Any]:
    return {"metadata": {"route": route}}


def _ensure_ndjson_line(value: str | bytes) -> str:
    if isinstance(value, bytes):
        text = value.decode()
    else:
        text = str(value)

    candidate = text.lstrip()
    if candidate.startswith("{") and candidate.rstrip().endswith("}"):
        return text if text.endswith("\n") else f"{text}\n"

    payload = {
        "event": "token",
        "data": text.rstrip("\n"),
    }
    return json.dumps(payload) + "\n"


def _extract_token_text(line: str) -> str | None:
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        text = line.strip()
        return text or None
    if payload.get("event") != "token":
        return None
    token = payload.get("data")
    if isinstance(token, str) and token:
        return token
    return None


def _format_history_entries(
    entries: Sequence[Mapping[str, Any] | Sequence[str] | str],
) -> list[dict[str, str]]:
    formatted: list[dict[str, str]] = []
    for entry in entries:
        if isinstance(entry, Mapping):
            role = str(entry.get("role", "user")).strip() or "user"
            content = str(entry.get("content", "")).strip()
        elif isinstance(entry, Sequence) and not isinstance(entry, (str, bytes)):
            role = str(entry[0] if entry else "user").strip() or "user"
            content = str(entry[1] if len(entry) > 1 else "").strip()
        else:
            role = "user"
            content = str(entry).strip()
        if content:
            formatted.append({"role": role, "content": content})
    return formatted


def _resolve_retrieval_mode(query_args) -> str:
    if "hirag" in query_args:
        return "hi"
    if "rag" in query_args:
        return "naive"
    return ""


def _parse_positive_int(value: str | None, default: int) -> int:
    if not value:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def create_chat_blueprint(
    chatbot: ChatBotBase,
    *,
    hirag_service: HiRAGService | None = None,
) -> Blueprint:
    chat_bp = Blueprint("chat", __name__)

    @chat_bp.get("/health")
    @log_call
    async def health() -> Response:
        """Basic health check endpoint."""
        return Response("ok\n", content_type="text/plain")

    @chat_bp.get("/models")
    async def models() -> Response:
        return jsonify(chatbot.model_info())

    @chat_bp.post("/chat")
    @log_call
    @validate(ChatInput)
    async def chat_endpoint(data: ChatInput) -> Response:
        """Stream chatbot responses as plain tokens or NDJSON events."""

        stream_mode = request.args.get("stream", "events").lower()
        include_arg = request.args.get("include", "")
        include_events = [item.strip() for item in include_arg.split(",") if item.strip()]
        retrieval_mode = _resolve_retrieval_mode(request.args)
        session_id = request.headers.get("Session-Id") or request.cookies.get("Session-Id") or ""
        history = data.history or []
        persisted_history = await chat_history_store.get_history(session_id)

        merged_history: list[Mapping[str, Any] | Sequence[str] | str] = []
        for entry in persisted_history:
            if isinstance(entry, Mapping):
                merged_history.append(dict(entry))
            else:
                merged_history.append(entry)
        for entry in history:
            if isinstance(entry, Mapping):
                merged_history.append(dict(entry))
            elif isinstance(entry, Sequence) and not isinstance(entry, (str, bytes)):
                merged_history.append(list(entry))
            else:
                merged_history.append(entry)

        if retrieval_mode == "hi":
            conversation_mode = "hirag"
        elif retrieval_mode == "naive":
            conversation_mode = "rag"
        else:
            conversation_mode = "llm"

        retrieval_metadata: dict[str, Any] | None = None
        if retrieval_mode:
            if hirag_service is None:
                current_app.logger.warning("HiRAG retrieval requested but service unavailable")
                return jsonify({"error": "Retrieval service unavailable"}), 503
            try:
                retrieval = await hirag_service.chat(
                    data.message,
                    session_id,
                    mode=retrieval_mode,
                    history=merged_history,
                )
            except Exception as exc:  # pragma: no cover - defensive logging
                current_app.logger.exception("HiRAG chat failed: %%s", exc)
                return jsonify({"error": "Retrieval failed"}), 502
            response_mode = conversation_mode if retrieval_mode else "llm"
            retrieval_metadata = {
                "mode": response_mode,
                "session_id": session_id,
                "answer": retrieval.get("answer", ""),
                "context": retrieval.get("context", ""),
                "references": retrieval.get("references", []),
            }

        if session_id:
            await chat_history_store.append_message(
                session_id,
                "user",
                data.message,
                conversation_mode,
            )

        llm_history = _format_history_entries(merged_history)

        allowed_events: list[str] | None
        if include_events:
            allowed_set = set(include_events)
            allowed_set.add("token")
            allowed_events = sorted(allowed_set)
        else:
            allowed_events = None

        include_log = ",".join(allowed_events) if allowed_events else "<all>"
        current_app.logger.debug(
            "chat_endpoint stream_mode=%s include=%s mode=%s",
            stream_mode,
            include_log,
            retrieval_mode or "llm",
        )

        assistant_chunks: list[str] = []

        async def ndjson_event_iter() -> AsyncGenerator[str, None]:
            try:
                async for event in chatbot.stream_events(
                    data.message,
                    config=_route_config("/chat"),
                    include_events=allowed_events,
                    history=llm_history,
                ):
                    line = _ensure_ndjson_line(event)
                    token = _extract_token_text(line)
                    if token:
                        assistant_chunks.append(token)
                    yield line
            finally:
                if session_id and assistant_chunks:
                    assistant_text = "".join(assistant_chunks)
                    await chat_history_store.append_message(
                        session_id,
                        "assistant",
                        assistant_text,
                        conversation_mode,
                    )

        if stream_mode == "tokens":

            async def generate_tokens() -> AsyncGenerator[bytes, None]:
                async for line in ndjson_event_iter():
                    token = _extract_token_text(line)
                    if token:
                        yield token.encode()

            return Response(generate_tokens(), content_type="text/plain")

        async def generate_events() -> AsyncGenerator[str, None]:
            async for line in ndjson_event_iter():
                yield line
            if retrieval_metadata is not None:
                payload = {
                    "event": "retrieval_metadata",
                    "data": retrieval_metadata,
                }
                yield json.dumps(payload) + "\n"

        return Response(generate_events(), content_type="application/x-ndjson")

    @chat_bp.get("/chat_history")
    async def list_chat_history() -> Response:
        cursor = request.args.get("cursor") or None
        limit = _parse_positive_int(request.args.get("limit"), 20)
        sessions, next_cursor = await chat_history_store.list_sessions(
            cursor=cursor,
            limit=limit,
        )
        payload = {
            "sessions": sessions or [],
            "next": next_cursor,
        }
        return jsonify(payload)

    @chat_bp.get("/chat_history/<session_id>")
    async def fetch_chat_history(session_id: str) -> Response:
        cursor = request.args.get("cursor") or None
        limit = _parse_positive_int(request.args.get("limit"), 50)
        messages, next_cursor = await chat_history_store.get_session_messages(
            session_id,
            cursor=cursor,
            limit=limit,
        )
        payload = {
            "messages": messages or [],
            "next": next_cursor,
        }
        return jsonify(payload)

    @chat_bp.delete("/chat_history/<session_id>")
    async def clear_chat_history(session_id: str) -> Response:
        deleted = await chat_history_store.delete_session(session_id)
        if not deleted:
            return jsonify({"error": "Session not found"}), 404
        return Response(status=204)

    return chat_bp
