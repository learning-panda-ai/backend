"""
Voice/audio service: transcribes audio via Gemini multimodal, then streams a tutor response.
"""

import asyncio
import json
from typing import AsyncGenerator

from google import genai
from google.genai import types

from app.core.config import settings
from app.services.agent_stream import stream_chat_response

_genai_client: genai.Client | None = None


def _get_genai_client() -> genai.Client:
    global _genai_client
    if _genai_client is None:
        _genai_client = genai.Client(api_key=settings.GOOGLE_API_KEY)
    return _genai_client


def _transcribe_sync(audio_bytes: bytes, mime_type: str) -> str:
    """Sync transcription via Gemini multimodal — runs in a thread."""
    client = _get_genai_client()
    response = client.models.generate_content(
        model=settings.GOOGLE_AGENT,
        contents=types.Content(
            role="user",
            parts=[
                types.Part(
                    inline_data=types.Blob(data=audio_bytes, mime_type=mime_type)
                ),
                types.Part(
                    text=(
                        "Transcribe this audio question from a student. "
                        "Return ONLY the transcribed text with no preamble, labels, or commentary. "
                        "If the audio is unclear or silent, return an empty string."
                    )
                ),
            ],
        ),
    )
    return (response.text or "").strip()


async def stream_voice_response(
    audio_bytes: bytes,
    mime_type: str,
    class_name: str,
    subject: str,
    history: list[dict],
) -> AsyncGenerator[str, None]:
    """
    Async generator yielding SSE-formatted strings for a voice interaction.

    Event sequence:
      data: {"type": "transcript", "content": "<student question>"}
      data: {"type": "token",      "content": "<partial AI reply>"}  (repeated)
      data: {"type": "done"}
      data: {"type": "error",      "content": "<message>"}           (on failure)
    """
    try:
        transcript = await asyncio.to_thread(_transcribe_sync, audio_bytes, mime_type)
    except Exception as exc:
        yield f"data: {json.dumps({'type': 'error', 'content': f'Transcription failed: {exc}'})}\n\n"
        return

    if not transcript:
        yield f"data: {json.dumps({'type': 'error', 'content': 'Could not understand the audio. Please try again.'})}\n\n"
        return

    yield f"data: {json.dumps({'type': 'transcript', 'content': transcript})}\n\n"

    async for event in stream_chat_response(
        message=transcript,
        class_name=class_name,
        subject=subject,
        history=history,
    ):
        yield event
