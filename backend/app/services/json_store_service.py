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

FILE_DIRECTORIES = {
    "documents.json": "knowledge",
    "sheets.json": "knowledge",
    "chunks.json": "knowledge",
    "embeddings.json": "knowledge",
    "conversations.json": "conversations",
    "messages.json": "conversations",
    "settings.json": "config",
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
        self._lock = threading.RLock()

    def initialize(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._migrate_legacy_files()
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
        path = self._path(file_name)
        path.parent.mkdir(parents=True, exist_ok=True)
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
        with self._lock:
            items = self.list_items(file_name)
            items.append(item)
            self.write_json(file_name, items)
            return item

    def add_run_message(self, message: dict) -> dict:
        """Check session existence and deduplicate a run's role under the same lock."""
        with self._lock:
            if self.get_item("conversations.json", message["conversation_id"]) is None:
                raise ValueError("会话已删除，不能继续写入消息。")
            items = self.list_items("messages.json")
            existing = next((item for item in items if item.get("run_id") == message["run_id"]
                             and item["role"] == message["role"]), None)
            if existing:
                return existing
            self.write_json("messages.json", [*items, message])
            return message

    def update_item(
        self, file_name: str, item_id: str, updates: dict, *, expected: dict | None = None,
    ) -> dict | None:
        with self._lock:
            items = self.list_items(file_name)
            for index, item in enumerate(items):
                if item.get("id") == item_id:
                    if expected and any(item.get(key) != value for key, value in expected.items()):
                        return None
                    items[index] = {**item, **updates}
                    self.write_json(file_name, items)
                    return items[index]
            return None

    def delete_item(self, file_name: str, item_id: str) -> bool:
        with self._lock:
            items = self.list_items(file_name)
            next_items = [item for item in items if item.get("id") != item_id]
            if len(next_items) == len(items):
                return False
            self.write_json(file_name, next_items)
            return True

    def _path(self, file_name: str) -> Path:
        directory = FILE_DIRECTORIES.get(file_name)
        return self.data_dir / directory / file_name if directory else self.data_dir / file_name

    def _migrate_legacy_files(self) -> None:
        # Check every destination before moving anything or initializing defaults.
        # Both copies may contain different data; never choose one silently.
        with self._lock:
            legacy_files = [
                (self.data_dir / file_name, self._path(file_name))
                for file_name in FILE_DIRECTORIES
                if (self.data_dir / file_name).exists()
            ]
            for source, target in legacy_files:
                if target.exists():
                    raise FileExistsError(
                        f"JSON migration conflict: both {source} and {target} exist. "
                        "Back up and resolve the duplicate files before starting the application."
                    )
            for source, target in legacy_files:
                target.parent.mkdir(parents=True, exist_ok=True)
                # A hard link preserves bytes and refuses to overwrite a target
                # created after the preflight check. Both paths are on the same disk.
                target.hardlink_to(source)
                source.unlink()


json_store = JsonStoreService()
