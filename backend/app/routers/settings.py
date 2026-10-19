from copy import deepcopy

from fastapi import APIRouter, Response

from app.schemas.settings import SettingsPayload
from app.services.env_service import env_service
from app.services.json_store_service import DEFAULT_SETTINGS, json_store


router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def get_settings() -> dict:
    settings_payload = json_store.read_json("settings.json")
    return {**_merge_defaults(settings_payload), "secrets": env_service.configured_flags()}


@router.get("/secrets")
def get_secret_settings(response: Response) -> dict[str, str]:
    response.headers["Cache-Control"] = "no-store"
    return env_service.secret_values()


@router.put("")
def update_settings(payload: SettingsPayload) -> dict:
    updates = payload.model_dump(exclude_none=True, exclude_unset=True)
    secrets = updates.pop("secrets", {})
    env_service.update_secrets(secrets)
    with json_store._lock:
        current = _merge_defaults(json_store.read_json("settings.json"))
        merged = _deep_merge(current, updates)
        json_store.write_json("settings.json", merged)
    return {**_merge_defaults(merged), "secrets": env_service.configured_flags()}


def _merge_defaults(payload: dict) -> dict:
    merged = deepcopy(DEFAULT_SETTINGS)
    if not isinstance(payload, dict):
        return merged
    for key, value in DEFAULT_SETTINGS.items():
        if key not in payload:
            continue
        overrides = payload[key]
        if isinstance(value, dict) and isinstance(overrides, dict):
            merged[key] = {**value, **overrides}
        else:
            merged[key] = overrides
    return merged


def _deep_merge(base: dict, updates: dict) -> dict:
    merged = deepcopy(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged
