from quart import Blueprint, Response, jsonify

from .decorators import log_call, validate
from .schema import ChatInput
from .services import ChatBotBase


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
        """Stream chatbot tokens as plain text."""

        async def generate():
            async for token in chatbot.stream_chat(data.message):
                yield token.encode()

        return Response(generate(), content_type="text/plain")

    return chat_bp
