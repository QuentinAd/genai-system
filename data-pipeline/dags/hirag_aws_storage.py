"""Custom HiRAG storage classes that persist data to AWS services."""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import sys

_VENDOR_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "third_party", "hhy-huang_hirag", "hirag")
)


def _load_vendor_attr(module_rel_path: str, module_name: str, attribute: str):
    module_path = os.path.join(_VENDOR_ROOT, module_rel_path)
    if not os.path.exists(module_path):  # pragma: no cover - defensive
        raise ImportError(f"Cannot locate HiRAG module at {module_path}")
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"Unable to load module spec for {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return getattr(module, attribute)


_vendor_errors: dict[str, Exception] = {}

try:
    JsonKVStorage = _load_vendor_attr("_storage/kv_json.py", "hirag_kv_json", "JsonKVStorage")
except Exception as exc:  # pragma: no cover - defensive
    _vendor_errors["kv"] = exc
    JsonKVStorage = None  # type: ignore[assignment]

try:
    NanoVectorDBStorage = _load_vendor_attr(
        "_storage/vdb_nanovectordb.py", "hirag_nanovectordb", "NanoVectorDBStorage"
    )
except Exception as exc:  # pragma: no cover - optional dependency
    _vendor_errors["vector"] = exc
    NanoVectorDBStorage = None  # type: ignore[assignment]

try:
    NetworkXStorage = _load_vendor_attr(
        "_storage/gdb_networkx.py", "hirag_networkx_storage", "NetworkXStorage"
    )
except Exception as exc:  # pragma: no cover - optional dependency
    _vendor_errors["graph"] = exc
    NetworkXStorage = None  # type: ignore[assignment]

try:
    vendor_logger = _load_vendor_attr("_utils.py", "hirag_utils", "logger")
except Exception:  # pragma: no cover - fallback
    vendor_logger = logging.getLogger("HiRAG")

logger = vendor_logger


if JsonKVStorage is None:  # pragma: no cover - optional dependency missing

    class JsonKVStorage:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError(
                "HiRAG JsonKVStorage unavailable. Install third_party dependencies."
            ) from _vendor_errors.get("kv")


if NanoVectorDBStorage is None:  # pragma: no cover - optional dependency missing

    class NanoVectorDBStorage:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError(
                "HiRAG nano vector storage unavailable. Install nano-vectordb dependency."
            ) from _vendor_errors.get("vector")


if NetworkXStorage is None:  # pragma: no cover - optional dependency missing

    class NetworkXStorage:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError(
                "HiRAG NetworkX storage unavailable. Install networkx dependency."
            ) from _vendor_errors.get("graph")


def _load_boto3():
    try:
        return importlib.import_module("boto3")
    except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "boto3 is required to use the HiRAG AWS storage classes. Install boto3 or "
            "set the HIRAG_STORAGE_MODE=local environment variable to skip AWS integration."
        ) from exc


def _load_opensearch():
    try:
        opensearch_module = importlib.import_module("opensearchpy")
    except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "opensearch-py is required to use the HiRAG OpenSearch storage. Install opensearch-py "
            "or set HIRAG_STORAGE_MODE=local."
        ) from exc
    return opensearch_module


def _load_aws4auth():
    try:
        return importlib.import_module("requests_aws4auth")
    except ModuleNotFoundError:  # pragma: no cover - optional dependency
        return None


async def _to_thread(func, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)


@dataclass
class DynamoKVStorage(JsonKVStorage):
    """KV store that mirrors JsonKVStorage semantics but persists entries in DynamoDB."""

    table_env_key: str = field(default="DYNAMO_KV_TABLE")
    partition_key: str = field(default="namespace")
    sort_key: str = field(default="key")

    def __post_init__(self):
        # initialise local cache via parent for compatibility
        super().__post_init__()
        self._region = self.global_config.get("aws_region") or os.getenv("AWS_REGION")
        self._table_name = (
            self.global_config.get("dynamo_table")
            or os.getenv(self.table_env_key)
            or self.global_config.get("table_name")
        )
        if not self._table_name:
            raise RuntimeError("DynamoKVStorage requires a DynamoDB table name")
        boto3 = _load_boto3()
        self._dynamodb = boto3.resource("dynamodb", region_name=self._region)
        self._table = self._dynamodb.Table(self._table_name)
        # warm cache from dynamo
        self._data = {}
        try:
            self._refresh_from_dynamo()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to warm cache from DynamoDB: %s", exc)

    def _refresh_from_dynamo(self) -> None:
        _load_boto3()
        conditions = importlib.import_module("boto3.dynamodb.conditions")
        key_expr = conditions.Key(self.partition_key).eq(self.namespace)
        items: list[dict[str, Any]] = []
        last_evaluated_key: Optional[Dict[str, Any]] = None
        while True:
            kwargs = {
                "KeyConditionExpression": key_expr,
                "ProjectionExpression": f"{self.sort_key}, payload",
            }
            if last_evaluated_key:
                kwargs["ExclusiveStartKey"] = last_evaluated_key
            response = self._table.query(**kwargs)
            items.extend(response.get("Items", []))
            last_evaluated_key = response.get("LastEvaluatedKey")
            if not last_evaluated_key:
                break
        self._data = {
            item[self.sort_key]: json.loads(item["payload"]) if "payload" in item else {}
            for item in items
        }

    async def upsert(self, data: dict[str, dict]):
        await super().upsert(data)

        def _write_batch() -> None:
            with self._table.batch_writer() as writer:
                for key, value in data.items():
                    writer.put_item(
                        Item={
                            self.partition_key: self.namespace,
                            self.sort_key: key,
                            "payload": json.dumps(value),
                        }
                    )

        await _to_thread(_write_batch)

    async def drop(self):
        await super().drop()

        def _delete_all() -> None:
            if not self._data:
                return
            with self._table.batch_writer() as writer:
                for key in list(self._data.keys()):
                    writer.delete_item(
                        Key={
                            self.partition_key: self.namespace,
                            self.sort_key: key,
                        }
                    )

        await _to_thread(_delete_all)
        self._data = {}


@dataclass
class OpenSearchVectorStorage(NanoVectorDBStorage):
    """
    Persist embeddings to OpenSearch vector storage while keeping local NanoVectorDB cache.
    """

    def __post_init__(self):
        super().__post_init__()
        self._endpoint = os.getenv("OPENSEARCH_ENDPOINT")
        self._index_name = os.getenv("OPENSEARCH_INDEX", f"hirag-{self.namespace}")
        self._region = self.global_config.get("aws_region") or os.getenv("AWS_REGION")
        self._opensearch_kwargs = {
            "use_ssl": os.getenv("OPENSEARCH_USE_SSL", "true").lower() == "true",
            "verify_certs": os.getenv("OPENSEARCH_VERIFY_CERTS", "true").lower() == "true",
        }
        if not self._endpoint:
            logger.warning("OPENSEARCH_ENDPOINT not set; OpenSearch persistence disabled")
            self._client = None
        else:
            self._client = self._create_client()
            self._ensure_index()

    def _create_client(self):
        opensearch_module = _load_opensearch()
        auth = None
        aws4auth_module = _load_aws4auth()
        username = os.getenv("OPENSEARCH_USERNAME")
        password = os.getenv("OPENSEARCH_PASSWORD")
        if username and password:
            auth = (username, password)
        elif aws4auth_module is not None:
            session = _load_boto3().session.Session()
            credentials = session.get_credentials().get_frozen_credentials()
            region = self._region or session.region_name
            auth = aws4auth_module.AWS4Auth(
                credentials.access_key,
                credentials.secret_key,
                region,
                "es",
                session_token=credentials.token,
            )
        return opensearch_module.OpenSearch(
            hosts=[self._endpoint],
            http_auth=auth,
            **self._opensearch_kwargs,
        )

    def _ensure_index(self) -> None:
        if self._client is None:
            return
        dim = getattr(self.embedding_func, "embedding_dim", None)
        if dim is None:
            raise RuntimeError(
                "Embedding function does not expose embedding_dim for OpenSearch mapping"
            )
        exists = self._client.indices.exists(index=self._index_name)
        if not exists:
            settings = {
                "settings": {
                    "index": {
                        "knn": True,
                        "number_of_shards": int(os.getenv("OPENSEARCH_SHARDS", "1")),
                        "number_of_replicas": int(os.getenv("OPENSEARCH_REPLICAS", "1")),
                    }
                },
                "mappings": {
                    "properties": {
                        "vector": {"type": "knn_vector", "dimension": dim},
                        "metadata": {"type": "object", "enabled": True},
                        "content": {"type": "text"},
                    }
                },
            }
            self._client.indices.create(index=self._index_name, body=settings)

    async def upsert(self, data: dict[str, dict]):
        results = await super().upsert(data)
        if not data or self._client is None:
            return results
        embeddings, list_data = await self._prepare_vectors(data)

        def _bulk_upload() -> None:
            actions: list[dict[str, Any]] = []
            for idx, item in enumerate(list_data):
                body = {
                    "vector": embeddings[idx].tolist(),
                    "metadata": {
                        k: v
                        for k, v in item.items()
                        if k not in {"__id__", "content", "__vector__"}
                    },
                    "content": data[item["__id__"]]["content"],
                }
                actions.append({"index": {"_index": self._index_name, "_id": item["__id__"]}})
                actions.append(body)
            opensearch_module = _load_opensearch()
            opensearch_module.helpers.bulk(self._client, actions)

        await _to_thread(_bulk_upload)
        return results

    async def _prepare_vectors(self, data: dict[str, dict]):
        # duplicate logic from parent but w/o writing to disk as already handled
        contents = [v["content"] for v in data.values()]
        batches = [
            contents[i : i + self._max_batch_size]
            for i in range(0, len(contents), self._max_batch_size)
        ]
        embeddings_list = await asyncio.gather(*[self.embedding_func(batch) for batch in batches])
        embeddings = importlib.import_module("numpy").concatenate(embeddings_list)
        list_data = [
            {
                "__id__": k,
                **{k1: v1 for k1, v1 in v.items() if k1 in self.meta_fields},
            }
            for k, v in data.items()
        ]
        return embeddings, list_data

    async def query(self, query: str, top_k=5):
        if self._client is None:
            return await super().query(query, top_k)
        embedding = await self.embedding_func([query])
        body = {
            "size": top_k,
            "query": {
                "knn": {
                    "vector": {
                        "vector": embedding[0].tolist(),
                        "k": top_k,
                    }
                }
            },
        }
        response = self._client.search(index=self._index_name, body=body)
        hits = response.get("hits", {}).get("hits", [])
        return [
            {
                "id": hit["_id"],
                "distance": hit.get("_score"),
                **hit.get("_source", {}),
            }
            for hit in hits
        ]


@dataclass
class NeptuneGraphStorage(NetworkXStorage):
    """Graph storage using NetworkX locally and Neptune bulk load for persistence."""

    def __post_init__(self):
        super().__post_init__()
        self._bucket = os.getenv("NEPTUNE_GRAPH_BUCKET")
        self._iam_role = os.getenv("NEPTUNE_IAM_ROLE_ARN")
        self._region = self.global_config.get("aws_region") or os.getenv("AWS_REGION")
        self._neptune_endpoint = os.getenv("NEPTUNE_ENDPOINT")

    async def index_done_callback(self):
        await super().index_done_callback()
        if not (self._bucket and self._iam_role and self._neptune_endpoint):
            logger.warning(
                "Neptune configuration incomplete; skipping Neptune bulk load for namespace %s",
                self.namespace,
            )
            return

        graph_file = self._graphml_xml_file
        key = f"hirag/{self.namespace}/{int(time.time())}.graphml"
        s3_uri = f"s3://{self._bucket}/{key}"

        def _upload_and_load():
            boto3 = _load_boto3()
            s3_client = boto3.client("s3", region_name=self._region)
            s3_client.upload_file(graph_file, self._bucket, key)
            neptune_client = boto3.client("neptune-data", region_name=self._region)
            neptune_client.start_loader_job(
                source=s3_uri,
                sourceFormat="graphml",
                iamRoleArn=self._iam_role,
                region=self._region,
                mode="NEW",
                failOnError=True,
                parallelism="HIGH",
                updateSingleCardinalityProperties=True,
                queueRequest=True,
            )

        await _to_thread(_upload_and_load)


def get_storage_overrides() -> Dict[str, Any]:
    """Return keyword arguments to override HiRAG storage classes."""
    storage_mode = os.getenv("HIRAG_STORAGE_MODE", "aws").lower()
    if storage_mode == "local":
        logger.warning("HIRAG_STORAGE_MODE=local – using bundled storage implementations only")
        return {}

    missing = [name for name in ("kv", "vector", "graph") if name in _vendor_errors]
    if missing:
        logger.warning(
            "Missing HiRAG vendor dependencies (%s); falling back to bundled storage classes.",
            ", ".join(missing),
        )
        return {}

    return {
        "key_string_value_json_storage_cls": DynamoKVStorage,
        "vector_db_storage_cls": OpenSearchVectorStorage,
        "graph_storage_cls": NeptuneGraphStorage,
    }
