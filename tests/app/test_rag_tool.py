from langchain_community.vectorstores import FAISS
from langchain_core.embeddings import FakeEmbeddings

from app.services.chatbot import load_faiss_retriever_tool


def test_load_faiss_retriever_tool(tmp_path):
    embeddings = FakeEmbeddings(size=3)
    store = FAISS.from_texts(["hello world"], embeddings)
    store.save_local(str(tmp_path))
    tool = load_faiss_retriever_tool(str(tmp_path), embeddings)
    assert tool.run("hello") == "hello world"
