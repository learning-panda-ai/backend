import redis.asyncio as aioredis
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.core.dependencies import get_current_active_db_user
from app.core.rate_limit import check_agent_chat_rate_limit
from app.core.redis import get_redis
from app.models.user import User
from app.schemas.agent import ChatRequest
from app.services.agent_stream import stream_chat_response

router = APIRouter()


@router.post(
    "/agent/chat",
    summary="Stream a tutor chat response via Server-Sent Events",
    description=(
        "Accepts the student's message, conversation history, class and subject. "
        "Retrieves relevant material from Milvus, then streams the LLM reply as SSE tokens. "
        "Events: `token` (partial text), `done` (stream finished), `error` (failure). "
        "Requires a valid JWT Bearer token. Rate-limited to 50 messages per hour per user."
    ),
    responses={
        200: {"description": "SSE stream of chat tokens.", "content": {"text/event-stream": {}}},
        401: {"description": "Missing, invalid, or expired access token."},
        429: {"description": "Hourly message limit reached."},
        422: {"description": "Validation error."},
    },
)
async def chat_stream(
    body: ChatRequest,
    current_user: User = Depends(get_current_active_db_user),
    redis: aioredis.Redis = Depends(get_redis),
) -> StreamingResponse:
    await check_agent_chat_rate_limit(redis, str(current_user.id))

    history = [{"role": m.role, "content": m.content} for m in body.history]

    return StreamingResponse(
        stream_chat_response(
            message=body.message,
            class_name=body.class_name,
            subject=body.subject,
            history=history,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
