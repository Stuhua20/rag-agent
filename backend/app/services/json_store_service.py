import json
import os
import threading
from pathlib import Path
from typing import Any

from app.core.config import settings


LIST_FILES = {
    "documents.json",
    "sheets.json",
    "chunks.json",
    "embeddings.json",
    "conversations.json",
    "messages.json",
}

DEFAULT_SETTINGS = {
    "embedding": {
        "provider": "openai-compatible",
        "base_url": "https://api.example.com/v1",
        "model": "text-embedding-3-small",
        "mock": True,
        "normalize": True,
    },
    "llm": {
        "provider": "openai-compatible",
        "base_url": "https://api.example.com/v1",
        "model": "gpt-4o-mini",
        "mock": True,
    },
    "retrieval": {
        "top_k": settings.default_top_k,
        "chunk_size": settings.default_chunk_size,
        "overlap": settings.default_overlap,
        "score_threshold": settings.default_score_threshold,
        "search_mode": "hybrid",
        "max_chunks_per_doc": 3,
        "full_scan_max_chunks": settings.full_scan_max_chunks,
    },
    "conversation": {
        "context_window": 8,
    },
}


class JsonStoreService:
    def __init__(self) -> None:
        self.data_dir = settings.data_dir
        self._lock = threading.Lock()

    def initialize(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        settings.storage_dir.mkdir(parents=True, exist_ok=True)
        for file_name in LIST_FILES:
            path = self._path(file_name)
            if not path.exists():
                self.write_json(file_name, [])
        settings_path = self._path("settings.json")
        if not settings_path.exists():
            self.write_json("settings.json", DEFAULT_SETTINGS)

    def read_json(self, file_name: str) -> Any:
        path = self._path(file_name)
        if not path.exists():
            return [] if file_name in LIST_FILES else {}
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def write_json(self, file_name: str, data: Any) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        path = self._path(file_name)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        with self._lock:
            with temp_path.open("w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, indent=2)
                file.write("\n")
            os.replace(temp_path, path)

    def list_items(self, file_name: str) -> list[dict]:
        data = self.read_json(file_name)
        return data if isinstance(data, list) else []

    def get_item(self, file_name: str, item_id: str) -> dict | None:
        return next((item for item in self.list_items(file_name) if item.get("id") == item_id), None)

    def add_item(self, file_name: str, item: dict) -> dict:
        items = self.list_items(file_name)
        items.append(item)
        self.write_json(file_name, items)
        return item

    def update_item(self, file_name: str, item_id: str, updates: dict) -> dict | None:
        items = self.list_items(file_name)
        for index, item in enumerate(items):
            if item.get("id") == item_id:
                items[index] = {**item, **updates}
                self.write_json(file_name, items)
                return items[index]
        return None

    def delete_item(self, file_name: str, item_id: str) -> bool:
        items = self.list_items(file_name)
        next_items = [item for item in items if item.get("id") != item_id]
        if len(next_items) == len(items):
            return False
        self.write_json(file_name, next_items)
        return True

    def _path(self, file_name: str) -> Path:
        return self.data_dir / file_name


json_store = JsonStoreService()
