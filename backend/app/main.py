from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.core.config import settings
from app.routers import chat, conversations, documents, health, prompts, settings as settings_router
from app.services.json_store_service import json_store
from app.services.chat_service import chat_service
from contextlib import asynccontextmanager

import os
from pathlib import Path

@asynccontextmanager
async def lifespan(app: FastAPI):
    json_store.initialize()
    if settings.chat_runtime == "langgraph":
        chat_service.agent_runtime()
    try:
        yield
    finally:
        chat_service.close()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(documents.router)
app.include_router(settings_router.router)
app.include_router(prompts.router)
app.include_router(conversations.router)
app.include_router(chat.router)

# Serve frontend static files
frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file_path = frontend_dist / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(frontend_dist / "index.html"))
