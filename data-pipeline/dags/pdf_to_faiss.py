from airflow import DAG
from datetime import datetime
import os

try:  # Airflow 2.x provider package
    from airflow.providers.cncf.kubernetes.operators.kubernetes_pod import KubernetesPodOperator
except Exception:  # pragma: no cover - provider not installed
    try:  # Airflow 1.10 fallback
        from airflow.contrib.operators.kubernetes_pod_operator import KubernetesPodOperator
    except Exception:  # pragma: no cover - no Kubernetes support
        KubernetesPodOperator = None  # type: ignore[misc]
from airflow.providers.docker.operators.docker import DockerOperator

DEFAULT_ARGS = {"start_date": datetime(2025, 1, 1), "retries": 0}

with DAG(
    "pdf_to_faiss",
    schedule_interval=None,
    catchup=False,
    default_args=DEFAULT_ARGS,
    description="Create FAISS index from PDF",
) as dag:
    if os.getenv("LOCAL_AIRFLOW", "false").lower() == "true":
        run_job = DockerOperator(
            task_id="run_pdf_to_faiss_job",
            image="spark-etl:local",
            auto_remove=True,
            command="python /app/pdf_to_faiss.py",
            docker_url="unix://var/run/docker.sock",
            network_mode="bridge",
            environment={
                "PDF_PATH": "/opt/airflow/data/input.pdf",
                "INDEX_PATH": "/opt/airflow/data/index.faiss",
            },
        )
    else:
        if KubernetesPodOperator is None:
            raise RuntimeError("KubernetesPodOperator not available")

        run_job = KubernetesPodOperator(
            task_id="run_pdf_to_faiss_job",
            name="pdf-to-faiss-job",
            namespace="default",
            image="271111372751.dkr.ecr.ca-central-1.amazonaws.com/spark-etl:latest",
            cmds=["python"],
            arguments=["/app/pdf_to_faiss.py"],
            get_logs=True,
            is_delete_operator_pod=True,
            service_account_name="spark-runner",
            env_vars={
                "PDF_PATH": "/opt/airflow/data/input.pdf",
                "INDEX_PATH": "/opt/airflow/data/index.faiss",
            },
        )
