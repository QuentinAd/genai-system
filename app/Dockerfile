FROM python:3.12-slim
WORKDIR /app
COPY app/requirements.txt app/
RUN pip install --no-cache-dir -r app/requirements.txt
COPY app/ app/
# Copy entire FAISS index directory for RAG
RUN mkdir -p data
COPY data-pipeline/data data
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000", "app.main:app"]
