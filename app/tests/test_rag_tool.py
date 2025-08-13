from langchain_chroma import Chroma
from langchain_core.embeddings import FakeEmbeddings

from app.services.chatbot import load_retriever_tool


def test_load_retriever_tool(tmp_path):
    embeddings = FakeEmbeddings(size=3)
    # Build and persist a small Chroma store
    store_dir = tmp_path / "chroma"
    store = Chroma.from_texts(
        [
            "hello world",
        ],
        embeddings,
        persist_directory=str(store_dir),
    )
    try:
        store.persist()
    except Exception:
        pass

    tool = load_retriever_tool(str(store_dir), embeddings)
    assert tool.run("hello") == "hello world"
