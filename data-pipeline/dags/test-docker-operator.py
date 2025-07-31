from airflow import DAG
from airflow.providers.docker.operators.docker import DockerOperator
from datetime import datetime

DEFAULT_ARGS = {
    "start_date": datetime(2025, 1, 1),
    "retries": 0,
}

with DAG(
    dag_id="test_docker",
    schedule=None,
    default_args=DEFAULT_ARGS,
    description="Test Docker Operator",
) as dag:
    test_docker = DockerOperator(
        task_id="test_docker_task",
        image="hello-world",
        auto_remove="success",
        docker_url="unix://var/run/docker.sock",
        network_mode="bridge",
    )
