from __future__ import annotations

import asyncio
from typing import AsyncGenerator

import httpx
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain.schema import HumanMessage
from langchain_community.vectorstores import FAISS
from langchain.tools.retriever import create_retriever_tool
from langchain.memory import ConversationBufferMemory
from langchain.agents import AgentExecutor, create_openai_functions_agent


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
        model_name: str = "gpt-3.5-turbo",
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


def load_faiss_retriever_tool(index_path: str, embeddings: OpenAIEmbeddings):
    """Return a LangChain tool that searches the FAISS index."""
    vectorstore = FAISS.load_local(
        index_path,
        embeddings,
        allow_dangerous_deserialization=True,
    )
    retriever = vectorstore.as_retriever()
    return create_retriever_tool(
        retriever,
        "faiss_search",
        "Searches documents indexed in FAISS",
    )


class RAGChatBot(OpenAIChatBot):
    """Chatbot that uses tool calling with a FAISS retriever and conversation memory."""

    def __init__(self, index_path: str, **kwargs) -> None:
        super().__init__(**kwargs)
        embeddings = OpenAIEmbeddings()
        tool = load_faiss_retriever_tool(index_path, embeddings)
        memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
        agent = create_openai_functions_agent(self.llm, [tool], memory)
        self.executor = AgentExecutor(agent=agent, tools=[tool], memory=memory)

    async def stream_chat(self, message: str) -> AsyncGenerator[str, None]:
        result = await self.executor.ainvoke({"input": message})
        yield result.get("output", "")
