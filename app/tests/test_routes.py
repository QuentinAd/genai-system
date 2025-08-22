import pytest

from app import create_app
from app.services.chatbot import DummyChatBot


@pytest.mark.asyncio
async def test_chat_endpoint(tmp_path):
    bot = DummyChatBot()
    app = create_app(chatbot=bot)
    async with app.test_client() as client:
        resp = await client.post("/chat", json={"message": "hello world"})
        text = await resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert text == "helloworld"


@pytest.mark.asyncio
async def test_chat_endpoint_invalid_json(tmp_path):
    bot = DummyChatBot()
    app = create_app(chatbot=bot)
    async with app.test_client() as client:
        resp = await client.post("/chat", data="not json", headers={"Content-Type": "text/plain"})
        assert resp.status_code == 400
        data = await resp.get_json()
        assert data == {"error": "Invalid request data"}


class FailingChatBot(DummyChatBot):
    def stream_chat(self, message: str):  # pragma: no cover - simple
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_chat_endpoint_stream_error(tmp_path):
    bot = FailingChatBot()
    app = create_app(chatbot=bot)
    async with app.test_client() as client:
        resp = await client.post("/chat", json={"message": "hi"})
        assert resp.status_code == 500
        text = await resp.get_data(as_text=True)
        assert "Internal Server Error" in text
