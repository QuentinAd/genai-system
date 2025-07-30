from flask import Flask

from .routes import chat_bp
from .services.chatbot import OpenAIChatBot


def create_app(chatbot: OpenAIChatBot | None = None) -> Flask:
    app = Flask(__name__)
    if chatbot is None:
        chatbot = OpenAIChatBot()
    app.config["CHATBOT"] = chatbot
    app.register_blueprint(chat_bp)
    return app
