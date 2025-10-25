from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from quart import Quart

from .settings import settings

if TYPE_CHECKING:
    from .services import ChatBotBase, HiRAGService

logging.basicConfig(
    level=logging.DEBUG if settings.logging_level == "DEBUG" else logging.WARNING,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


def create_app(
    chatbot: ChatBotBase | None = None,
    *,
    hirag_service: HiRAGService | None = None,
) -> Quart:
    from .routes import create_chat_blueprint
    from .services import DummyChatBot, HiRAGService, OpenAIChatBot, RAGChatBot

    app = Quart(__name__)
    if chatbot is None:
        # Allow forcing DummyChatBot via env var for local/dev/testing
        if settings.use_dummy:
            logger.info("Using DummyChatBot due to USE_DUMMY setting")
            chatbot = DummyChatBot()
        else:
            candidates: list[str] = []
            if settings.rag_index_path:
                candidates.append(settings.rag_index_path)
            candidates.append("data")
            candidates.append("data-pipeline/data")
            selected: str | None = None
            for idx in candidates:
                dir_path = idx
                if os.path.isfile(dir_path):
                    dir_path = os.path.dirname(dir_path)
                if os.path.isdir(dir_path) and os.path.exists(os.path.join(dir_path, "chroma")):
                    selected = os.path.join(dir_path, "chroma")
                    break
            if selected:
                logger.info("Using RAGChatBot with Chroma directory: %s", selected)
                chatbot = RAGChatBot(index_path=selected)
            else:
                logger.info("Using default OpenAIChatBot")
                chatbot = OpenAIChatBot()
    if hirag_service is None:
        try:
            hirag_service = HiRAGService()
        except Exception as exc:  # pragma: no cover - optional dependency failures
            logger.warning("HiRAGService unavailable: %s", exc)
            hirag_service = None

    chat_bp = create_chat_blueprint(chatbot, hirag_service=hirag_service)
    app.register_blueprint(chat_bp)

    @app.after_serving
    async def shutdown() -> None:
        await chatbot.aclose()

    return app
