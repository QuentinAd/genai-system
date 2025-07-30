# app/routes.py
from quart import Blueprint, Response, current_app

from .decorators import log_call, validate
from .schema import ChatInput

chat_bp = Blueprint("chat", __name__)


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
