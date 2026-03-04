import uuid
from datetime import datetime, timezone
from typing import Optional

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_admin_user
from app.models.admin_user import AdminUser
from app.models.uploaded_file import UploadedFile
from app.schemas.upload import Board, Standard, State, Subject, UploadedFileOut
from app.services.s3 import upload_file_to_s3
from app.worker.celery_app import celery_app

router = APIRouter(tags=["Storage"])

_CELERY_STATE_MAP = {
    "PENDING": "queued",
    "RECEIVED": "queued",
    "STARTED": "processing",
    "RETRY": "processing",
    "SUCCESS": "completed",
    "FAILURE": "failed",
    "REVOKED": "failed",
}


# ── Upload ─────────────────────────────────────────────────────────────────────

@router.post(
    "/upload",
    response_model=UploadedFileOut,
    summary="Upload a file to S3",
    description=(
        "Uploads a file to AWS S3 and returns the file record including ingest status. "
        "Requires a valid admin JWT Bearer token in the Authorization header."
    ),
    responses={
        200: {"description": "File uploaded successfully."},
        400: {"description": "Empty file provided."},
        401: {"description": "Missing, invalid, or expired access token."},
        403: {"description": "Administrator access required."},
        413: {"description": "File exceeds the allowed size limit."},
        415: {"description": "File type is not supported."},
        422: {"description": "Invalid board / standard / subject / state value."},
        500: {"description": "Internal AWS/S3 error."},
    },
)
async def upload_file(
    board: Board = Form(..., description=f"Allowed values: {[e.value for e in Board]}"),
    standard: Standard = Form(..., description=f"Allowed values: {[e.value for e in Standard]}"),
    subject: Subject = Form(..., description=f"Allowed values: {[e.value for e in Subject]}"),
    state: Optional[State] = Form(
        None,
        description=(
            f"Required only when board is 'State Board'. "
            f"Ignored for all other boards (resolved to 'Central'). "
            f"Allowed values: {[e.value for e in State]}"
        ),
    ),
    file: UploadFile = File(..., description="The file to upload."),
    current_user: AdminUser = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> UploadedFileOut:
    if board == Board.STATE_BOARD:
        resolved_state = state.value if state else "Unspecified"
    else:
        resolved_state = "Central"

    url = await upload_file_to_s3(file, board, resolved_state, standard, subject)

    record = UploadedFile(
        filename=file.filename or "",
        s3_url=url,
        content_type=file.content_type or "application/octet-stream",
        board=board.value,
        standard=standard.value,
        subject=subject.value,
        state=resolved_state,
        uploaded_by=current_user.id,
        ingest_status="pending",
    )
    db.add(record)
    await db.flush()
    return UploadedFileOut.model_validate(record)


# ── File listing ───────────────────────────────────────────────────────────────

@router.get(
    "/files",
    response_model=list[UploadedFileOut],
    summary="List all uploaded files",
    description="Returns all uploaded files ordered by upload time (newest first).",
    responses={
        200: {"description": "File list returned."},
        401: {"description": "Missing or invalid admin token."},
    },
)
async def list_files(
    current_user: AdminUser = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> list[UploadedFileOut]:
    result = await db.execute(
        select(UploadedFile).order_by(UploadedFile.uploaded_at.desc())
    )
    files = result.scalars().all()
    return [UploadedFileOut.model_validate(f) for f in files]


# ── Ingest trigger ─────────────────────────────────────────────────────────────

@router.post(
    "/files/{file_id}/ingest",
    response_model=UploadedFileOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger ingestion for an uploaded file",
    description=(
        "Enqueues the PDF ingestion pipeline (Docling → SentenceTransformer → Milvus) "
        "for the given file. Sets ingest_status to 'queued' immediately."
    ),
    responses={
        202: {"description": "Ingestion queued."},
        404: {"description": "File not found."},
        401: {"description": "Missing or invalid admin token."},
    },
)
async def ingest_file(
    file_id: uuid.UUID,
    current_user: AdminUser = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> UploadedFileOut:
    file = await db.get(UploadedFile, file_id)
    if file is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")

    task = celery_app.send_task("ingest_pdf_task", args=[file.s3_url, False])

    file.ingest_status = "queued"
    file.celery_task_id = task.id
    file.ingested_at = None
    await db.flush()

    return UploadedFileOut.model_validate(file)


# ── Ingest status refresh ──────────────────────────────────────────────────────

@router.get(
    "/files/{file_id}/ingest-status",
    response_model=UploadedFileOut,
    summary="Refresh and return ingest status for a file",
    description=(
        "Polls the Celery task for the latest state, persists it to the database, "
        "and returns the updated file record."
    ),
    responses={
        200: {"description": "Updated file record returned."},
        404: {"description": "File not found."},
        401: {"description": "Missing or invalid admin token."},
    },
)
async def get_file_ingest_status(
    file_id: uuid.UUID,
    current_user: AdminUser = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> UploadedFileOut:
    file = await db.get(UploadedFile, file_id)
    if file is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")

    # If there is an active Celery task, poll it and update the stored status
    if file.celery_task_id and file.ingest_status in ("queued", "processing"):
        async_result = AsyncResult(file.celery_task_id, app=celery_app)
        new_status = _CELERY_STATE_MAP.get(async_result.state, "queued")
        file.ingest_status = new_status
        if new_status == "completed" and file.ingested_at is None:
            file.ingested_at = datetime.now(timezone.utc)
        await db.flush()

    return UploadedFileOut.model_validate(file)

