from airflow import DAG
import os
from airflow.providers.docker.operators.docker import DockerOperator
from datetime import datetime
import logging

# Configure logging
logger = logging.getLogger(__name__)

DEFAULT_ARGS = {
    "start_date": datetime(2025, 1, 1),
    "retries": 0,
    "on_failure_callback": lambda context: logger.error(
        f"Task failed: {context['task_instance'].task_id}"
    ),
    "on_success_callback": lambda context: logger.info(
        f"Task completed successfully: {context['task_instance'].task_id}"
    ),
}

with DAG(
    dag_id="pdf_to_faiss",
    schedule=None,  # Manual trigger
    default_args=DEFAULT_ARGS,
    description="Create FAISS index from PDF",
    catchup=False,
    tags=["etl", "pdf", "faiss", "embeddings"],
) as dag:
    # Log AWS environment for debug (mask sensitive values)
    aws_key_present = "AWS_ACCESS_KEY_ID" in os.environ
    aws_region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    logger.info(f"AWS creds present: {aws_key_present}, AWS region: {aws_region}")
    run_job = DockerOperator(
        task_id="run_pdf_to_faiss_job",
        image="spark-etl:local",
        auto_remove="success",  # Valid options: 'never', 'success', 'force'
        command="python /app/pdf_to_faiss.py",
        docker_url="unix://var/run/docker.sock",
        network_mode="bridge",
        environment={
            "PDF_PATH": "/opt/airflow/data/input.pdf",
            "INDEX_PATH": "/opt/airflow/data/index.faiss",
            "PYTHONUNBUFFERED": "1",
            "LOGLEVEL": "INFO",
            # Pass AWS credentials for S3 access
            "AWS_ACCESS_KEY_ID": os.getenv("AWS_ACCESS_KEY_ID", ""),
            "AWS_SECRET_ACCESS_KEY": os.getenv("AWS_SECRET_ACCESS_KEY", ""),
            "AWS_SESSION_TOKEN": os.getenv("AWS_SESSION_TOKEN", ""),
            "AWS_REGION": os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "")),
            "AWS_DEFAULT_REGION": os.getenv("AWS_DEFAULT_REGION", ""),
            "AWS_PROFILE": os.getenv("AWS_PROFILE", ""),
            "AWS_DEFAULT_PROFILE": os.getenv("AWS_DEFAULT_PROFILE", ""),
        },
        retrieve_output=True,
        retrieve_output_path="/tmp/script.out",
        # Enhanced logging configuration
        xcom_all=True,  # Return all outputs as XCom
        do_xcom_push=True,
    )
