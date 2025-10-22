"""Airflow DAG orchestrating hierarchical RAG indexing with AWS-native storage backends."""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import sys
import logging
import os
import shutil
import tempfile
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any, Dict, List, Protocol
from pathlib import Path

from airflow import DAG

try:  # pragma: no cover - Airflow 3 compatibility
    from airflow.sdk.param import Param
except ModuleNotFoundError:  # pragma: no cover - fallback for older Airflow
    from airflow.models.param import Param  # type: ignore[no-redef]

try:
    from airflow.providers.amazon.aws.hooks.s3 import S3Hook
    from airflow.providers.amazon.aws.sensors.s3 import S3KeySensor
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    from airflow.exceptions import AirflowException

    try:  # pragma: no cover - standard provider optional on older Airflow installations
        from airflow.providers.standard.operators.empty import EmptyOperator
    except ModuleNotFoundError:  # pragma: no cover
        from airflow.operators.empty import EmptyOperator  # type: ignore[no-redef]

    class S3Hook:  # type: ignore[override]
        """Stub S3Hook that fails fast when the AWS provider is missing."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
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
        """Stub sensor used when the AWS provider is unavailable."""

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

try:  # pragma: no cover - Airflow 3 compatibility
    from airflow.task.trigger_rule import TriggerRule
except ModuleNotFoundError:  # pragma: no cover - fallback
    from airflow.utils.trigger_rule import TriggerRule  # type: ignore[no-redef]


def _load_storage_module():
    module_name = "hirag_aws_storage"
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError:
        package_dir = os.path.dirname(__file__)
        module_path = os.path.join(package_dir, "hirag_aws_storage.py")
        if not os.path.exists(module_path):
            raise
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:
            raise
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module


_storage_module = _load_storage_module()
DynamoKVStorage = _storage_module.DynamoKVStorage
get_storage_overrides = _storage_module.get_storage_overrides

LOGGER = logging.getLogger(__name__)

try:
    from third_party.hhy_huang_hirag.hirag._utils import compute_mdhash_id
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    import hashlib

    def compute_mdhash_id(content: str, prefix: str = "") -> str:
        return prefix + hashlib.sha256(content.encode("utf-8")).hexdigest()


AWS_CONN_ID = os.getenv("HIRAG_AWS_CONN_ID", "aws_default")
INGEST_BUCKET = os.getenv("HIRAG_SOURCE_BUCKET", "hirag-ingestion")
INGEST_PREFIX = os.getenv("HIRAG_SOURCE_PREFIX", "incoming/")
ARCHIVE_PREFIX = os.getenv("HIRAG_ARCHIVE_PREFIX", "archive/")
DEFAULT_BATCH_SIZE = int(os.getenv("HIRAG_BATCH_SIZE", "5"))
DEFAULT_MAX_CONCURRENCY = int(os.getenv("HIRAG_MAX_CONCURRENCY", "2"))
TEMP_BASE_DIR = os.getenv("HIRAG_TEMP_BASE_DIR", tempfile.gettempdir())
HIRAG_WORKING_DIR = os.getenv("HIRAG_WORKING_DIR", "/opt/airflow/hirag")
PROCESSED_NAMESPACE = os.getenv("HIRAG_PROCESSED_NAMESPACE", "processed_keys")
DYNAMO_PROCESSED_TABLE = os.getenv("DYNAMO_PROCESSED_TABLE")

DEFAULT_ARGS = {
    "start_date": datetime(2024, 1, 1),
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


class KVStorage(Protocol):
    """Subset of the HiRAG KV storage interface used by the DAG."""

    namespace: str

    async def all_keys(self) -> list[str]: ...

    async def upsert(self, data: dict[str, dict[str, Any]]) -> None: ...

    async def index_done_callback(self) -> None: ...


def _run_async(coro):
    """Run an async coroutine from a synchronous context."""
    return asyncio.run(coro)


@lru_cache(maxsize=1)
def _get_kv_storage_cls() -> type[KVStorage]:
    return DynamoKVStorage


def _create_processed_store() -> KVStorage:
    storage_cls = _get_kv_storage_cls()
    global_config = {
        "working_dir": HIRAG_WORKING_DIR,
        "dynamo_table": DYNAMO_PROCESSED_TABLE or os.getenv("DYNAMO_KV_TABLE"),
        "aws_region": os.getenv("AWS_REGION"),
    }
    if not global_config["dynamo_table"]:
        raise RuntimeError(
            "DYNAMO_PROCESSED_TABLE (or DYNAMO_KV_TABLE) must be set for HiRAG indexing"
        )
    return storage_cls(namespace=PROCESSED_NAMESPACE, global_config=global_config)


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
        key_hash = compute_mdhash_id(key, prefix="key-")
        if key_hash in processed_hashes:
            LOGGER.debug("Skipping already processed key %s", key)
            continue
        LOGGER.info("Downloading s3://%s/%s to temporary directory %s", INGEST_BUCKET, key, tempdir)
        downloaded_path = hook.download_file(
            key=key,
            bucket_name=INGEST_BUCKET,
            local_path=tempdir,
            preserve_file_name=True,
        )
        candidate_path = (
            Path(downloaded_path) if downloaded_path else Path(tempdir) / os.path.basename(key)
        )
        if candidate_path.is_dir():
            candidate_path = candidate_path / os.path.basename(key)
        if not candidate_path.exists():
            fallback_path = Path(tempdir) / os.path.basename(key)
            if fallback_path.exists():
                candidate_path = fallback_path
            else:
                raise FileNotFoundError(f"Downloaded object {key} not found at {candidate_path}")
        local_path = str(candidate_path)
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
        doc_hash = compute_mdhash_id(content, prefix="doc-")
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
        hirag_module = importlib.import_module("third_party.hhy_huang_hirag.hirag")
        HiRAG = hirag_module.HiRAG
    except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency
        LOGGER.error("HiRAG package not available: %s", exc)
        raise

    storage_overrides = get_storage_overrides()

    LOGGER.info("Starting HiRAG indexing for %d documents", len(payload))
    hirag_instance = HiRAG(
        working_dir=HIRAG_WORKING_DIR,
        embedding_batch_num=batch_size,
        embedding_func_max_async=max_concurrency,
        best_model_max_async=max_concurrency,
        cheap_model_max_async=max_concurrency,
        **storage_overrides,
    )
    hirag_instance.insert(payload)
    LOGGER.info("HiRAG indexing completed")

    return {
        "documents": documents,
    }


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
    description="Index hierarchical RAG documents into DynamoDB, OpenSearch, and Neptune",
    default_args=DEFAULT_ARGS,
    schedule="@hourly",
    catchup=False,
    max_active_runs=1,
    params={
        "batch_size": Param(DEFAULT_BATCH_SIZE, type="integer", minimum=1),
        "max_concurrency": Param(DEFAULT_MAX_CONCURRENCY, type="integer", minimum=1),
    },
    tags=["hirag", "rag", "aws"],
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
        result = _index_documents(
            documents,
            batch_size=batch_size,
            max_concurrency=max_concurrency,
        )
        result["tempdir"] = downstream_context.get("tempdir")
        return result

    index_documents = PythonOperator(
        task_id="index_documents",
        python_callable=index_callable,
    )

    def archive_callable(**context: Any) -> Dict[str, Any]:
        upstream = context["ti"].xcom_pull(task_ids="index_documents")
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
        >> archive_documents
        >> cleanup_tempdir
    )
