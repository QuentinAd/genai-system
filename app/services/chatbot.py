from __future__ import annotations

import asyncio
from typing import AsyncGenerator

import httpx
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage


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
