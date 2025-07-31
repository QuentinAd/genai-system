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
EMB_DIR = os.path.join(DATA_DIR, "embeddings.npy")
INDEX_PATH = os.path.join(DATA_DIR, "index.faiss")
PDF_PATH = os.path.join(DATA_DIR, "input.pdf")
MODEL = os.getenv("EMBED_MODEL", "text-embedding-3-small")

DEFAULT_ARGS = {
    "start_date": datetime(2025, 1, 1),
    "retries": 1,
}

with DAG(
    dag_id="pdf_to_faiss_python",
    default_args=DEFAULT_ARGS,
    schedule=None,
    description="PDF to FAISS index using pure Python",
    catchup=False,
    tags=["etl", "python", "faiss"],
) as dag:

    def extract_pdf_task():
        """Load PDF and write raw text to file"""
        logger.info(f"Extracting text from {PDF_PATH}")
        text = load_pdf(PDF_PATH)
        with open(RAW_TEXT, "w") as f:
            f.write(text)
        logger.info(f"Raw text saved to {RAW_TEXT}")

    def generate_embeddings_task():
        """Chunk text, generate embeddings, save to numpy file"""
        logger.info(f"Loading raw text from {RAW_TEXT}")
        with open(RAW_TEXT) as f:
            text = f.read()
        logger.info("Chunking text")
        chunks = chunk_text(text)
        # dynamic imports for OpenAI and numpy
        OpenAI = __import__("openai", fromlist=["OpenAI"]).OpenAI
        np = __import__("numpy")
        client = OpenAI()
        embeddings = []
        for chunk in chunks:
            resp = client.embeddings.create(model=MODEL, input=[chunk])
            embeddings.append(resp.data[0].embedding)
        arr = np.array(embeddings, dtype="float32")
        np.save(EMB_DIR, arr)
        logger.info(f"Embeddings saved to {EMB_DIR} (shape={arr.shape})")

    def build_index_task():
        """Load embeddings and build FAISS index"""
        logger.info(f"Loading embeddings from {EMB_DIR}")
        # dynamic imports for numpy and faiss
        np = __import__("numpy")
        faiss = __import__("faiss")
        arr = np.load(EMB_DIR)
        dim = arr.shape[1]
        logger.info(f"Creating FAISS index with dimension {dim}")
        index = faiss.IndexFlatL2(dim)
        index.add(arr)
        logger.info(f"Index contains {index.ntotal} vectors")
        faiss.write_index(index, INDEX_PATH)
        logger.info(f"Index saved to {INDEX_PATH}")

    extract_pdf = PythonOperator(
        task_id="extract_pdf",
        python_callable=extract_pdf_task,
    )

    generate_embeddings = PythonOperator(
        task_id="generate_embeddings",
        python_callable=generate_embeddings_task,
    )

    build_index = PythonOperator(
        task_id="build_index",
        python_callable=build_index_task,
    )

    extract_pdf >> generate_embeddings >> build_index
