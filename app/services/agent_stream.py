"""
Streaming chat service using Milvus RAG + Gemini LLM.
Mirrors the logic in learning_panda_agent/agent.py but streams tokens via async generator.
"""

import asyncio
import json
import re
from typing import AsyncGenerator

from langchain_google_genai import ChatGoogleGenerativeAI
from pymilvus import MilvusClient
from sentence_transformers import SentenceTransformer

from app.core.config import settings

_SYSTEM_PROMPT = """You are a friendly and patient tutor helping a student clear their doubts.
Use the following retrieved context from the course material when it is relevant to the student's question.
If the context does not contain enough information, say so and answer from general knowledge where appropriate.
Keep explanations clear and concise. Encourage the student to ask follow-up questions."""

_embedder: SentenceTransformer | None = None
_llm: ChatGoogleGenerativeAI | None = None


def _get_embedder() -> SentenceTransformer:
    global _embedder
    if _embedder is None:
        _embedder = SentenceTransformer("all-MiniLM-L12-v2")
    return _embedder


def _get_llm() -> ChatGoogleGenerativeAI:
    global _llm
    if _llm is None:
        _llm = ChatGoogleGenerativeAI(model=settings.GOOGLE_AGENT, temperature=0)
    return _llm


def _normalize_content(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and "text" in part:
                parts.append(str(part["text"]))
            else:
                parts.append(str(part))
        return "\n".join(parts).strip()
    return str(content)


def _retrieve_docs(query: str, class_name: str, subject: str, top_k: int = 5) -> list[str]:
    """Sync retrieval from Milvus — called via asyncio.to_thread."""
    c = class_name.strip().lower().replace(" ", "_")
    s = subject.strip().lower().replace(" ", "_")
    raw = f"class_{c}_{s}"
    collection_name = re.sub(r"_+", "_", re.sub(r"[^a-z0-9_]", "_", raw)).strip("_")

    client = MilvusClient(settings.MILVUS_URI)
    if not client.has_collection(collection_name):
        return []

    query_vector = _get_embedder().encode(query)
    results = client.search(
        collection_name=collection_name,
        data=[query_vector],
        limit=top_k,
        search_params={"metric_type": "IP", "params": {}},
        output_fields=["text"],
    )
    docs = []
    for hit in results[0]:
        text = hit.get("entity", {}).get("text")
        if text:
            docs.append(text)
    return docs


def _build_prompt(
    message: str,
    history: list[dict],
    docs: list[str],
) -> str:
    parts = [_SYSTEM_PROMPT]

    if docs:
        context = "\n\n--- Retrieved material ---\n\n" + "\n\n---\n\n".join(docs)
        parts.append(context)

    parts.append("\n\nCurrent conversation:\n")
    for m in history:
        role = "Student" if m["role"] == "user" else "Tutor"
        parts.append(f"{role}: {m['content']}\n")

    parts.append(f"Student: {message}\n")
    parts.append("Tutor:")

    return "".join(parts)


async def stream_chat_response(
    message: str,
    class_name: str,
    subject: str,
    history: list[dict],
) -> AsyncGenerator[str, None]:
    """
    Async generator that yields SSE-formatted strings.
    Events:
      data: {"type": "token", "content": "<text>"}\n\n
      data: {"type": "done"}\n\n
      data: {"type": "error", "content": "<message>"}\n\n
    """
    try:
        docs = await asyncio.to_thread(_retrieve_docs, message, class_name, subject)
        prompt = _build_prompt(message, history, docs)

        llm = _get_llm()
        async for chunk in llm.astream(prompt):
            text = _normalize_content(chunk.content)
            if text:
                yield f"data: {json.dumps({'type': 'token', 'content': text})}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    except Exception as exc:
        yield f"data: {json.dumps({'type': 'error', 'content': str(exc)})}\n\n"
