from fastapi import APIRouter

from app.api.v1.routes import admin, admin_users, agent, auth, chat, health, ingest, upload, user

api_router = APIRouter()

api_router.include_router(health.router, tags=["Health"])
api_router.include_router(auth.router)
api_router.include_router(user.router)
api_router.include_router(admin.router)
api_router.include_router(admin_users.router)
api_router.include_router(upload.router)
api_router.include_router(ingest.router, tags=["Vector DB"])
api_router.include_router(agent.router, tags=["Agent"])
api_router.include_router(chat.router)
