from airflow import DAG
import os

try:  # Airflow 2.x provider package
    from airflow.providers.cncf.kubernetes.operators.kubernetes_pod import (
        KubernetesPodOperator,
    )
except Exception:  # pragma: no cover - provider not installed
    try:  # Airflow 1.10 fallback
        from airflow.contrib.operators.kubernetes_pod_operator import (
            KubernetesPodOperator,
        )
    except Exception:  # pragma: no cover - no Kubernetes support
        KubernetesPodOperator = None  # type: ignore[misc]
from airflow.providers.docker.operators.docker import DockerOperator
from datetime import datetime

default_args = {
    "start_date": datetime(2025, 1, 1),
    "retries": 0,
}

with DAG(
    "etl_csv_to_parquet_k8s",
    schedule_interval=None,
    catchup=False,
    default_args=default_args,
    description="Run PySpark ETL",
) as dag:
    if os.getenv("LOCAL_AIRFLOW", "false").lower() == "true":
        run_spark = DockerOperator(
            task_id="run_spark_job",
            image="spark-etl:local",
            auto_remove=True,
            command="/opt/bitnami/spark/bin/spark-submit /app/etl_job.py",
            docker_url="unix://var/run/docker.sock",
            network_mode="bridge",
        )
    else:
        if KubernetesPodOperator is None:
            raise RuntimeError("KubernetesPodOperator not available")

        run_spark = KubernetesPodOperator(
            task_id="run_spark_job",
            name="spark-etl-job",
            namespace="default",
            image="271111372751.dkr.ecr.ca-central-1.amazonaws.com/spark-etl:latest",
            cmds=["/opt/bitnami/spark/bin/spark-submit"],
            arguments=["/app/etl_job.py"],
            get_logs=True,
            is_delete_operator_pod=True,
            service_account_name="spark-runner",
        )
