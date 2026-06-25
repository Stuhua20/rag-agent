from fastapi import APIRouter

from app.services.env_service import env_service
from app.services.json_store_service import json_store


router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def get_settings() -> dict:
    settings_payload = json_store.read_json("settings.json")
    return {**settings_payload, "secrets": env_service.configured_flags()}


@router.put("")
def update_settings(payload: dict) -> dict:
    secrets = payload.pop("secrets", {})
    env_service.update_secrets(secrets)
    json_store.write_json("settings.json", payload)
    return {**payload, "secrets": env_service.configured_flags()}
