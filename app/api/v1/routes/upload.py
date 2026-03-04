from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.core.dependencies import get_current_admin_user
from app.models.user import User
from app.schemas.upload import Board, Standard, State, Subject
from app.services.s3 import upload_file_to_s3

router = APIRouter()


@router.post(
    "/upload",
    summary="Upload a file to S3",
    description=(
        "Uploads a file to AWS S3 and returns its URL. "
        "Requires a valid JWT Bearer token in the Authorization header. "
        "When `board` is 'State Board', `state` is accepted from the allowed list. "
        "For all other boards, `state` is automatically set to 'Central'."
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
    current_user: User = Depends(get_current_admin_user),
):
    """
    Authenticated file upload endpoint.

    State resolution rules:
    - board == 'State Board' → use the provided `state` value (defaults to 'Unspecified' if omitted).
    - board == anything else  → `state` is always 'Central', regardless of what was sent.
    """
    if board == Board.STATE_BOARD:
        resolved_state = state.value if state else "Unspecified"
    else:
        resolved_state = "Central"

    url = await upload_file_to_s3(file, board, resolved_state, standard, subject)
    return {
        "url": url,
        "filename": file.filename,
        "content_type": file.content_type,
        "board": board.value,
        "state": resolved_state,
        "standard": standard.value,
        "subject": subject.value,
        "uploaded_by": str(current_user.id),
    }
