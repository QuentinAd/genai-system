# app/routes.py
from quart import Blueprint, Response, current_app

from .decorators import log_call, validate
from .schema import ChatInput

chat_bp = Blueprint("chat", __name__)


@chat_bp.get("/health")
@log_call
async def health() -> Response:
    """Basic health check endpoint."""
    return Response("ok/n", content_type="text/plain")


@chat_bp.post("/chat")
@log_call
@validate(ChatInput)
async def chat_endpoint(data: ChatInput) -> Response:
    """
    Stream chatbot tokens as plain text.
    """

    # Instantiate chatbot
    chatbot = current_app.config["CHATBOT"]

    # Async‑generator that yields **bytes**, as per Quart's requirements for streaming responses
    async def generate():
        async for token in chatbot.stream_chat(data.message):
            yield token.encode()

    # Quart treats the async generator as a streamed body
    return Response(generate(), content_type="text/plain")


@chat_bp.post("/agent")
@log_call
@validate(ChatInput)
async def agent_endpoint(data: ChatInput) -> Response:
    """Stream LangGraph agent events as NDJSON for real-time UI updates."""
    agent_runner = current_app.config.get("AGENT")

    if agent_runner is None:
        # Fallback: simple stream of final text
        async def fallback():
            yield b'{"type":"final","content":"Agent not configured"}\n'

        return Response(fallback(), content_type="application/x-ndjson")

    async def generate():
        async for chunk in agent_runner.stream(data.message):
            yield chunk

    return Response(generate(), content_type="application/x-ndjson")
