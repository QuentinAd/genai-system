from langchain_community.vectorstores import Chroma
from langchain_core.embeddings import FakeEmbeddings

from app.services import load_retriever_tool


def test_load_retriever_tool(tmp_path):
    embeddings = FakeEmbeddings(size=3)
    # Build and persist a small Chroma store
    store_dir = tmp_path / "chroma"
    Chroma.from_texts(
        [
            "hello world",
        ],
        embeddings,
        persist_directory=str(store_dir),
    )

    tool = load_retriever_tool(str(store_dir), embeddings)
    assert tool.run("hello") == "hello world"
