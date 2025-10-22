import importlib.util
import sys
from pathlib import Path

import pytest

try:
    from airflow.models import DagBag
except Exception:  # pragma: no cover - Airflow optional dependency
    DAG_AVAILABLE = False
else:
    DAG_AVAILABLE = True


@pytest.mark.skipif(not DAG_AVAILABLE, reason="Airflow not installed")
def test_hirag_index_dag_loaded():
    dagbag = DagBag(dag_folder="data-pipeline/dags", include_examples=False)

    assert "hirag_index" in dagbag.dags
    dag = dagbag.dags["hirag_index"]

    expected_task_ids = {
        "wait_for_new_documents",
        "download_new_documents",
        "index_documents",
        "sync_knowledge_base",
        "archive_documents",
        "cleanup_tempdir",
    }
    assert set(dag.task_ids) == expected_task_ids


@pytest.mark.skipif(not DAG_AVAILABLE, reason="Airflow not installed")
def test_hirag_index_task_dependencies():
    dag = DagBag(dag_folder="data-pipeline/dags", include_examples=False).dags["hirag_index"]

    wait_task = dag.get_task("wait_for_new_documents")
    download_task = dag.get_task("download_new_documents")
    index_task = dag.get_task("index_documents")
    sync_task = dag.get_task("sync_knowledge_base")
    archive_task = dag.get_task("archive_documents")
    cleanup_task = dag.get_task("cleanup_tempdir")

    assert download_task in wait_task.downstream_list
    assert index_task in download_task.downstream_list
    assert sync_task in index_task.downstream_list
    assert archive_task in sync_task.downstream_list
    assert cleanup_task in archive_task.downstream_list


@pytest.mark.skipif(not DAG_AVAILABLE, reason="Airflow not installed")
def test_hirag_index_params_and_defaults():
    dag = DagBag(dag_folder="data-pipeline/dags", include_examples=False).dags["hirag_index"]

    assert dag.catchup is False
    assert dag.max_active_runs == 1
    assert "batch_size" in dag.params
    assert dag.params["batch_size"] == 5
    assert "max_concurrency" in dag.params
    assert dag.params["max_concurrency"] == 2

    default_args = dag.default_args
    assert default_args["retries"] == 2
    assert "retry_delay" in default_args


@pytest.mark.skipif(not DAG_AVAILABLE, reason="Airflow not installed")
def test_download_documents_uses_explicit_file_path(monkeypatch, tmp_path):
    dag_path = Path(__file__).resolve().parents[2] / "dags" / "hirag_index.py"
    spec = importlib.util.spec_from_file_location("hirag_index_module", dag_path)
    assert spec and spec.loader
    dag_module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = dag_module
    spec.loader.exec_module(dag_module)

    downloads: list[dict[str, object]] = []

    class StubS3Hook:
        def __init__(self, *args, **kwargs):
            pass

        def list_keys(self, *, bucket_name: str, prefix: str):
            return ["incoming/sample.txt"]

        def download_file(
            self,
            *,
            key: str,
            bucket_name: str,
            local_path: str,
            preserve_file_name: bool = True,
        ):
            downloads.append(
                {
                    "key": key,
                    "bucket": bucket_name,
                    "local_path": local_path,
                    "preserve_file_name": preserve_file_name,
                }
            )
            destination = Path(local_path) / Path(key).name
            destination.write_text("dummy", encoding="utf-8")
            return str(destination)

    class StubStore:
        async def all_keys(self):
            return []

        async def upsert(self, data):
            self.data = data  # type: ignore[attr-defined]

        async def index_done_callback(self):
            pass

    monkeypatch.setattr(dag_module, "S3Hook", StubS3Hook)
    monkeypatch.setattr(dag_module, "_create_processed_store", lambda: StubStore())
    monkeypatch.setattr(dag_module, "TEMP_BASE_DIR", str(tmp_path))

    result = dag_module._download_documents(batch_size=1)

    assert downloads, "S3 download was not invoked"
    download_call = downloads[0]
    assert download_call["preserve_file_name"] is True
    assert Path(download_call["local_path"]).is_dir()
    document = result["documents"][0]
    assert Path(document["local_path"]).exists()
    assert Path(document["local_path"]).parent == Path(download_call["local_path"])
