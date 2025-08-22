import logging
import os

from quart import Quart

from .routes import create_chat_blueprint
from .services import ChatBotBase, OpenAIChatBot, RAGChatBot
from .settings import settings

import os

logger = logging.getLogger(__name__)


def create_app(chatbot: ChatBotBase | None = None) -> Quart:
    app = Quart(__name__)
    if chatbot is None:
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
    chat_bp = create_chat_blueprint(chatbot)
    app.register_blueprint(chat_bp)

    @app.after_serving
    async def shutdown() -> None:
        await chatbot.aclose()

    return app
