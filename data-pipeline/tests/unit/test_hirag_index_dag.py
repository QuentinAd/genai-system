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
    assert dag.params["batch_size"].default == 5
    assert "max_concurrency" in dag.params
    assert dag.params["max_concurrency"].default == 2

    default_args = dag.default_args
    assert default_args["retries"] == 2
    assert "retry_delay" in default_args
