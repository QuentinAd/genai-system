from __future__ import annotations

from typing import AsyncGenerator

import httpx
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage

from .base import ChatBotBase


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
