from quart import Quart

from .routes import chat_bp

# Select chatbot based on Chroma index presence or environment variable
import os
from .services.chatbot import OpenAIChatBot, RAGChatBot
from .services.agent import AgentRunner, build_retriever


def create_app(chatbot: OpenAIChatBot | None = None) -> Quart:
    app = Quart(__name__)
    if chatbot is None:
        # Determine candidate directories for Chroma store
        candidates: list[str] = []
        # environment override
        index_env = os.getenv("RAG_INDEX_PATH")
        if index_env:
            candidates.append(index_env)
        # default container path
        candidates.append("data")
        # default local path
        candidates.append("data-pipeline/data")
        # select first valid Chroma directory (contains sqlite + index data)
        selected: str | None = None
        for idx in candidates:
            dir_path = idx
            # If a file path was provided earlier, normalize to directory
            if os.path.isfile(dir_path):
                dir_path = os.path.dirname(dir_path)
            # Heuristic: Chroma persists under a folder; accept folder existence
            if os.path.isdir(dir_path) and os.path.exists(os.path.join(dir_path, "chroma")):
                selected = os.path.join(dir_path, "chroma")
                break
        if selected:
            print(f"[INFO] Using RAGChatBot with Chroma directory: {selected}")
            chatbot = RAGChatBot(index_path=selected)
            # Initialize Agent with retriever tool backed by the same index
            try:
                retriever_fn = build_retriever(selected)
                app.config["AGENT"] = AgentRunner(retriever_fn)
                print("[INFO] LangGraph Agent initialized")
            except Exception as e:
                print(f"[WARN] Failed to init LangGraph Agent: {e}")
                app.config["AGENT"] = None
        else:
            chatbot = OpenAIChatBot()
            app.config["AGENT"] = None
    else:
        # If custom chatbot is injected, do not configure agent by default
        app.config["AGENT"] = None

    app.config["CHATBOT"] = chatbot
    app.register_blueprint(chat_bp)
    return app
