from airflow import DAG
from airflow.providers.cncf.kubernetes.operators.kubernetes_pod import (
    KubernetesPodOperator,
)
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
    description="Run PySpark ETL in KubernetesPodOperator",
) as dag:
    run_spark = KubernetesPodOperator(
        task_id="run_spark_job",
        name="spark-etl-job",
        namespace="default",
        image="271111372751.dkr.ecr.ca-central-1.amazonaws.com/spark-etl:latest",
        cmds=["/opt/bitnami/spark/bin/spark-submit"],
        arguments=["/app/etl_job.py"],
        get_logs=True,
        is_delete_operator_pod=True,
    )
