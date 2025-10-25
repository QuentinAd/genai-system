from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable
from unittest.mock import AsyncMock

import pytest

from app.services.hirag import HiRAGService


@dataclass
class FakeQueryParam:
    mode: str = "hi"
    only_need_context: bool = False
    response_type: str = "Multiple Paragraphs"
    level: int = 2
    top_k: int = 20
    top_m: int = 10


class StubHiRAG:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.aquery: AsyncMock = AsyncMock()
        self.insert_calls: list[list[str]] = []

    def insert(self, documents: Iterable[str]) -> None:
        self.insert_calls.append(list(documents))


def _make_service(monkeypatch, *, storage_kwargs: dict[str, Any] | None = None):
    created: dict[str, StubHiRAG] = {}

    def factory(**kwargs: Any) -> StubHiRAG:
        created["instance"] = StubHiRAG(**kwargs)
        return created["instance"]

    if storage_kwargs is not None:
        monkeypatch.setattr(
            HiRAGService,
            "_local_storage_overrides",
            lambda self: storage_kwargs,
        )

    service = HiRAGService(hirag_cls=factory, query_param_cls=FakeQueryParam)
    return service, created["instance"]


@pytest.mark.asyncio
async def test_constructor_uses_local_storage_when_no_aws(monkeypatch):
    monkeypatch.delenv("AWS_REGION", raising=False)
    storage = {
        "key_string_value_json_storage_cls": "local-kv",
        "vector_db_storage_cls": "local-vector",
        "graph_storage_cls": "local-graph",
    }
    service, stub = _make_service(monkeypatch, storage_kwargs=storage)
    assert service
    assert stub.kwargs["key_string_value_json_storage_cls"] == "local-kv"
    assert stub.kwargs["vector_db_storage_cls"] == "local-vector"
    assert stub.kwargs["graph_storage_cls"] == "local-graph"
    assert "aws_region" not in stub.kwargs


@pytest.mark.asyncio
async def test_constructor_uses_aws_overrides_when_region_set(monkeypatch):
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    overrides = {
        "key_string_value_json_storage_cls": "aws-kv",
        "vector_db_storage_cls": "aws-vector",
        "graph_storage_cls": "aws-graph",
    }

    def fake_overrides(self) -> dict[str, Any]:
        return overrides

    monkeypatch.setattr(HiRAGService, "_load_aws_storage_overrides", fake_overrides)

    created: dict[str, StubHiRAG] = {}

    def factory(**kwargs: Any) -> StubHiRAG:
        created["instance"] = StubHiRAG(**kwargs)
        return created["instance"]

    service = HiRAGService(hirag_cls=factory, query_param_cls=FakeQueryParam)
    stub = created["instance"]

    assert service
    assert stub.kwargs["key_string_value_json_storage_cls"] == "aws-kv"
    assert stub.kwargs["vector_db_storage_cls"] == "aws-vector"
    assert stub.kwargs["graph_storage_cls"] == "aws-graph"
    assert stub.kwargs["aws_region"] == "us-west-2"


@pytest.mark.asyncio
async def test_index_documents_invokes_insert(monkeypatch):
    service, stub = _make_service(monkeypatch, storage_kwargs={})

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr("app.services.hirag.asyncio.to_thread", fake_to_thread)

    docs = ["doc-a", "doc-b"]
    await service.index_documents(docs)

    assert stub.insert_calls == [docs]


@pytest.mark.asyncio
async def test_chat_uses_hierarchical_mode_by_default(monkeypatch):
    context_block = """-----Source Documents-----\n```csv\n"id", "content"\n"0", "Chunk A"\n```\n"""
    stub_response = "Hierarchical answer"
    service, stub = _make_service(monkeypatch, storage_kwargs={})
    stub.aquery.side_effect = [context_block, stub_response]

    history = [
        {"role": "user", "content": "Earlier question"},
        {"role": "assistant", "content": "Earlier answer"},
    ]

    result = await service.chat("What is new?", "session-1", mode="", history=history)

    first_call = stub.aquery.await_args_list[0].args
    second_call = stub.aquery.await_args_list[1].args

    assert first_call[1].mode == "hi"
    assert first_call[1].only_need_context is True
    assert second_call[1].mode == "hi"
    assert second_call[1].only_need_context is False

    assert result["answer"] == stub_response
    assert result["references"] == [{"id": "0", "content": "Chunk A"}]
    assert "Chunk A" in result["prompt"]
    assert "references:" in result["prompt"].lower()


@pytest.mark.asyncio
async def test_chat_supports_naive_mode(monkeypatch):
    context_block = """-----Source Documents-----\n```csv\n"id", "content"\n"0", "Snippet"\n```\n"""
    service, stub = _make_service(monkeypatch, storage_kwargs={})
    stub.aquery.side_effect = [context_block, "Naive answer"]

    result = await service.chat("plain question", "session-2", mode="naive", history=None)

    first_call = stub.aquery.await_args_list[0].args[1]
    second_call = stub.aquery.await_args_list[1].args[1]

    assert first_call.mode == "naive"
    assert first_call.only_need_context is True
    assert second_call.mode == "naive"
    assert second_call.only_need_context is False
    assert result["answer"] == "Naive answer"
    assert "references:" in result["prompt"].lower()


@pytest.mark.asyncio
async def test_chat_rejects_unknown_mode(monkeypatch):
    service, stub = _make_service(monkeypatch, storage_kwargs={})
    stub.aquery.side_effect = ["", ""]

    with pytest.raises(ValueError):
        await service.chat("question", "session-3", mode="invalid", history=None)
