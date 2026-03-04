"""
Chat session persistence endpoints.

POST   /chat/sessions                       — create a new session
GET    /chat/sessions                       — list user's sessions (newest first, max 20)
GET    /chat/sessions/{session_id}          — get session + messages
DELETE /chat/sessions/{session_id}          — delete session (cascades messages)
POST   /chat/sessions/{session_id}/messages — bulk-save messages, bump updated_at
"""
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.dependencies import get_current_db_user
from app.models.chat import ChatMessage, ChatSession
from app.models.user import User
from app.schemas.chat import (
    CreateSessionRequest,
    SaveMessagesRequest,
    SessionDetailOut,
    SessionOut,
)

router = APIRouter(prefix="/chat", tags=["Chat"])
logger = logging.getLogger(__name__)


@router.post("/sessions", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
async def create_session(
    body: CreateSessionRequest,
    current_user: User = Depends(get_current_db_user),
    db: AsyncSession = Depends(get_db),
) -> SessionOut:
    session = ChatSession(
        user_id=current_user.id,
        subject=body.subject,
        class_name=body.class_name,
        title=body.title[:160],
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    logger.info("User %s created chat session %s", current_user.id, session.id)
    return SessionOut.model_validate(session)


@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(
    current_user: User = Depends(get_current_db_user),
    db: AsyncSession = Depends(get_db),
) -> list[SessionOut]:
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == current_user.id)
        .order_by(ChatSession.updated_at.desc())
        .limit(20)
    )
    sessions = result.scalars().all()
    return [SessionOut.model_validate(s) for s in sessions]


@router.get("/sessions/{session_id}", response_model=SessionDetailOut)
async def get_session(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_db_user),
    db: AsyncSession = Depends(get_db),
) -> SessionDetailOut:
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.id == session_id)
        .options(selectinload(ChatSession.messages))
    )
    session = result.scalar_one_or_none()
    if session is None or session.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
    return SessionDetailOut.model_validate(session)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_db_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if session is None or session.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
    await db.delete(session)
    await db.commit()
    logger.info("User %s deleted chat session %s", current_user.id, session_id)


@router.post("/sessions/{session_id}/messages")
async def save_messages(
    session_id: uuid.UUID,
    body: SaveMessagesRequest,
    current_user: User = Depends(get_current_db_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if session is None or session.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

    now = datetime.now(timezone.utc)
    for msg in body.messages:
        db.add(
            ChatMessage(
                session_id=session_id,
                role=msg.role,
                content=msg.content,
                created_at=now,
            )
        )

    # Explicitly set updated_at since bulk inserts don't trigger onupdate
    session.updated_at = now
    await db.commit()

    return {"saved": len(body.messages)}
