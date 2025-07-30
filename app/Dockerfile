FROM python:3.12-slim
WORKDIR /app
COPY app/requirements.txt app/
RUN pip install --no-cache-dir -r app/requirements.txt
COPY app/ app/
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000", "app.main:app"]
