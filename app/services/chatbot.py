from __future__ import annotations

import asyncio
from typing import AsyncGenerator

import httpx
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain.schema import HumanMessage
from langchain_chroma import Chroma
from langchain.chains import RetrievalQA


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
        model_name: str = "gpt-4.1",
        temperature: float = 0.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(model_name, temperature, client)
        self.llm = ChatOpenAI(
            model_name=model_name,
            temperature=temperature,
            streaming=True,
        )

    async def stream_chat(self, message: str) -> AsyncGenerator[str, None]:
        async for chunk in self.llm.astream([HumanMessage(content=message)]):
            yield chunk.content or ""


class DummyChatBot(ChatBotBase):
    """Simplified bot for tests."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        super().__init__("dummy", client=client)

    async def stream_chat(self, message: str) -> AsyncGenerator[str, None]:
        for word in message.split():
            yield word
            await asyncio.sleep(0)


def load_retriever_tool(index_path: str, embeddings: OpenAIEmbeddings):
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
    """Chatbot that uses Chroma retriever and conversation memory."""

    def __init__(self, index_path: str, **kwargs) -> None:
        super().__init__(**kwargs)
        import os
        from langchain.schema import Document
        from langchain.text_splitter import RecursiveCharacterTextSplitter

        embeddings = OpenAIEmbeddings()
        # If a Chroma directory exists, load it; otherwise build from raw_text.txt
        if os.path.basename(index_path) == "chroma":
            raw_text_path = os.path.join(os.path.dirname(index_path), "raw_text.txt")
        else:
            raw_text_path = os.path.join(index_path, "raw_text.txt")

        if os.path.isdir(index_path):
            # try to open existing persisted store
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

        # limit to top-3 docs to control token usage
        self.retriever = self.vectorstore.as_retriever(search_kwargs={"k": 3})

        # build a RetrievalQA chain with map_reduce to handle chunking & summarization
        self.qa_chain = RetrievalQA.from_chain_type(
            llm=self.llm,
            chain_type="map_reduce",
            retriever=self.retriever,
            return_source_documents=False,
        )

    async def stream_chat(self, message: str) -> AsyncGenerator[str, None]:
        """Generate an answer via RetrievalQA (handles retrieval, chunking & summarization)."""
        result = await self.qa_chain.ainvoke(message)
        answer = result.get("result") if isinstance(result, dict) else result
        yield answer
