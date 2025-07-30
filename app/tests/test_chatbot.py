import pytest
import httpx

from pydantic import ValidationError

from app.schema import ChatInput
from app.services.chatbot import DummyChatBot


def test_chat_input_validation():
    data = ChatInput(message="hello")
    assert data.message == "hello"

    with pytest.raises(ValidationError):
        ChatInput(message="")


@pytest.mark.asyncio
async def test_dummy_chatbot_stream():
    bot = DummyChatBot()
    tokens = [token async for token in bot.stream_chat("foo bar")]
    assert tokens == ["foo", "bar"]


@pytest.mark.asyncio
async def test_fetch_status():
    async def handler(request: httpx.Request) -> httpx.Response:  # type: ignore
        return httpx.Response(200)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        bot = DummyChatBot(client=client)
        status = await bot.fetch_status("http://test")
        assert status == 200
