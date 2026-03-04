from pydantic import BaseModel


class MessageItem(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    class_name: str
    subject: str
    history: list[MessageItem] = []
