from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime
import os
import logging


# Define helper functions inline to avoid external imports
def load_pdf(path: str) -> str:
    """Load PDF and extract text"""
    # dynamic import to avoid DAG parsing errors
    # Attempt to import PdfReader from pypdf, else fall back to PyPDF2
    try:
        PdfReader = __import__("pypdf", fromlist=["PdfReader"]).PdfReader
    except ImportError:
        try:
            from PyPDF2 import PdfReader
        except ImportError:
            logger.error("Neither pypdf nor PyPDF2 is available. Install pypdf>=3.9 or PyPDF2>=2.0")
            raise
    reader = PdfReader(path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def chunk_text(text: str, size: int = 1000) -> list[str]:
    """Chunk text into list of strings"""
    return [text[i : i + size] for i in range(0, len(text), size)]


# Heavy dependencies will be imported inside tasks to avoid DAG parsing errors

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Shared paths
DATA_DIR = "/opt/airflow/data"
RAW_TEXT = os.path.join(DATA_DIR, "raw_text.txt")
CHROMA_DIR = os.path.join(DATA_DIR, "chroma")
PDF_PATH = os.path.join(DATA_DIR, "input.pdf")
MODEL = os.getenv("EMBED_MODEL", "text-embedding-3-small")

DEFAULT_ARGS = {
    "start_date": datetime(2025, 1, 1),
    "retries": 1,
}

with DAG(
    dag_id="pdf_to_chroma_python_python",
    default_args=DEFAULT_ARGS,
    schedule=None,
    description="PDF to ChromaDB index using pure Python",
    catchup=False,
    tags=["etl", "python", "chroma", "embeddings"],
) as dag:

    def extract_pdf_task():
        """Load PDF and write raw text to file"""
        logger.info(f"Extracting text from {PDF_PATH}")
        text = load_pdf(PDF_PATH)
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(RAW_TEXT, "w", encoding="utf-8") as f:
            f.write(text)
        logger.info(f"Raw text saved to {RAW_TEXT}")

    def build_chroma_task():
        """Chunk text and persist Chroma collection on disk"""
        logger.info(f"Loading raw text from {RAW_TEXT}")
        with open(RAW_TEXT, encoding="utf-8") as f:
            text = f.read()
        logger.info("Chunking text")
        chunks = chunk_text(text)
        # Dynamic imports to avoid import errors during DAG parse
        doc_mod = __import__("langchain.schema", fromlist=["Document"])
        Document = doc_mod.Document
        emb_mod = __import__("langchain_openai", fromlist=["OpenAIEmbeddings"])
        OpenAIEmbeddings = emb_mod.OpenAIEmbeddings
        vc_mod = __import__("langchain_community.vectorstores", fromlist=["Chroma"])
        Chroma = vc_mod.Chroma

        docs = [Document(page_content=c) for c in chunks]
        os.makedirs(CHROMA_DIR, exist_ok=True)
        logger.info(f"Building Chroma vectorstore in {CHROMA_DIR}")
        embeddings = OpenAIEmbeddings(model=MODEL)
        Chroma.from_documents(
            documents=docs,
            embedding=embeddings,
            persist_directory=CHROMA_DIR,
        )
        # Chroma >=0.4 persists automatically on creation
        logger.info("Chroma vectorstore persisted successfully")

    extract_pdf = PythonOperator(
        task_id="extract_pdf",
        python_callable=extract_pdf_task,
    )

    build_chroma = PythonOperator(
        task_id="build_chroma",
        python_callable=build_chroma_task,
    )

    extract_pdf >> build_chroma
