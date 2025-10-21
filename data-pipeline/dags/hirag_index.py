"""Airflow DAG orchestrating hierarchical RAG indexing using the vendored HiRAG package."""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
import logging
import os
import shutil
import tempfile
from functools import lru_cache
from datetime import datetime, timedelta
from typing import Any, Dict, List, Protocol

from airflow import DAG
from airflow.models.param import Param

try:
    from airflow.providers.amazon.aws.hooks.s3 import S3Hook
    from airflow.providers.amazon.aws.sensors.s3 import S3KeySensor
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    from airflow.exceptions import AirflowException

    try:  # pragma: no cover - standard provider is optional in older Airflow
        from airflow.providers.standard.operators.empty import EmptyOperator
    except ModuleNotFoundError:  # pragma: no cover - fallback for older releases
        from airflow.operators.empty import EmptyOperator  # type: ignore[no-redef]

    class S3Hook:  # type: ignore[override]
        """Stub S3Hook that fails fast when the AWS provider is missing."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: D401 - simple stub
            self._raise()

        def _raise(self) -> None:
            raise AirflowException(
                "apache-airflow-providers-amazon is required for the hirag_index DAG."
            )

        def list_keys(self, *args: Any, **kwargs: Any) -> list[str]:
            self._raise()

        def download_file(self, *args: Any, **kwargs: Any) -> None:
            self._raise()

        def copy_object(self, *args: Any, **kwargs: Any) -> None:
            self._raise()

        def delete_objects(self, *args: Any, **kwargs: Any) -> None:
            self._raise()

    class S3KeySensor(EmptyOperator):  # type: ignore[misc]
        """Stub sensor that raises if executed without the AWS provider."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            for field in (
                "bucket_name",
                "bucket_key",
                "wildcard_match",
                "aws_conn_id",
                "verify",
                "poke_interval",
                "timeout",
                "soft_fail",
                "mode",
                "deferrable",
            ):
                kwargs.pop(field, None)
            super().__init__(*args, **kwargs)

        def execute(self, context: dict | None = None) -> None:  # noqa: D401 - simple stub
            raise AirflowException(
                "apache-airflow-providers-amazon is required for the hirag_index DAG."
            )


from airflow.providers.standard.operators.python import PythonOperator
from airflow.utils.trigger_rule import TriggerRule

LOGGER = logging.getLogger(__name__)


AWS_CONN_ID = os.getenv("HIRAG_AWS_CONN_ID", "aws_default")
INGEST_BUCKET = os.getenv("HIRAG_SOURCE_BUCKET", "hirag-ingestion")
INGEST_PREFIX = os.getenv("HIRAG_SOURCE_PREFIX", "incoming/")
ARCHIVE_PREFIX = os.getenv("HIRAG_ARCHIVE_PREFIX", "archive/")
BACKEND_SYNC_ENDPOINT = os.getenv(
    "HIRAG_SYNC_ENDPOINT",
    "http://backend:8000/api/v1/hirag/sync",
)
DEFAULT_BATCH_SIZE = int(os.getenv("HIRAG_BATCH_SIZE", "5"))
DEFAULT_MAX_CONCURRENCY = int(os.getenv("HIRAG_MAX_CONCURRENCY", "2"))
TEMP_BASE_DIR = os.getenv("HIRAG_TEMP_BASE_DIR", tempfile.gettempdir())
HIRAG_WORKING_DIR = os.getenv("HIRAG_WORKING_DIR", "/opt/airflow/hirag")
PROCESSED_NAMESPACE = os.getenv("HIRAG_PROCESSED_NAMESPACE", "processed_keys")

DEFAULT_ARGS = {
    "start_date": datetime(2024, 1, 1),
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


class KVStorage(Protocol):
    """Subset of the JsonKVStorage async API used by the DAG."""

    namespace: str

    async def all_keys(self) -> list[str]: ...

    async def upsert(self, data: dict[str, dict[str, Any]]) -> None: ...

    async def index_done_callback(self) -> None: ...


class FallbackJsonKVStorage:
    """Synchronous JSON backed KV store mirroring JsonKVStorage behaviour."""

    def __init__(self, namespace: str, global_config: Dict[str, Any]):
        self.namespace = namespace
        working_dir = global_config.get("working_dir", tempfile.gettempdir())
        os.makedirs(working_dir, exist_ok=True)
        self._file_name = os.path.join(working_dir, f"kv_store_{namespace}.json")
        try:
            with open(self._file_name, encoding="utf-8") as infile:
                self._data: Dict[str, Dict[str, Any]] = json.load(infile)
        except FileNotFoundError:
            self._data = {}
        except json.JSONDecodeError:
            LOGGER.warning("Fallback store %s has invalid JSON; reinitialising", self._file_name)
            self._data = {}

    async def all_keys(self) -> list[str]:
        return list(self._data.keys())

    async def upsert(self, data: dict[str, dict[str, Any]]) -> None:
        self._data.update(data)

    async def index_done_callback(self) -> None:
        with open(self._file_name, "w", encoding="utf-8") as outfile:
            json.dump(self._data, outfile, indent=2, ensure_ascii=False)


def _run_async(coro):
    """Run an async coroutine from a synchronous context."""
    return asyncio.run(coro)


@lru_cache(maxsize=1)
def _load_compute_mdhash_id():
    try:
        utils_module = importlib.import_module("third_party.hhy-huang_hirag.hirag._utils")
        return utils_module.compute_mdhash_id
    except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency
        LOGGER.warning("Could not load HiRAG utils: %s. Falling back to hashlib", exc)
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.error("Unexpected error importing HiRAG utils: %s", exc)
    return lambda content, prefix="": prefix + hashlib.sha256(content.encode("utf-8")).hexdigest()


@lru_cache(maxsize=1)
def _get_kv_storage_cls() -> type[KVStorage]:
    try:
        storage_module = importlib.import_module(
            "third_party.hhy-huang_hirag.hirag._storage.kv_json"
        )
        return storage_module.JsonKVStorage
    except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency
        LOGGER.warning("JsonKVStorage unavailable (%s), using fallback store", exc)
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.error("Unexpected error importing JsonKVStorage: %s", exc)
    return FallbackJsonKVStorage


def _create_processed_store() -> KVStorage:
    storage_cls = _get_kv_storage_cls()
    return storage_cls(
        namespace=PROCESSED_NAMESPACE, global_config={"working_dir": HIRAG_WORKING_DIR}
    )


def _compute_key_hash(key: str) -> str:
    compute_mdhash_id = _load_compute_mdhash_id()
    return compute_mdhash_id(key, prefix="key-")


def _compute_document_hash(content: str) -> str:
    compute_mdhash_id = _load_compute_mdhash_id()
    return compute_mdhash_id(content, prefix="doc-")


def _download_documents(batch_size: int) -> Dict[str, Any]:
    hook = S3Hook(aws_conn_id=AWS_CONN_ID)
    keys = hook.list_keys(bucket_name=INGEST_BUCKET, prefix=INGEST_PREFIX) or []

    processed_store = _create_processed_store()
    processed_hashes = set(_run_async(processed_store.all_keys()))
    new_documents: List[Dict[str, Any]] = []

    if not keys:
        LOGGER.info("No keys found under %s/%s", INGEST_BUCKET, INGEST_PREFIX)

    tempdir = tempfile.mkdtemp(prefix="hirag_", dir=TEMP_BASE_DIR)

    for key in keys:
        if not key or key.endswith("/"):
            continue
        key_hash = _compute_key_hash(key)
        if key_hash in processed_hashes:
            LOGGER.debug("Skipping already processed key %s", key)
            continue
        local_path = os.path.join(tempdir, os.path.basename(key))
        LOGGER.info("Downloading s3://%s/%s to %s", INGEST_BUCKET, key, local_path)
        hook.download_file(key=key, bucket_name=INGEST_BUCKET, local_path=local_path)
        new_documents.append(
            {
                "s3_key": key,
                "local_path": local_path,
                "key_hash": key_hash,
            }
        )
        if len(new_documents) >= batch_size:
            break

    if not new_documents:
        LOGGER.info("No new documents to process")

    return {
        "tempdir": tempdir,
        "documents": new_documents,
    }


def _build_hirag_payload(documents: List[Dict[str, Any]]) -> Dict[str, Any]:
    payload: List[str] = []
    document_hashes: Dict[str, str] = {}

    for doc in documents:
        local_path = doc["local_path"]
        with open(local_path, "r", encoding="utf-8") as infile:
            content = infile.read()
        doc_hash = _compute_document_hash(content)
        payload.append(content)
        document_hashes[local_path] = doc_hash
        doc["document_hash"] = doc_hash

    return {
        "payload": payload,
        "hashes": document_hashes,
    }


def _index_documents(
    documents: List[Dict[str, Any]], batch_size: int, max_concurrency: int
) -> Dict[str, Any]:
    if not documents:
        LOGGER.info("Skipping indexing run because there are no new documents")
        return {"documents": []}

    hirag_payload = _build_hirag_payload(documents)
    payload = hirag_payload["payload"]

    try:
        hirag_module = importlib.import_module("third_party.hhy-huang_hirag.hirag")
        HiRAG = hirag_module.HiRAG
    except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency
        LOGGER.error("HiRAG package not available: %s", exc)
        raise

    LOGGER.info("Starting HiRAG indexing for %d documents", len(payload))
    hirag_instance = HiRAG(
        working_dir=HIRAG_WORKING_DIR,
        embedding_batch_num=batch_size,
        embedding_func_max_async=max_concurrency,
        best_model_max_async=max_concurrency,
        cheap_model_max_async=max_concurrency,
    )
    hirag_instance.insert(payload)
    LOGGER.info("HiRAG indexing completed")

    return {
        "documents": documents,
    }


def _sync_bedrock(documents: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not documents:
        LOGGER.info("Skipping Bedrock sync because there are no indexed documents")
        return {"documents": []}

    if not BACKEND_SYNC_ENDPOINT:
        LOGGER.warning("No sync endpoint configured; skipping Bedrock synchronization")
        return {"documents": documents}

    LOGGER.info("Triggering Bedrock Knowledge Base sync at %s", BACKEND_SYNC_ENDPOINT)
    httpx = importlib.import_module("httpx")
    with httpx.Client(timeout=60) as client:
        response = client.post(
            BACKEND_SYNC_ENDPOINT,
            json={
                "document_keys": [doc["s3_key"] for doc in documents],
            },
        )
        response.raise_for_status()
    LOGGER.info("Bedrock Knowledge Base sync completed")
    return {"documents": documents}


def _archive_documents(documents: List[Dict[str, Any]]) -> None:
    if not documents:
        LOGGER.info("Nothing to archive")
        return

    hook = S3Hook(aws_conn_id=AWS_CONN_ID)
    processed_store = _create_processed_store()
    upsert_payload: Dict[str, Dict[str, Any]] = {}

    for doc in documents:
        key = doc["s3_key"]
        archive_key = f"{ARCHIVE_PREFIX.rstrip('/')}/{os.path.basename(key)}"
        LOGGER.info("Archiving %s to s3://%s/%s", key, INGEST_BUCKET, archive_key)
        hook.copy_object(
            source_bucket_key=key,
            dest_bucket_key=archive_key,
            source_bucket_name=INGEST_BUCKET,
            dest_bucket_name=INGEST_BUCKET,
        )
        hook.delete_objects(bucket=INGEST_BUCKET, keys=[key])
        upsert_payload[doc["key_hash"]] = {
            "s3_key": key,
            "archived_at": datetime.utcnow().isoformat(),
            "document_hash": doc.get("document_hash"),
        }

    if upsert_payload:
        _run_async(processed_store.upsert(upsert_payload))
        _run_async(processed_store.index_done_callback())

    LOGGER.info("Archived %d documents and updated processed state", len(documents))


def _cleanup_tempdir(tempdir: str) -> None:
    if tempdir and os.path.exists(tempdir):
        LOGGER.info("Cleaning up temporary directory %s", tempdir)
        shutil.rmtree(tempdir, ignore_errors=True)


with DAG(
    dag_id="hirag_index",
    description="Index hierarchical RAG documents and synchronize Bedrock knowledge base",
    default_args=DEFAULT_ARGS,
    schedule="@hourly",
    catchup=False,
    max_active_runs=1,
    params={
        "batch_size": Param(DEFAULT_BATCH_SIZE, type="integer", minimum=1),
        "max_concurrency": Param(DEFAULT_MAX_CONCURRENCY, type="integer", minimum=1),
    },
    tags=["hirag", "rag", "bedrock"],
) as DAG_INSTANCE:
    wait_for_new_documents = S3KeySensor(
        task_id="wait_for_new_documents",
        bucket_name=INGEST_BUCKET,
        bucket_key=f"{INGEST_PREFIX}*",
        wildcard_match=True,
        aws_conn_id=AWS_CONN_ID,
        poke_interval=int(os.getenv("HIRAG_SENSOR_POKE", "60")),
        timeout=int(os.getenv("HIRAG_SENSOR_TIMEOUT", "3600")),
        soft_fail=True,
    )

    def download_callable(**context: Any) -> Dict[str, Any]:
        batch_size = context["params"]["batch_size"]
        return _download_documents(batch_size=batch_size)

    download_new_documents = PythonOperator(
        task_id="download_new_documents",
        python_callable=download_callable,
    )

    def index_callable(**context: Any) -> Dict[str, Any]:
        downstream_context = context["ti"].xcom_pull(task_ids="download_new_documents")
        documents = downstream_context.get("documents", [])
        batch_size = context["params"]["batch_size"]
        max_concurrency = context["params"]["max_concurrency"]
        result = _index_documents(documents, batch_size=batch_size, max_concurrency=max_concurrency)
        result["tempdir"] = downstream_context.get("tempdir")
        return result

    index_documents = PythonOperator(
        task_id="index_documents",
        python_callable=index_callable,
    )

    def sync_callable(**context: Any) -> Dict[str, Any]:
        upstream = context["ti"].xcom_pull(task_ids="index_documents")
        documents = upstream.get("documents", [])
        result = _sync_bedrock(documents)
        result["tempdir"] = upstream.get("tempdir")
        return result

    sync_knowledge_base = PythonOperator(
        task_id="sync_knowledge_base",
        python_callable=sync_callable,
    )

    def archive_callable(**context: Any) -> Dict[str, Any]:
        upstream = context["ti"].xcom_pull(task_ids="sync_knowledge_base")
        documents = upstream.get("documents", [])
        _archive_documents(documents)
        return {"tempdir": upstream.get("tempdir")}

    archive_documents = PythonOperator(
        task_id="archive_documents",
        python_callable=archive_callable,
    )

    def cleanup_callable(**context: Any) -> None:
        upstream = context["ti"].xcom_pull(task_ids="archive_documents")
        _cleanup_tempdir(upstream.get("tempdir"))

    cleanup_tempdir = PythonOperator(
        task_id="cleanup_tempdir",
        python_callable=cleanup_callable,
        trigger_rule=TriggerRule.ALL_DONE,
    )

    (
        wait_for_new_documents
        >> download_new_documents
        >> index_documents
        >> sync_knowledge_base
        >> archive_documents
        >> cleanup_tempdir
    )
