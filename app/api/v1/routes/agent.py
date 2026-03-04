from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.core.dependencies import get_current_user
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
        "Requires a valid JWT Bearer token."
    ),
    responses={
        200: {"description": "SSE stream of chat tokens.", "content": {"text/event-stream": {}}},
        401: {"description": "Missing, invalid, or expired access token."},
        422: {"description": "Validation error."},
    },
)
async def chat_stream(
    body: ChatRequest,
    current_user: dict = Depends(get_current_user),
) -> StreamingResponse:
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
