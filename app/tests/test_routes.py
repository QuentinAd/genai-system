import pytest

from app import create_app
from app.services import DummyChatBot


@pytest.mark.asyncio
async def test_chat_endpoint():
    bot = DummyChatBot()
    app = create_app(chatbot=bot)
    async with app.test_client() as client:
        resp = await client.post("/chat", json={"message": "hello world"})
        text = await resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert text == "helloworld"


@pytest.mark.asyncio
async def test_chat_endpoint_invalid_json():
    bot = DummyChatBot()
    app = create_app(chatbot=bot)
    async with app.test_client() as client:
        resp = await client.post("/chat", json={"foo": "bar"})
        assert resp.status_code == 400


@pytest.mark.asyncio
async def test_models_endpoint():
    bot = DummyChatBot()
    app = create_app(chatbot=bot)
    async with app.test_client() as client:
        resp = await client.get("/models")
        data = await resp.get_json()
        assert resp.status_code == 200
        assert data["model_name"] == "dummy"
