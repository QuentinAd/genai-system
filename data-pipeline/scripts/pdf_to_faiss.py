import os
from typing import List

import faiss
import numpy as np
from openai import OpenAI
from pypdf import PdfReader


def load_pdf(path: str) -> str:
    reader = PdfReader(path)
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    return text


def chunk_text(text: str, size: int = 1000) -> List[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]


def main() -> None:
    pdf_path = os.getenv("PDF_PATH", "input.pdf")
    index_path = os.getenv("INDEX_PATH", "faiss.index")
    model = os.getenv("EMBED_MODEL", "text-embedding-3-small")

    client = OpenAI()

    text = load_pdf(pdf_path)
    chunks = chunk_text(text)

    embeddings: List[List[float]] = []
    for chunk in chunks:
        resp = client.embeddings.create(model=model, input=[chunk])
        embeddings.append(resp.data[0].embedding)

    if not embeddings:
        raise ValueError("No embeddings created")

    dim = len(embeddings[0])
    index = faiss.IndexFlatL2(dim)
    index.add(np.array(embeddings).astype("float32"))
    faiss.write_index(index, index_path)


if __name__ == "__main__":
    main()
