import uuid
from urllib.parse import quote

import boto3
import filetype
from botocore.exceptions import ClientError, NoCredentialsError
from fastapi import HTTPException, UploadFile, status

from app.core.config import settings
from app.schemas.upload import Board, Standard, Subject

# Allowlist of accepted MIME types. Extend as the product requires.
ALLOWED_CONTENT_TYPES: frozenset[str] = frozenset(
    {
        # Images
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
        "image/svg+xml",
        # Documents
        "application/pdf",
        # Video
        "video/mp4",
        "video/webm",
        # Audio
        "audio/mpeg",
        "audio/wav",
        "audio/ogg",
    }
)


def _s3_client():
    return boto3.client(
        "s3",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION,
    )


def _build_object_key(
    filename: str,
    board: Board,
    state: str,
    standard: Standard,
    subject: Subject,
) -> str:
    """
    Construct a safe, well-organised S3 object key.

    Layout: uploads/{board}/{state}/{standard}/{subject}/{uuid}.{ext}

    Examples:
      uploads/CBSE/Central/Class 10/Mathematics/3f2a1b....pdf
      uploads/State Board/Maharashtra/Class 10/Mathematics/3f2a1b....pdf

    The user-supplied filename is never used directly — only its extension is
    kept so that browsers can infer the content type correctly.
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    unique_name = f"{uuid.uuid4().hex}.{ext}" if ext else uuid.uuid4().hex
    return (
        f"{settings.S3_KEY_PREFIX}"
        f"/{board.value}/{state}/{standard.value}/{subject.value}"
        f"/{unique_name}"
    )


async def upload_file_to_s3(
    file: UploadFile,
    board: Board,
    state: str,
    standard: Standard,
    subject: Subject,
) -> str:
    """
    Validate *file*, upload it to S3, and return its public URL.

    Raises:
        HTTP 415 — unsupported media type.
        HTTP 413 — file exceeds the configured size limit.
        HTTP 500 — AWS credential or S3 error.
    """
    # 1. MIME type validation
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"File type '{file.content_type}' is not supported. "
                f"Allowed types: {sorted(ALLOWED_CONTENT_TYPES)}"
            ),
        )

    # 2. Enforce size limit via Content-Length header before reading the body.
    #    Then stream-read with a hard cap so a lying/missing header is still safe.
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    declared_size = file.size  # populated by python-multipart from Content-Length
    if declared_size is not None and declared_size > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size exceeds the {settings.MAX_UPLOAD_SIZE_MB} MB limit.",
        )

    # Read in chunks so an absent/forged Content-Length cannot exhaust memory
    chunks: list[bytes] = []
    total = 0
    chunk_size = 256 * 1024  # 256 KB
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File size exceeds the {settings.MAX_UPLOAD_SIZE_MB} MB limit.",
            )
        chunks.append(chunk)

    content = b"".join(chunks)

    if total == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    # 3. Magic-byte MIME verification — client-supplied Content-Type can be spoofed.
    #    Detect the actual type from file bytes and reject if it doesn't match the allowlist.
    detected = filetype.guess(content)
    actual_mime = detected.mime if detected else "application/octet-stream"
    if actual_mime not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"File content does not match an allowed type "
                f"(detected: '{actual_mime}'). "
                f"Allowed types: {sorted(ALLOWED_CONTENT_TYPES)}"
            ),
        )

    # 4. Upload to S3
    key = _build_object_key(file.filename or "file", board, state, standard, subject)
    try:
        _s3_client().put_object(
            Bucket=settings.S3_BUCKET_NAME,
            Key=key,
            Body=content,
            ContentType=actual_mime,  # use verified type, not client-supplied header
        )
    except NoCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AWS credentials are misconfigured.",
        )
    except ClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"S3 upload failed: {exc.response['Error']['Message']}",
        )

    # 4. Return the permanent object URL (percent-encode spaces/special chars,
    #    but keep '/' intact so the path structure is preserved).
    url = (
        f"https://{settings.S3_BUCKET_NAME}"
        f".s3.{settings.AWS_REGION}.amazonaws.com/{quote(key, safe='/')}"
    )
    return url

