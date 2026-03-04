from fastapi import HTTPException

from app.worker.celery_app import celery_app


@celery_app.task(bind=True, name="ingest_pdf_task")
def ingest_pdf_task(self, url: str, replace: bool = False) -> dict:
    """
    Celery task that runs the full PDF ingestion pipeline.

    Delegates to ``ingest_pdf`` from services/milvus.py (unchanged).
    HTTPException raised inside that service is caught and re-raised as a
    plain Exception so Celery can serialise the failure cleanly.
    """
    from app.services.milvus import ingest_pdf

    try:
        result = ingest_pdf(url, replace)
    except HTTPException as exc:
        raise Exception(f"[{exc.status_code}] {exc.detail}") from exc

    return {
        "collection": result.collection,
        "board": result.board,
        "state": result.state,
        "standard": result.standard,
        "subject": result.subject,
        "chunks_inserted": result.chunks_inserted,
        "source_url": result.source_url,
    }
