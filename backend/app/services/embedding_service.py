import hashlib
import math
import re

import httpx

from app.core.config import settings
from app.services.json_store_service import json_store


class EmbeddingService:
    def embed_text(self, text: str) -> list[float]:
        config = self._get_config()
        if config["mock"]:
            return self._mock_embedding(text, config["dim"])
        return self._api_embedding(text, config)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        config = self._get_config()
        if config["mock"]:
            return [self._mock_embedding(text, config["dim"]) for text in texts]
        return self._api_embedding_batch(texts, config)

    def embedding_model(self) -> str:
        return self._get_config()["model"]

    def _get_config(self) -> dict:
        settings_json = json_store.read_json("settings.json")
        embedding_settings = settings_json.get("embedding", {}) if isinstance(settings_json, dict) else {}
        return {
            "provider": embedding_settings.get("provider", settings.embedding_provider),
            "base_url": embedding_settings.get("base_url", settings.embedding_base_url).rstrip("/"),
            "api_key": settings.embedding_api_key,
            "model": embedding_settings.get("model", settings.embedding_model),
            "mock": bool(embedding_settings.get("mock", settings.embedding_mock)),
            "dim": settings.embedding_dim,
        }

    def _mock_embedding(self, text: str, dim: int) -> list[float]:
        vector = [0.0] * dim
        tokens = self._tokens(text)
        if not tokens:
            tokens = [text or "empty"]

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % dim
            vector[index] += 1.0

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [round(value / norm, 8) for value in vector]

    def _tokens(self, text: str) -> list[str]:
        normalized = text.lower()
        words = re.findall(r"[\w\u4e00-\u9fff]+", normalized)
        features = list(words)
        for word in words:
            if len(word) > 1:
                features.extend(word[index : index + 2] for index in range(len(word) - 1))
        return features

    def _api_embedding(self, text: str, config: dict) -> list[float]:
        embeddings = self._api_embedding_batch([text], config)
        return embeddings[0] if embeddings else []

    def _api_embedding_batch(self, texts: list[str], config: dict) -> list[list[float]]:
        if not config["api_key"]:
            raise ValueError("EMBEDDING_API_KEY is required when EMBEDDING_MOCK=false.")
        if config["provider"] != "openai-compatible":
            raise ValueError(f"Unsupported embedding provider: {config['provider']}")

        response = httpx.post(
            f"{config['base_url']}/embeddings",
            headers={"Authorization": f"Bearer {config['api_key']}"},
            json={"model": config["model"], "input": texts},
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        data = sorted(payload.get("data", []), key=lambda item: item.get("index", 0))
        return [item["embedding"] for item in data]


embedding_service = EmbeddingService()
