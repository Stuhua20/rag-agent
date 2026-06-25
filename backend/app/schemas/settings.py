from typing import Any

from pydantic import BaseModel


class SettingsPayload(BaseModel):
    settings: dict[str, Any]

