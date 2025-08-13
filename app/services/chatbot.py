from __future__ import annotations

import asyncio
from typing import AsyncGenerator

import httpx
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.messages import HumanMessage
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate


class ChatBotBase:
    """Base chatbot with streaming and HTTP helpers."""

    def __init__(
        self,
        model_name: str,
        temperature: float = 0.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model_name = model_name
        self.temperature = temperature
        self.client = client or httpx.AsyncClient()

    async def stream_chat(self, message: str) -> AsyncGenerator[str, None]:
        raise NotImplementedError

    async def fetch_status(self, url: str) -> int:
        """Fetch a URL using httpx to demonstrate async HTTP calls."""
        response = await self.client.get(url)
        return response.status_code

    async def aclose(self) -> None:
        await self.client.aclose()

    def __repr__(self) -> str:  # pragma: no cover - simple dunder method
        return f"{self.__class__.__name__}(model_name={self.model_name!r})"


class OpenAIChatBot(ChatBotBase):
    """Chatbot using OpenAI via LangChain."""

    def __init__(
        self,
        model_name: str = "gpt-4o-mini",
        temperature: float = 0.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(model_name, temperature, client)
        # Use current v0.3+ style param `model`
        self.llm = ChatOpenAI(
            model=model_name,
            temperature=temperature,
            streaming=True,
        )

    async def stream_chat(self, message: str) -> AsyncGenerator[str, None]:
        async for chunk in self.llm.astream([HumanMessage(content=message)]):
            yield getattr(chunk, "content", "") or ""


class DummyChatBot(ChatBotBase):
    """Simplified bot for tests."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        super().__init__("dummy", client=client)

    async def stream_chat(self, message: str) -> AsyncGenerator[str, None]:
        for word in message.split():
            yield word
            await asyncio.sleep(0)


def load_retriever_tool(index_path: str, embeddings: Embeddings):
    """Return a simple tool that searches the Chroma collection."""
    vectorstore = Chroma(
        persist_directory=index_path,
        embedding_function=embeddings,
    )
    retriever = vectorstore.as_retriever()

    class RetrieverTool:
        """Simple tool wrapping retriever."""

        def run(self, query: str) -> str:
            docs = retriever.get_relevant_documents(query)
            return docs[0].page_content if docs else ""

    return RetrieverTool()


class RAGChatBot(OpenAIChatBot):
    """RAG chatbot implemented with LangChain v0.3 chains (no agents)."""

    def __init__(self, index_path: str, **kwargs) -> None:
        super().__init__(**kwargs)
        import os

        embeddings = OpenAIEmbeddings()
        # Resolve raw_text for bootstrap if needed
        if os.path.basename(index_path) == "chroma":
            raw_text_path = os.path.join(os.path.dirname(index_path), "raw_text.txt")
        else:
            raw_text_path = os.path.join(index_path, "raw_text.txt")

        if os.path.isdir(index_path):
            # Load existing persisted store
            self.vectorstore = Chroma(
                persist_directory=index_path,
                embedding_function=embeddings,
            )
        else:
            # Build a new store from raw text if available
            try:
                with open(raw_text_path, encoding="utf-8") as f:
                    text = f.read()
            except OSError:
                text = ""
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=1000,
                chunk_overlap=100,
            )
            texts = splitter.split_text(text)
            docs = [Document(page_content=chunk) for chunk in texts]
            os.makedirs(index_path, exist_ok=True)
            self.vectorstore = Chroma.from_documents(
                documents=docs,
                embedding=embeddings,
                persist_directory=index_path,
            )
            try:
                self.vectorstore.persist()
            except Exception:
                pass

        # Top-k retrieval
        self.retriever = self.vectorstore.as_retriever(search_kwargs={"k": 3})

        # Build the QA chain using the recommended v0.3 helpers (stuff documents)
        qa_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are an assistant for question-answering tasks. Use the provided context "
                    "to answer the question. If you don't know the answer, say you don't know.\n\n"
                    "Context:\n{context}",
                ),
                ("human", "{input}"),
            ]
        )
        question_answer_chain = create_stuff_documents_chain(self.llm, qa_prompt)
        self.rag_chain = create_retrieval_chain(self.retriever, question_answer_chain)

    async def stream_chat(self, message: str) -> AsyncGenerator[str, None]:
        """Stream tokens from the RAG chain using astream_events."""
        # Stream only the chat model tokens to the client
        async for event in self.rag_chain.astream_events(
            {"input": message},
            version="v1",
        ):
            if event.get("event") == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                # chunk is an AIMessageChunk; its `content` is a string or list of parts
                token = getattr(chunk, "content", "") or ""
                if token:
                    yield token
