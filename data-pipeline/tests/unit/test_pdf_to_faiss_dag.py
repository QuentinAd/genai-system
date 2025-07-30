import pytest

try:
    from airflow.models import DagBag
    from airflow.providers.docker.operators.docker import DockerOperator
    from airflow.providers.cncf.kubernetes.operators.kubernetes_pod import KubernetesPodOperator
except Exception:  # pragma: no cover - Airflow optional
    DAG_AVAILABLE = False
else:
    DAG_AVAILABLE = True


@pytest.mark.skipif(not DAG_AVAILABLE, reason="Airflow not installed")
def test_dag_loaded():
    dagbag = DagBag(dag_folder="data-pipeline/dags", include_examples=False)
    assert "pdf_to_faiss" in dagbag.dags
    dag = dagbag.get_dag("pdf_to_faiss")
    assert dag.task_ids == ["run_pdf_to_faiss_job"]


@pytest.mark.skipif(not DAG_AVAILABLE, reason="Airflow not installed")
def test_operator_selection(monkeypatch):
    monkeypatch.setenv("LOCAL_AIRFLOW", "true")
    dagbag = DagBag(dag_folder="data-pipeline/dags", include_examples=False)
    task = dagbag.get_dag("pdf_to_faiss").tasks[0]
    assert isinstance(task, DockerOperator)
    monkeypatch.setenv("LOCAL_AIRFLOW", "false")
    dagbag = DagBag(dag_folder="data-pipeline/dags", include_examples=False)
    task = dagbag.get_dag("pdf_to_faiss").tasks[0]
    assert isinstance(task, KubernetesPodOperator)
