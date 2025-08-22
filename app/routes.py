# app/routes.py
import logging

from quart import Blueprint, Response, current_app

from .decorators import log_call, validate
from .schema import ChatInput

logger = logging.getLogger(__name__)

chat_bp = Blueprint("chat", __name__)


@chat_bp.get("/health")
@log_call
async def health() -> Response:
    """Basic health check endpoint."""
    return Response("ok\n", content_type="text/plain")


@chat_bp.post("/chat")
@log_call
@validate(ChatInput)
async def chat_endpoint(data: ChatInput) -> Response:
    """
    Stream chatbot tokens as plain text.
    """

    # Instantiate chatbot
    chatbot = current_app.config["CHATBOT"]
    try:
        stream = chatbot.stream_chat(data.message)

        # Async‑generator that yields **bytes**, as per Quart's requirements for streaming responses
        async def generate():
            try:
                async for token in stream:
                    yield token.encode()
            except Exception:
                logger.exception("Error while streaming chat response")
                raise

        # Quart treats the async generator as a streamed body
        return Response(generate(), content_type="text/plain")
    except Exception:
        logger.exception("Failed to start chat stream")
        return Response("Internal Server Error\n", status=500, content_type="text/plain")
