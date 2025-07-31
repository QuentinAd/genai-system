# Custom Airflow image with project dependencies installed
FROM apache/airflow:3.0.3
USER root

# Install project Python dependencies
COPY data-pipeline/requirements.txt /opt/airflow/requirements.txt
RUN pip install --no-cache-dir -r /opt/airflow/requirements.txt

# Restore non-root user
USER airflow
