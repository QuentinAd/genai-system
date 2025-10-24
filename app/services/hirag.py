"""Async wrapper around the vendored HiRAG implementation."""

from __future__ import annotations

import asyncio
import csv
import importlib
import importlib.util
import os
import re
import sys
import types
from dataclasses import replace
from io import StringIO
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


_REPO_ROOT = Path(__file__).resolve().parents[2]
_VENDOR_DIR = _REPO_ROOT / "third_party" / "hhy-huang_hirag"
_VENDOR_PACKAGE = "_hirag_vendor"
_SOURCE_SECTION_PATTERN = re.compile(
    r"-----Source Documents-----\s*```csv\s*(.*?)\s*```",
    re.DOTALL,
)


def _ensure_vendor_package() -> str:
    if _VENDOR_PACKAGE not in sys.modules:
        package = types.ModuleType(_VENDOR_PACKAGE)
        package.__path__ = [str(_VENDOR_DIR)]  # type: ignore[attr-defined]
        sys.modules[_VENDOR_PACKAGE] = package
    return _VENDOR_PACKAGE


def _load_hirag_module():
    package = _ensure_vendor_package()
    return importlib.import_module(f"{package}.hirag")


_LOCAL_STORAGE_CACHE: dict[str, Any] | None = None
_HIRAG_SYMBOLS: tuple[type, type] | None = None


def _load_storage_module():
    module_name = "hirag_aws_storage"
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError:
        module_path = _REPO_ROOT / "data-pipeline" / "dags" / "hirag_aws_storage.py"
        if not module_path.exists():  # pragma: no cover - defensive
            raise
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:  # pragma: no cover - defensive
            raise
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module


def _load_local_storage_overrides() -> dict[str, Any]:
    global _LOCAL_STORAGE_CACHE
    if _LOCAL_STORAGE_CACHE is None:
        storage_pkg = f"{_VENDOR_PACKAGE}.hirag._storage"
        try:
            kv_cls = importlib.import_module(f"{storage_pkg}.kv_json").JsonKVStorage
            vector_cls = importlib.import_module(
                f"{storage_pkg}.vdb_nanovectordb"
            ).NanoVectorDBStorage
            graph_cls = importlib.import_module(f"{storage_pkg}.gdb_networkx").NetworkXStorage
        except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency missing
            missing = getattr(exc, "name", "a required dependency")
            raise RuntimeError(
                f"HiRAG local storage dependencies missing ({missing}). Install the vendor "
                "requirements or configure AWS storage overrides."
            ) from exc
        _LOCAL_STORAGE_CACHE = {
            "key_string_value_json_storage_cls": kv_cls,
            "vector_db_storage_cls": vector_cls,
            "graph_storage_cls": graph_cls,
        }
    return dict(_LOCAL_STORAGE_CACHE)


def _get_vendor_symbols() -> tuple[type, type]:
    global _HIRAG_SYMBOLS
    if _HIRAG_SYMBOLS is None:
        try:
            module = _load_hirag_module()
        except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency missing
            missing = getattr(exc, "name", "required dependency")
            raise RuntimeError(
                f"Unable to load HiRAG vendor package. Missing dependency: {missing}."
            ) from exc
        _HIRAG_SYMBOLS = (module.HiRAG, module.QueryParam)
    return _HIRAG_SYMBOLS


class HiRAGService:
    """High-level service that wraps HiRAG indexing and query flows."""

    def __init__(
        self,
        *,
        hirag: Any | None = None,
        hirag_cls: type | None = None,
        query_param_cls: type | None = None,
        working_dir: str | None = None,
        **hirag_kwargs: Any,
    ) -> None:
        if query_param_cls is None:
            query_param_cls = _get_vendor_symbols()[1]
        self._query_param_cls = query_param_cls
        self._aws_region = os.getenv("AWS_REGION")
        self._hirag = hirag or self._create_hirag_instance(
            hirag_cls or _get_vendor_symbols()[0], working_dir, hirag_kwargs
        )

    def _create_hirag_instance(
        self,
        hirag_cls: type,
        working_dir: str | None,
        extra_kwargs: dict[str, Any],
    ) -> Any:
        kwargs = dict(extra_kwargs)
        default_dir = os.getenv("HIRAG_WORKING_DIR")
        if default_dir is None:
            default_dir = str(_REPO_ROOT / "hirag_cache")
        kwargs.setdefault("working_dir", working_dir or default_dir)
        kwargs.setdefault("enable_naive_rag", True)

        storage_kwargs = self._resolve_storage_overrides()
        kwargs.update(storage_kwargs)

        if self._aws_region:
            kwargs.setdefault("aws_region", self._aws_region)

        return hirag_cls(**kwargs)

    def _resolve_storage_overrides(self) -> dict[str, Any]:
        if self._aws_region:
            return self._load_aws_storage_overrides()
        return self._local_storage_overrides()

    def _local_storage_overrides(self) -> dict[str, Any]:
        return _load_local_storage_overrides()

    def _load_aws_storage_overrides(self) -> dict[str, Any]:
        module = _load_storage_module()
        return dict(module.get_storage_overrides())

    async def index_documents(self, documents: Iterable[str]) -> None:
        doc_list = [doc for doc in documents if doc]
        if not doc_list:
            return
        await asyncio.to_thread(self._hirag.insert, doc_list)

    async def chat(
        self,
        query: str,
        session_id: str,
        mode: str = "",
        history: Sequence[Mapping[str, Any] | Sequence[str] | str] | None = None,
    ) -> dict[str, Any]:
        if not query:
            raise ValueError("query must not be empty")

        resolved_mode = self._normalize_mode(mode)
        base_param = self._query_param_cls(mode=resolved_mode)
        context_param = replace(base_param, only_need_context=True)

        context = await self._hirag.aquery(query, context_param)
        prompt = self._compose_prompt(query, session_id, history, context)
        answer = await self._hirag.aquery(query, base_param)
        references = self._extract_references(context)

        return {
            "answer": answer,
            "prompt": prompt,
            "context": context,
            "references": references,
        }

    def _normalize_mode(self, mode: str | None) -> str:
        candidate = (mode or "").strip().lower()
        if candidate in {"", "hi", "hierarchical"}:
            return "hi"
        if candidate in {"naive"}:
            return "naive"
        raise ValueError(f"Unsupported HiRAG mode: {mode}")

    def _compose_prompt(
        self,
        query: str,
        session_id: str,
        history: Sequence[Mapping[str, Any] | Sequence[str] | str] | None,
        context: str,
    ) -> str:
        parts: list[str] = []
        if session_id:
            parts.append(f"session: {session_id}")
        for entry in history or []:
            role, content = self._normalize_history_entry(entry)
            if content:
                parts.append(f"{role}: {content}")
        parts.append(f"user: {query}")
        if context:
            parts.append("retrieved context:\n" + context.strip())
        return "\n\n".join(parts)

    def _normalize_history_entry(
        self, entry: Mapping[str, Any] | Sequence[str] | str
    ) -> tuple[str, str]:
        if isinstance(entry, Mapping):
            role = str(entry.get("role", "user")).strip() or "user"
            content = str(entry.get("content", "")).strip()
            return role, content
        if isinstance(entry, Sequence) and not isinstance(entry, (str, bytes)):
            role = str(entry[0] if entry else "user").strip() or "user"
            content = str(entry[1] if len(entry) > 1 else "").strip()
            return role, content
        return "user", str(entry).strip()

    def _extract_references(self, context: str) -> list[dict[str, str]]:
        if not context:
            return []
        match = _SOURCE_SECTION_PATTERN.search(context)
        if not match:
            return []
        csv_block = match.group(1).replace("\t", "")
        reader = csv.reader(StringIO(csv_block))
        rows = [
            [cell.strip().strip('"').strip("'") for cell in row]
            for row in reader
            if any(cell.strip() for cell in row)
        ]
        if len(rows) < 2:
            return []
        headers = rows[0]
        references: list[dict[str, str]] = []
        for row in rows[1:]:
            padded = row + [""] * (len(headers) - len(row))
            references.append({headers[idx]: padded[idx] for idx in range(len(headers))})
        return references


__all__ = ["HiRAGService"]
