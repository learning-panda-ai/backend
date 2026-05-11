"""
Real-time voice chat via Gemini Live API.

Browser <── PCM16 audio (24 kHz) ──> WebSocket <── audio ──> Gemini Live
Browser <── PCM16 audio (16 kHz) ──> WebSocket <── audio ──> Gemini Live
"""

import asyncio
import logging
import uuid

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from google import genai
from google.genai import types as gt
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import _session_factory

logger = logging.getLogger(__name__)
router = APIRouter()

_LIVE_MODEL = "gemini-2.5-flash-native-audio-latest"

_SYSTEM_TEMPLATE = (
    "You are Panda, a friendly and patient AI tutor for Indian school students. "
    "The student is studying {subject} for Class {class_name}. "
    "Keep your responses concise, warm, and easy to follow. "
    "Speak in short conversational sentences — this is a voice call, not a text chat. "
    "If a question is off-topic, gently redirect the student back to {subject}."
)


# ── Auth helper (can't use FastAPI Depends in WS routes) ─────────────────────


async def _resolve_user(token: str):
    """Return User ORM object or None when token is invalid/user missing."""
    from app.models.user import User  # local import — avoids circular dep at load time

    try:
        payload: dict = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError:
        return None

    if payload.get("type") != "access":
        return None

    sub = payload.get("sub")
    if not sub:
        return None

    try:
        user_id = uuid.UUID(sub)
    except ValueError:
        return None

    if _session_factory is None:
        return None

    async with _session_factory() as db:
        return await db.get(User, user_id)


# ── WebSocket endpoint ────────────────────────────────────────────────────────


@router.websocket("/ws/voice")
async def voice_realtime(
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token (httpOnly cookie cannot be forwarded in WS)"),
    subject: str = Query("Mathematics"),
    class_name: str = Query("10"),
):
    """
    Bidirectional real-time voice session.

    Protocol (binary frames = audio, text frames = JSON control):

    Client → Server (binary):  Raw PCM16 mono 16 kHz audio chunks
    Server → Client (binary):  Raw PCM16 mono 24 kHz audio chunks from Gemini
    Server → Client (text):
        {"type": "connected"}           – session ready
        {"type": "turn_complete"}       – model finished its turn
        {"type": "error", "content": …} – fatal error
    """
    user = await _resolve_user(token)
    if user is None:
        await websocket.close(code=4001, reason="Unauthorized")
        return
    if not user.is_active:
        await websocket.close(code=4003, reason="Account not active")
        return

    await websocket.accept()

    system_prompt = _SYSTEM_TEMPLATE.format(subject=subject, class_name=class_name)
    genai_client = genai.Client(
        api_key=settings.GOOGLE_API_KEY,
        http_options={"api_version": "v1alpha"},
    )

    try:
        async with genai_client.aio.live.connect(
            model=_LIVE_MODEL,
            config=gt.LiveConnectConfig(
                response_modalities=["AUDIO"],
                system_instruction=gt.Content(
                    parts=[gt.Part(text=system_prompt)]
                ),
                speech_config=gt.SpeechConfig(
                    voice_config=gt.VoiceConfig(
                        prebuilt_voice_config=gt.PrebuiltVoiceConfig(voice_name="Puck")
                    )
                ),
            ),
        ) as session:
            await websocket.send_json({"type": "connected"})

            async def browser_to_gemini():
                """Receive PCM16 chunks from the browser and forward to Gemini."""
                try:
                    while True:
                        raw = await websocket.receive_bytes()
                        await session.send_realtime_input(
                            media=gt.Blob(data=raw, mime_type="audio/pcm;rate=16000")
                        )
                except WebSocketDisconnect:
                    pass
                except Exception as exc:
                    logger.debug("browser_to_gemini stopped: %s", exc)

            async def gemini_to_browser():
                """Receive audio chunks from Gemini and push to the browser.

                Wraps session.receive() in a while-True loop because the async
                generator exhausts after each turn_complete; re-entering it
                picks up the next turn without restarting the session.
                """
                try:
                    while True:
                        async for msg in session.receive():
                            if not msg.server_content:
                                continue
                            if msg.server_content.model_turn:
                                for part in msg.server_content.model_turn.parts:
                                    if part.inline_data and part.inline_data.data:
                                        await websocket.send_bytes(part.inline_data.data)
                            if msg.server_content.turn_complete:
                                await websocket.send_json({"type": "turn_complete"})
                except WebSocketDisconnect:
                    pass
                except Exception as exc:
                    logger.debug("gemini_to_browser stopped: %s", exc)

            recv_task = asyncio.create_task(browser_to_gemini())
            send_task = asyncio.create_task(gemini_to_browser())

            # gemini_to_browser loops forever; only exits on error/disconnect.
            # browser_to_gemini exits on WebSocket close.
            # Either task completing means the session is over.
            _done, _pending = await asyncio.wait(
                [recv_task, send_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in _pending:
                t.cancel()
                try:
                    await t
                except (asyncio.CancelledError, Exception):
                    pass

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error("Voice WS session error: %s", exc)
        try:
            await websocket.send_json({"type": "error", "content": "Voice session failed. Please try again."})
            await websocket.close()
        except Exception:
            pass
