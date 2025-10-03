from __future__ import annotations

import json
from typing import AsyncGenerator

from quart import Blueprint, Response, current_app, jsonify, request

from .decorators import log_call, validate
from .schema import ChatInput
from .services import ChatBotBase


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


def create_chat_blueprint(chatbot: ChatBotBase) -> Blueprint:
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

        allowed_events: list[str] | None
        if include_events:
            allowed_set = set(include_events)
            allowed_set.add("token")
            allowed_events = sorted(allowed_set)
        else:
            allowed_events = None

        include_log = ",".join(allowed_events) if allowed_events else "<all>"
        current_app.logger.debug(
            "chat_endpoint stream_mode=%s include=%s", stream_mode, include_log
        )

        async def event_iter():
            async for event in chatbot.stream_events(
                data.message,
                include_events=allowed_events,
            ):
                yield event

        if stream_mode == "tokens":

            async def generate_tokens() -> AsyncGenerator[bytes, None]:
                async for event in event_iter():
                    line = _ensure_ndjson_line(event)
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if payload.get("event") != "token":
                        continue
                    token = payload.get("data")
                    if isinstance(token, str) and token:
                        yield token.encode()

            return Response(generate_tokens(), content_type="text/plain")

        async def generate_events() -> AsyncGenerator[str, None]:
            async for event in event_iter():
                yield _ensure_ndjson_line(event)

        return Response(generate_events(), content_type="application/x-ndjson")

    return chat_bp
