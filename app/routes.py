from flask import Blueprint, Response, current_app

from .decorators import log_call, validate
from .schema import ChatInput

chat_bp = Blueprint("chat", __name__)


@chat_bp.route("/chat", methods=["POST"])
@log_call
@validate(ChatInput)
async def chat_endpoint(data: ChatInput) -> Response:
    async def generate() -> str:
        async for token in current_app.config["CHATBOT"].stream_chat(data.message):
            yield token

    return Response(generate(), mimetype="text/plain")
