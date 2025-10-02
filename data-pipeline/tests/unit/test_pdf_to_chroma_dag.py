import pytest

try:
    from airflow.models import DagBag
except Exception:  # pragma: no cover - Airflow optional dependency
    DAG_AVAILABLE = False
else:
    DAG_AVAILABLE = True


@pytest.mark.skipif(not DAG_AVAILABLE, reason="Airflow not installed")
def test_dag_loaded():
    dagbag = DagBag(dag_folder="data-pipeline/dags", include_examples=False)
    assert "pdf_to_chroma" in dagbag.dags
    dag = dagbag.dags["pdf_to_chroma"]
    assert dag.task_ids == ["run_pdf_to_chroma_python_job"]
