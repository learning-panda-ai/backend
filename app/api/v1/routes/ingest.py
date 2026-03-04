from celery.result import AsyncResult
from fastapi import APIRouter, Depends, Request, status

from app.core.dependencies import get_current_admin_user
from app.models.user import User
from app.schemas.ingest import IngestJobResponse, IngestRequest, IngestStatusResponse
from app.worker.celery_app import celery_app
from app.worker.tasks import ingest_pdf_task

router = APIRouter()

_CELERY_STATE_MAP = {
    "PENDING": "queued",
    "RECEIVED": "queued",
    "STARTED": "processing",
    "RETRY": "processing",
    "SUCCESS": "completed",
    "FAILURE": "failed",
    "REVOKED": "failed",
}


@router.post(
    "/ingest/pdf",
    response_model=IngestJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Enqueue a PDF for ingestion into the Milvus vector database",
    description=(
        "Accepts an S3 PDF URL and immediately enqueues the ingestion pipeline "
        "(Docling + SentenceTransformer + Milvus) as a background Celery task. "
        "Returns a `task_id` that callers can poll via the status endpoint. "
        "Requires a valid JWT Bearer token."
    ),
    responses={
        202: {"description": "PDF ingestion job queued successfully."},
        401: {"description": "Missing, invalid, or expired access token."},
        403: {"description": "Administrator access required."},
        422: {"description": "URL does not end in .pdf or failed Pydantic validation."},
    },
)
async def enqueue_ingest_pdf(
    body: IngestRequest,
    request: Request,
    current_user: User = Depends(get_current_admin_user),
) -> IngestJobResponse:
    task = ingest_pdf_task.delay(str(body.url), body.replace)
    status_url = str(request.url_for("get_ingest_status", task_id=task.id))
    return IngestJobResponse(
        task_id=task.id,
        status="queued",
        status_url=status_url,
    )


@router.get(
    "/ingest/pdf/status/{task_id}",
    response_model=IngestStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Poll the status of a PDF ingestion job",
    description=(
        "Returns the current state of the Celery task identified by `task_id`. "
        "Possible statuses: `queued`, `processing`, `completed`, `failed`. "
        "Requires a valid JWT Bearer token."
    ),
    responses={
        200: {"description": "Task status returned."},
        401: {"description": "Missing, invalid, or expired access token."},
        403: {"description": "Administrator access required."},
    },
)
async def get_ingest_status(
    task_id: str,
    current_user: User = Depends(get_current_admin_user),
) -> IngestStatusResponse:
    async_result = AsyncResult(task_id, app=celery_app)
    friendly_status = _CELERY_STATE_MAP.get(async_result.state, "queued")

    result = None
    error = None

    if async_result.state == "SUCCESS":
        result = async_result.result
    elif async_result.state == "FAILURE":
        error = str(async_result.result)

    return IngestStatusResponse(
        task_id=task_id,
        status=friendly_status,
        result=result,
        error=error,
    )
