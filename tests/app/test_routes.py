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
