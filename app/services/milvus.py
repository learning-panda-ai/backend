"""
Milvus vector-database ingestion service.

Pipeline:
    S3 PDF URL → download → Docling convert+chunk → SentenceTransformer embed
    → Milvus upsert

Design notes:
  • All heavy models (DocumentConverter, HybridChunker, SentenceTransformer) are
    lazy-loaded and cached as module-level singletons — the first request pays the
    warm-up cost; every subsequent request is fast.
  • This module is intentionally synchronous / CPU-bound.  Call `ingest_pdf` via
    `asyncio.to_thread` from async FastAPI handlers so the event loop stays free.
  • The embedding model and dimension MUST match the retriever in agent.py.
"""

import os
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

from docling.chunking import HybridChunker
from docling.document_converter import DocumentConverter
from fastapi import HTTPException, status
from pymilvus import MilvusClient
from sentence_transformers import SentenceTransformer

from app.core.config import settings

# ---------------------------------------------------------------------------
# Constants — must stay in sync with learning_panda_agent/agent.py
# ---------------------------------------------------------------------------
_EMBED_MODEL = "all-MiniLM-L12-v2"
_EMBED_DIM = 384
_BATCH_SIZE = 100  # keep Milvus payloads small


# ---------------------------------------------------------------------------
# Lazy-loaded, module-level singletons (one copy per worker process)
# ---------------------------------------------------------------------------
_converter: DocumentConverter | None = None
_chunker: HybridChunker | None = None
_embedder: SentenceTransformer | None = None


def _get_converter() -> DocumentConverter:
    global _converter
    if _converter is None:
        _converter = DocumentConverter()
    return _converter


def _get_chunker() -> HybridChunker:
    global _chunker
    if _chunker is None:
        _chunker = HybridChunker()
    return _chunker


def _get_embedder() -> SentenceTransformer:
    global _embedder
    if _embedder is None:
        _embedder = SentenceTransformer(_EMBED_MODEL)
    return _embedder


# ---------------------------------------------------------------------------
# Internal data classes (not exposed as API schemas)
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class _PDFMetadata:
    board: str
    state: str
    standard: str
    subject: str
    collection_name: str


@dataclass(frozen=True, slots=True)
class IngestResult:
    collection: str
    board: str
    state: str
    standard: str
    subject: str
    chunks_inserted: int
    source_url: str


# ---------------------------------------------------------------------------
# URL parsing
# ---------------------------------------------------------------------------

def _collection_name(standard: str, subject: str) -> str:
    """
    Build a Milvus collection name that is compatible with agent.py.

    Examples:
        "Class 1",  "Mathematics" → "class_1_mathematics"
        "Class 10", "Science"     → "class_10_science"
    """
    # Strip the leading "Class " / "class " prefix to get just the number
    class_num = standard.lower().replace("class", "").strip().replace(" ", "_")
    subj_slug = subject.strip().lower().replace(" ", "_")
    return f"class_{class_num}_{subj_slug}"


def parse_s3_url(url: str) -> _PDFMetadata:
    """
    Extract board / state / standard / subject from an S3 PDF URL.

    Expected path layout (URL-encoded):
        /<prefix>/<board>/<state>/<standard>/<subject>/<uuid>.pdf

    Example:
        /uploads/CBSE/Central/Class%201/Mathematics/384b2221....pdf
        → board="CBSE", state="Central", standard="Class 1", subject="Mathematics"
    """
    parsed = urlparse(url)
    path = unquote(parsed.path)          # decode %20 → space, etc.
    parts = [p for p in path.split("/") if p]   # drop empty segments

    # Minimum: prefix / board / state / standard / subject / filename
    if len(parts) < 6:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "URL path does not match the expected S3 layout: "
                "/<prefix>/<board>/<state>/<standard>/<subject>/<filename>.pdf"
            ),
        )

    board = parts[1]
    state = parts[2]
    standard = parts[3]
    subject = parts[4]

    for field, value in (("board", board), ("state", state), ("standard", standard), ("subject", subject)):
        if not value.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Could not extract '{field}' from the URL path.",
            )

    return _PDFMetadata(
        board=board,
        state=state,
        standard=standard,
        subject=subject,
        collection_name=_collection_name(standard, subject),
    )


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def _download_pdf(url: str) -> Path:
    """
    Stream PDF from *url* into a named temporary file.

    Returns the temp-file path.  The caller MUST delete it after use.
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp_path = Path(tmp.name)
    tmp.close()  # close so urllib can write to it on all OSes

    try:
        urllib.request.urlretrieve(url, tmp_path)
    except Exception as exc:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to download PDF from S3: {exc}",
        )

    return tmp_path


# ---------------------------------------------------------------------------
# PDF → chunks
# ---------------------------------------------------------------------------

def _extract_chunks(pdf_path: Path) -> list[str]:
    """
    Convert PDF with Docling and apply hybrid chunking.
    Returns a list of non-empty, contextualized chunk strings.
    """
    converter = _get_converter()
    chunker = _get_chunker()

    result = converter.convert(str(pdf_path))
    chunks: list[str] = []
    for chunk in chunker.chunk(dl_doc=result.document):
        text = chunker.contextualize(chunk=chunk)
        if text and text.strip():
            chunks.append(text)

    return chunks


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ingest_pdf(url: str, replace: bool = False) -> IngestResult:
    """
    Full ingestion pipeline (synchronous / CPU-bound).

    1. Parse metadata from the S3 URL.
    2. Download PDF to a temp file.
    3. Convert → chunk with Docling.
    4. Embed chunks with SentenceTransformer.
    5. Upsert into the appropriate Milvus collection.
    6. Return an IngestResult summary.

    Call this via ``asyncio.to_thread(ingest_pdf, url, replace)`` from async
    FastAPI handlers to avoid blocking the event loop.
    """
    metadata = parse_s3_url(url)

    # --- Download ---
    pdf_path = _download_pdf(url)

    # --- Convert & chunk (always clean up the temp file) ---
    try:
        chunks = _extract_chunks(pdf_path)
    finally:
        try:
            os.unlink(pdf_path)
        except OSError:
            pass

    if not chunks:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No text content could be extracted from the PDF.",
        )

    # --- Embed ---
    embedder = _get_embedder()
    # show_progress_bar=False keeps server logs clean; progress isn't useful here
    embeddings = embedder.encode(chunks, show_progress_bar=False)

    # --- Milvus upsert ---
    client = MilvusClient(settings.MILVUS_URI)
    collection = metadata.collection_name

    if replace and client.has_collection(collection):
        client.drop_collection(collection)

    if not client.has_collection(collection):
        client.create_collection(
            collection_name=collection,
            dimension=_EMBED_DIM,
            metric_type="IP",
            consistency_level="Strong",
        )

    # In append mode, start IDs after the last existing row to avoid conflicts
    start_id = 0
    if not replace and client.has_collection(collection):
        stats = client.get_collection_stats(collection)
        start_id = int(stats.get("row_count", 0))

    rows = [
        {"id": start_id + i, "vector": emb.tolist(), "text": text}
        for i, (emb, text) in enumerate(zip(embeddings, chunks))
    ]

    for batch_start in range(0, len(rows), _BATCH_SIZE):
        client.insert(
            collection_name=collection,
            data=rows[batch_start : batch_start + _BATCH_SIZE],
        )

    return IngestResult(
        collection=collection,
        board=metadata.board,
        state=metadata.state,
        standard=metadata.standard,
        subject=metadata.subject,
        chunks_inserted=len(rows),
        source_url=url,
    )
