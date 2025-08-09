import os
import logging
import time

# Heavy dependencies (faiss, numpy, OpenAI, pypdf) are imported inside functions

# Configure logging
logging.basicConfig(
    level=os.getenv("LOGLEVEL", "INFO").upper(),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def load_pdf(path: str) -> str:
    """Load PDF and extract text with logging"""
    logger.info(f"Starting PDF loading from: {path}")

    if not os.path.exists(path):
        logger.error(f"PDF file not found: {path}")
        raise FileNotFoundError(f"PDF file not found: {path}")

    file_size = os.path.getsize(path)
    logger.info(f"PDF file size: {file_size:,} bytes")

    start_time = time.time()
    from pypdf import PdfReader

    reader = PdfReader(path)
    logger.info(f"PDF loaded successfully. Number of pages: {len(reader.pages)}")

    text_parts = []
    for i, page in enumerate(reader.pages):
        page_text = page.extract_text() or ""
        text_parts.append(page_text)
        if i % 10 == 0:  # Log progress every 10 pages
            logger.debug(f"Processed page {i + 1}/{len(reader.pages)}")

    text = "\n".join(text_parts)
    extraction_time = time.time() - start_time

    logger.info(f"Text extraction completed in {extraction_time:.2f} seconds")
    logger.info(f"Total extracted text length: {len(text):,} characters")

    return text


def chunk_text(text: str, size: int = 1000) -> list[str]:
    """Chunk text into smaller pieces with logging"""
    logger.info(f"Starting text chunking with chunk size: {size}")

    chunks = [text[i : i + size] for i in range(0, len(text), size)]

    logger.info(f"Text chunked into {len(chunks)} pieces")
    # Debug sample chunk sizes
    if chunks:
        logger.debug(f"First chunk length: {len(chunks[0])}")
        logger.debug(f"Last chunk length: {len(chunks[-1])}")

    logger.info(f"Average chunk size: {len(text) / len(chunks):.1f} characters")

    return chunks


def main() -> None:
    """Main function with comprehensive logging"""
    logger.info("=== PDF to FAISS Index Creation Started ===")
    overall_start_time = time.time()

    # Get environment variables
    pdf_path = os.getenv("PDF_PATH", "input.pdf")
    index_path = os.getenv("INDEX_PATH", "faiss.index")
    model = os.getenv("EMBED_MODEL", "text-embedding-3-small")
    # Warn if using defaults
    if "PDF_PATH" not in os.environ:
        logger.warning(f"Using default PDF_PATH: {pdf_path}")
    if "INDEX_PATH" not in os.environ:
        logger.warning(f"Using default INDEX_PATH: {index_path}")
    if "EMBED_MODEL" not in os.environ:
        logger.warning(f"Using default EMBED_MODEL: {model}")

    logger.info("Configuration:")
    logger.info(f"  PDF Path: {pdf_path}")
    logger.info(f"  Index Output Path: {index_path}")
    logger.info(f"  Embedding Model: {model}")

    try:
        # Initialize OpenAI client
        logger.info("Initializing OpenAI client...")
        from openai import OpenAI

        client = OpenAI()
        logger.info("OpenAI client initialized successfully")

        # Load PDF
        text = load_pdf(pdf_path)
        # Chunk text
        chunks = chunk_text(text)
        # Debug chunk content
        logger.debug(f"Total characters: {len(text)}; Total chunks: {len(chunks)}")

        # Generate embeddings
        logger.info("Starting embedding generation...")
        embeddings: list[list[float]] = []
        embedding_start_time = time.time()

        for i, chunk in enumerate(chunks):
            chunk_start_time = time.time()

            try:
                resp = client.embeddings.create(model=model, input=[chunk])
                embeddings.append(resp.data[0].embedding)

                chunk_time = time.time() - chunk_start_time

                # Log progress every 10 chunks or for significant delays
                if i % 10 == 0 or chunk_time > 2.0:
                    logger.info(
                        f"Generated embedding for chunk {i + 1}/{len(chunks)} "
                        f"(took {chunk_time:.2f}s)"
                    )

            except Exception as e:
                logger.error(f"Failed to generate embedding for chunk {i + 1}: {e}")
                raise

        embedding_time = time.time() - embedding_start_time
        logger.info(f"Embedding generation completed in {embedding_time:.2f} seconds")
        logger.info(f"Generated {len(embeddings)} embeddings")
        # Debug embedding matrix shape
        if embeddings:
            logger.debug(f"Embedding vector dimension: {len(embeddings[0])}")
            logger.debug(f"Embeddings array shape: ({len(embeddings)}, {len(embeddings[0])})")
            # Sample embedding values
            sample_first = embeddings[0][:5]
            sample_last = embeddings[-1][:5]
            logger.debug(f"Sample embedding (first 5 values): {sample_first}")
            logger.debug(f"Sample embedding (last 5 values): {sample_last}")

        # Validate embeddings
        if not embeddings:
            logger.error("No embeddings were created")
            raise ValueError("No embeddings created")

        # Create FAISS index
        logger.info("Creating FAISS index...")
        index_start_time = time.time()

        dim = len(embeddings[0])
        logger.info(f"Embedding dimension: {dim}")

        index = faiss.IndexFlatL2(dim)
        embeddings_array = np.array(embeddings).astype("float32")

        logger.info(f"Adding {len(embeddings)} vectors to index...")
        index.add(embeddings_array)

        index_creation_time = time.time() - index_start_time
        logger.info(f"FAISS index created in {index_creation_time:.2f} seconds")
        logger.info(f"Index contains {index.ntotal} vectors")

        # Save index
        logger.info(f"Saving index to: {index_path}")
        save_start_time = time.time()
        # Ensure output directory exists
        output_dir = os.path.dirname(index_path) or "."
        logger.debug(f"Ensuring directory exists: {output_dir}")

        os.makedirs(output_dir, exist_ok=True)
        logger.debug(f"Directory ready: {output_dir}")

        faiss.write_index(index, index_path)

        save_time = time.time() - save_start_time
        logger.info(f"Index saved successfully in {save_time:.2f} seconds")

        # Final summary
        total_time = time.time() - overall_start_time
        logger.info("=== PDF to FAISS Index Creation Completed Successfully ===")
        logger.info(f"Total execution time: {total_time:.2f} seconds")
        logger.info(f"Output file: {index_path}")
        logger.info(f"Index size: {os.path.getsize(index_path):,} bytes")

    except Exception:
        logger.exception("Process failed and is exiting with an error")
        raise


if __name__ == "__main__":
    main()
