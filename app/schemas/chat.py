import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CreateSessionRequest(BaseModel):
    subject: str
    class_name: str
    title: str


class MessageIn(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class SaveMessagesRequest(BaseModel):
    messages: list[MessageIn]


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: str
    content: str
    created_at: datetime


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    subject: str
    class_name: str
    title: str
    created_at: datetime
    updated_at: datetime


class SessionDetailOut(SessionOut):
    messages: list[MessageOut] = []
