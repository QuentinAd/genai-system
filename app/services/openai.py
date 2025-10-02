from __future__ import annotations

from typing import Any

import httpx
from langchain.schema import HumanMessage
from langchain_openai import ChatOpenAI

from .base import ChatBotBase
from app.settings import settings


class OpenAIChatBot(ChatBotBase):
    """Chatbot using OpenAI via LangChain."""

    def __init__(
        self,
        model_name: str = "gpt-4.1",
        temperature: float = 0.0,
        client: httpx.AsyncClient | None = None,
        **llm_kwargs: Any,
    ) -> None:
        if settings.openai_api_key and "api_key" not in llm_kwargs:
            llm_kwargs["api_key"] = settings.openai_api_key
        if settings.openai_api_base and "base_url" not in llm_kwargs:
            llm_kwargs["base_url"] = settings.openai_api_base
        llm = ChatOpenAI(
            model_name=model_name,
            temperature=temperature,
            streaming=True,
            **llm_kwargs,
        )
        super().__init__(model_name, temperature, client, llm=llm)

    def build_request(self, message: str) -> list[HumanMessage]:
        return [HumanMessage(content=message)]
