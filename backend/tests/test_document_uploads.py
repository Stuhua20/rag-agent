import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import settings
from app.routers.documents import router
from app.services.json_store_service import json_store
from app.services.document_pipeline import document_pipeline
from app.services.retrieval_service import retrieval_service
from app.services.table_analysis_service import table_analysis_service
from app.utils.file_utils import validate_source_relative_path


class DocumentUploadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.original_data_dir = json_store.data_dir
        self.original_storage_dir = settings.storage_dir
        self.addCleanup(self.restore_paths)
        json_store.data_dir = root / "data"
        settings.storage_dir = root / "storage"
        json_store.initialize()
        config = json_store.read_json("settings.json")
        config["embedding"]["mock"] = True
        json_store.write_json("settings.json", config)
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def restore_paths(self) -> None:
        json_store.data_dir = self.original_data_dir
        settings.storage_dir = self.original_storage_dir

    def upload_csv(self, **data: str):
        return self.client.post(
            "/api/documents/upload",
            files={"file": ("sales.csv", b"customer,amount\nAlice,10\n", "text/csv")},
            data=data,
        )

    def test_legacy_single_file_request_still_indexes(self) -> None:
        response = self.upload_csv(file_name="Sales report")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "indexed")
        self.assertGreater(response.json()["chunk_count"], 0)
        document = self.client.get(f"/api/documents/{response.json()['document_id']}").json()
        self.assertEqual(document["file_name"], "Sales report")
        self.assertNotIn("permission_level", document)
        for collection in ("chunks.json", "embeddings.json"):
            self.assertTrue(json_store.list_items(collection))
            self.assertTrue(all("permission_level" not in item["metadata"] for item in json_store.list_items(collection)))
        self.assertIsNone(document["source_relative_path"])

    def test_same_name_in_different_folders_keeps_separate_documents(self) -> None:
        for path in ("资料/华东/sales.csv", "资料/华南/sales.csv"):
            response = self.upload_csv(source_relative_path=path)
            self.assertEqual(response.status_code, 200, response.text)
        documents = self.client.get("/api/documents").json()
        self.assertEqual(len(documents), 2)
        self.assertEqual({item["source_relative_path"] for item in documents}, {"资料/华东/sales.csv", "资料/华南/sales.csv"})
        self.assertEqual(len({item["storage_path"] for item in documents}), 2)
        self.assertEqual(len(list(settings.storage_dir.iterdir())), 2)

    def test_invalid_source_paths_are_rejected_before_storage(self) -> None:
        for path in ("../sales.csv", "/tmp/sales.csv", "C:\\sales.csv", "资料/../sales.csv", "资料//sales.csv", "资料/./sales.csv", "资料/\x00sales.csv"):
            with self.subTest(path=path):
                response = self.upload_csv(source_relative_path=path)
                self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(json_store.list_items("documents.json"), [])
        self.assertEqual(list(settings.storage_dir.iterdir()), [])

    def test_windows_relative_path_is_normalized_as_metadata(self) -> None:
        self.assertEqual(validate_source_relative_path("资料\\销售\\sales.csv"), "资料/销售/sales.csv")

    def test_failed_document_does_not_prevent_next_upload(self) -> None:
        response = self.client.post(
            "/api/documents/upload",
            files={"file": ("broken.pdf", b"invalid PDF", "application/pdf")},
            data={"source_relative_path": "资料/broken.pdf"},
        )
        self.assertGreaterEqual(response.status_code, 400)
        response = self.upload_csv(source_relative_path="资料/sales.csv")
        self.assertEqual(response.status_code, 200, response.text)
        documents = json_store.list_items("documents.json")
        self.assertEqual([item["status"] for item in documents], ["failed", "indexed"])
        self.assertEqual(len(list(settings.storage_dir.iterdir())), 1)
        self.assertTrue(all(item["document_id"] == response.json()["document_id"] for item in json_store.list_items("chunks.json")))

    def test_obsolete_permission_form_field_is_ignored(self) -> None:
        response = self.upload_csv(permission_level="4")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("permission_level", json_store.list_items("documents.json")[0])

    def test_legacy_permission_metadata_no_longer_limits_search_or_analysis(self) -> None:
        response = self.upload_csv()
        self.assertEqual(response.status_code, 200, response.text)
        document_id = response.json()["document_id"]
        json_store.update_item("documents.json", document_id, {"permission_level": 3})
        for collection in ("chunks.json", "embeddings.json"):
            items = json_store.list_items(collection)
            for item in items:
                item["metadata"]["permission_level"] = 3
            json_store.write_json(collection, items)

        filters = {"permission_level": 1}
        sources = retrieval_service.search("Alice", filters=filters, full_scan=True)
        self.assertEqual({item["document_id"] for item in sources}, {document_id})
        analysis = table_analysis_service.analyze("amount总计", "aggregate", filters)
        self.assertIsNotNone(analysis)
        self.assertIn("10", analysis["answer"])

        filters["sheet_name"] = "missing-sheet"
        self.assertEqual(retrieval_service.search("Alice", filters=filters, full_scan=True), [])
        self.assertIsNone(table_analysis_service.analyze("amount总计", "aggregate", filters))

    def test_delete_cleans_original_and_indexes_without_affecting_other_documents(self) -> None:
        first = self.upload_csv(source_relative_path="资料/first.csv").json()["document_id"]
        second = self.upload_csv(source_relative_path="资料/second.csv").json()["document_id"]
        originals = {path.name for path in settings.storage_dir.iterdir()}
        self.assertEqual(len(originals), 2)

        response = self.client.delete(f"/api/documents/{first}")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["deleted"])
        self.assertEqual(self.client.get(f"/api/documents/{first}").status_code, 404)
        self.assertEqual({path.name for path in settings.storage_dir.iterdir()}, {f"{second}.csv"})
        for collection in ("sheets.json", "chunks.json", "embeddings.json"):
            items = json_store.list_items(collection)
            self.assertTrue(items)
            self.assertEqual({item["document_id"] for item in items}, {second})

        self.assertTrue(self.client.delete(f"/api/documents/{second}").json()["deleted"])
        self.assertEqual(json_store.list_items("documents.json"), [])
        self.assertEqual(list(settings.storage_dir.iterdir()), [])
        for collection in ("sheets.json", "chunks.json", "embeddings.json"):
            self.assertEqual(json_store.list_items(collection), [])

    def test_delete_filesystem_failure_keeps_record_and_indexes_for_retry(self) -> None:
        document_id = self.upload_csv().json()["document_id"]
        with patch.object(Path, "unlink", side_effect=PermissionError("file is locked")):
            with self.assertRaises(PermissionError):
                document_pipeline.delete_document(document_id)
        self.assertIsNotNone(document_pipeline.get_document(document_id))
        self.assertTrue(list(settings.storage_dir.iterdir()))
        for collection in ("sheets.json", "chunks.json", "embeddings.json"):
            self.assertTrue(json_store.list_items(collection))
        self.assertTrue(document_pipeline.delete_document(document_id))


if __name__ == "__main__":
    unittest.main()
