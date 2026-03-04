from fastapi import APIRouter

from app.api.v1.routes import agent, auth, chat, health, ingest, upload, user

api_router = APIRouter()

api_router.include_router(health.router, tags=["Health"])
api_router.include_router(auth.router)
api_router.include_router(user.router)
api_router.include_router(upload.router, tags=["Storage"])
api_router.include_router(ingest.router, tags=["Vector DB"])
api_router.include_router(agent.router, tags=["Agent"])
api_router.include_router(chat.router)
