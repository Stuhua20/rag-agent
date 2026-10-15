import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.config import settings
from app.services.json_store_service import DEFAULT_SETTINGS, FILE_DIRECTORIES, JsonStoreService


class JsonStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.store = JsonStoreService()
        self.store.data_dir = self.root / "custom-data"
        storage_patch = patch.object(settings, "storage_dir", self.root / "original")
        storage_patch.start()
        self.addCleanup(storage_patch.stop)

    def test_empty_directory_initializes_all_categories(self) -> None:
        self.store.initialize()
        for file_name, directory in FILE_DIRECTORIES.items():
            path = self.store.data_dir / directory / file_name
            self.assertTrue(path.is_file())
            self.assertFalse((self.store.data_dir / file_name).exists())
            expected = DEFAULT_SETTINGS if file_name == "settings.json" else []
            self.assertEqual(self.store.read_json(file_name), expected)

    def test_migration_preserves_every_file_byte_and_is_repeatable(self) -> None:
        self.store.data_dir.mkdir()
        original = {}
        for file_name in FILE_DIRECTORIES:
            payload = (
                {"embedding": {"mock": False, "model": "existing-model"}}
                if file_name == "settings.json"
                else [{"id": "existing", "content": "已有资料", "vector": [0.123456789, -0.5]}]
            )
            original[file_name] = json.dumps(payload, ensure_ascii=False, indent=4).encode() + b"\n"
            (self.store.data_dir / file_name).write_bytes(original[file_name])

        self.store.initialize()
        self.store.initialize()

        for file_name, directory in FILE_DIRECTORIES.items():
            self.assertEqual((self.store.data_dir / directory / file_name).read_bytes(), original[file_name])
            self.assertFalse((self.store.data_dir / file_name).exists())
            self.assertEqual(self.store.read_json(file_name), json.loads(original[file_name]))

    def test_conflict_stops_before_moving_files_or_creating_defaults(self) -> None:
        knowledge = self.store.data_dir / "knowledge"
        knowledge.mkdir(parents=True)
        legacy_document = self.store.data_dir / "documents.json"
        legacy_document.write_text('[{"id":"old-doc"}]')
        legacy_vectors = self.store.data_dir / "embeddings.json"
        legacy_vectors.write_text('[{"vector":[1.0]}]')
        target = knowledge / "embeddings.json"
        target.write_text('[{"vector":[2.0]}]')

        with self.assertRaisesRegex(FileExistsError, "JSON migration conflict"):
            self.store.initialize()

        self.assertTrue(legacy_document.is_file())
        self.assertFalse((knowledge / "documents.json").exists())
        self.assertEqual(legacy_vectors.read_text(), '[{"vector":[1.0]}]')
        self.assertEqual(target.read_text(), '[{"vector":[2.0]}]')
        self.assertFalse((self.store.data_dir / "config" / "settings.json").exists())

    def test_partially_migrated_directory_keeps_existing_data(self) -> None:
        knowledge = self.store.data_dir / "knowledge"
        knowledge.mkdir(parents=True)
        (knowledge / "documents.json").write_text('[{"id":"already-moved"}]')
        (self.store.data_dir / "messages.json").write_text('[{"id":"old-message"}]')
        self.store.initialize()
        self.assertEqual(self.store.get_item("documents.json", "already-moved"), {"id": "already-moved"})
        self.assertEqual(self.store.get_item("messages.json", "old-message"), {"id": "old-message"})
        self.assertFalse((self.store.data_dir / "messages.json").exists())

    def test_write_creates_parent_without_initialize_and_preserves_crud(self) -> None:
        self.store.add_item("messages.json", {"id": "message", "content": "hello"})
        self.store.update_item("messages.json", "message", {"content": "updated"})
        self.assertEqual(self.store.get_item("messages.json", "message")["content"], "updated")
        path = self.store.data_dir / "conversations" / "messages.json"
        self.assertTrue(path.is_file())
        self.assertFalse(path.with_suffix(".json.tmp").exists())
        self.assertTrue(self.store.delete_item("messages.json", "message"))
        self.assertEqual(self.store.list_items("messages.json"), [])


if __name__ == "__main__":
    unittest.main()
