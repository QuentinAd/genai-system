from datetime import datetime
from airflow import DAG
from airflow.operators.python import PythonOperator
import subprocess


def run_spark_job():
    spark_submit = [
        "spark-submit",
        "--master",
        "local[*]",
        "/opt/airflow/spark_jobs/csv_to_parquet.py",
    ]
    subprocess.run(spark_submit, check=True)


with DAG(
    dag_id="etl_csv_to_parquet",
    start_date=datetime(2023, 1, 1),
    schedule_interval="@once",
    catchup=False,
) as dag:
    etl_task = PythonOperator(
        task_id="run_csv_to_parquet_etl",
        python_callable=run_spark_job,
    )
