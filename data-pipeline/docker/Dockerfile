FROM bitnami/spark:3.4.1

USER root

RUN pip install pandas boto3 pyarrow s3fs

ENV PYSPARK_PYTHON=python3
ENV PYSPARK_DRIVER_PYTHON=python3

COPY etl_job.py /app/etl_job.py
WORKDIR /app

ENTRYPOINT ["spark-submit", "etl_job.py"]
