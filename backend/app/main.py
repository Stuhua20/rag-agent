from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import chat, conversations, documents, health, settings as settings_router
from app.services.json_store_service import json_store


app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(documents.router)
app.include_router(settings_router.router)
app.include_router(conversations.router)
app.include_router(chat.router)


@app.on_event("startup")
def startup() -> None:
    json_store.initialize()

