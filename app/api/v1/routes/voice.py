import json

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import StreamingResponse

from app.core.dependencies import get_current_active_db_user
from app.core.rate_limit import check_agent_chat_rate_limit
from app.core.redis import get_redis
from app.models.user import User
from app.services.voice_service import stream_voice_response

router = APIRouter()

_SUPPORTED_MIME_TYPES = {
    "audio/webm",
    "audio/webm;codecs=opus",
    "audio/ogg",
    "audio/ogg;codecs=opus",
    "audio/mp4",
    "audio/mpeg",
    "audio/wav",
    "audio/x-m4a",
    "audio/aac",
    "audio/flac",
}


@router.post(
    "/agent/voice",
    summary="Transcribe student audio and stream a tutor response via SSE",
    description=(
        "Accepts a recorded audio blob (multipart/form-data) plus context fields. "
        "Transcribes the audio with Gemini multimodal, then streams the AI tutor reply as SSE tokens. "
        "Events: `transcript` (what the student said), `token` (partial reply), `done`, `error`. "
        "Requires a valid JWT Bearer token. Rate-limited alongside text chat (50 messages/hour per user)."
    ),
    responses={
        200: {"description": "SSE stream.", "content": {"text/event-stream": {}}},
        401: {"description": "Missing or invalid access token."},
        415: {"description": "Unsupported audio MIME type."},
        429: {"description": "Hourly message limit reached."},
        422: {"description": "Validation error."},
    },
)
async def voice_chat(
    audio: UploadFile = File(..., description="Recorded audio blob from the browser MediaRecorder API"),
    class_name: str = Form(..., description="Student's class/grade, e.g. '10'"),
    subject: str = Form(..., description="Subject being studied, e.g. 'Mathematics'"),
    history: str = Form("[]", description="JSON-encoded chat history: [{role, content}]"),
    current_user: User = Depends(get_current_active_db_user),
    redis: aioredis.Redis = Depends(get_redis),
) -> StreamingResponse:
    await check_agent_chat_rate_limit(redis, str(current_user.id))

    # Validate MIME type (normalise by stripping codec suffix for the check)
    mime_type = (audio.content_type or "audio/webm").lower()
    base_mime = mime_type.split(";")[0].strip()
    if base_mime not in {m.split(";")[0] for m in _SUPPORTED_MIME_TYPES}:
        from fastapi import HTTPException
        raise HTTPException(status_code=415, detail=f"Unsupported audio type: {mime_type}")

    audio_bytes = await audio.read()

    try:
        parsed_history: list[dict] = json.loads(history)
        if not isinstance(parsed_history, list):
            parsed_history = []
    except (json.JSONDecodeError, ValueError):
        parsed_history = []

    return StreamingResponse(
        stream_voice_response(
            audio_bytes=audio_bytes,
            mime_type=mime_type,
            class_name=class_name,
            subject=subject,
            history=parsed_history,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
