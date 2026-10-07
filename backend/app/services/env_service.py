import os
from pathlib import Path

from app.core.config import settings


SECRET_KEYS = {"EMBEDDING_API_KEY", "LLM_API_KEY"}


class EnvService:
    def __init__(self) -> None:
        self.env_path = settings.backend_dir / ".env"

    def secret_values(self) -> dict[str, str]:
        values = self._read_env()
        return {
            "embedding_api_key": values.get("EMBEDDING_API_KEY", "") or settings.embedding_api_key,
            "llm_api_key": values.get("LLM_API_KEY", "") or settings.llm_api_key,
        }

    def configured_flags(self) -> dict[str, bool]:
        secrets = self.secret_values()
        return {
            "embedding_api_key_configured": bool(secrets["embedding_api_key"]),
            "llm_api_key_configured": bool(secrets["llm_api_key"]),
        }

    def update_secrets(self, secrets: dict) -> None:
        updates = {
            "EMBEDDING_API_KEY": secrets.get("embedding_api_key", "").strip(),
            "LLM_API_KEY": secrets.get("llm_api_key", "").strip(),
        }
        updates = {key: value for key, value in updates.items() if value}
        if not updates:
            return

        values = self._read_env()
        values.update(updates)
        self._write_env(values)
        os.environ.update(updates)
        if "EMBEDDING_API_KEY" in updates:
            settings.embedding_api_key = updates["EMBEDDING_API_KEY"]
        if "LLM_API_KEY" in updates:
            settings.llm_api_key = updates["LLM_API_KEY"]

    def _read_env(self) -> dict[str, str]:
        if not self.env_path.exists():
            return {}
        values = {}
        for line in self.env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            values[key.strip()] = value.strip()
        return values

    def _write_env(self, values: dict[str, str]) -> None:
        self.env_path.parent.mkdir(parents=True, exist_ok=True)
        lines = []
        if self.env_path.exists():
            seen = set()
            for line in self.env_path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    lines.append(line)
                    continue
                key, _ = stripped.split("=", 1)
                key = key.strip()
                if key in values:
                    lines.append(f"{key}={values[key]}")
                    seen.add(key)
                else:
                    lines.append(line)
            for key in values:
                if key not in seen:
                    lines.append(f"{key}={values[key]}")
        else:
            lines = [f"{key}={value}" for key, value in values.items()]
        self.env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


env_service = EnvService()
