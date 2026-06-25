import shutil
from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings
from app.services.csv_parser_service import CsvParserService
from app.services.embedding_service import embedding_service
from app.services.excel_parser_service import ExcelParserService
from app.services.json_store_service import json_store
from app.services.table_chunker_service import TableChunkerService
from app.services.table_cleaner_service import TableCleanerService
from app.utils.file_utils import ensure_supported_file
from app.utils.id_utils import new_id
from app.utils.time_utils import utc_now_iso


class DocumentPipeline:
    def __init__(self) -> None:
        self.excel_parser = ExcelParserService()
        self.csv_parser = CsvParserService()
        self.cleaner = TableCleanerService()
        self.chunker = TableChunkerService()

    async def upload_and_parse(
        self,
        upload_file: UploadFile,
        file_name: str | None,
        doc_type: str,
        department: str,
        permission_level: int,
    ) -> dict:
        original_name = upload_file.filename or "uploaded_file"
        file_type = ensure_supported_file(original_name)
        document_id = new_id("doc")
        safe_file_name = file_name.strip() if file_name and file_name.strip() else original_name
        stored_name = f"{document_id}.{file_type}"
        storage_path = settings.storage_dir / stored_name
        now = utc_now_iso()
        document = {
            "id": document_id,
            "file_name": safe_file_name,
            "original_name": original_name,
            "file_type": file_type,
            "doc_type": doc_type,
            "department": department,
            "permission_level": permission_level,
            "status": "uploaded",
            "storage_path": str(Path("storage/original") / stored_name),
            "sheet_count": 0,
            "chunk_count": 0,
            "row_count": 0,
            "column_count": 0,
            "error_message": None,
            "created_at": now,
            "updated_at": now,
        }
        json_store.add_item("documents.json", document)

        try:
            settings.storage_dir.mkdir(parents=True, exist_ok=True)
            with storage_path.open("wb") as output:
                shutil.copyfileobj(upload_file.file, output)

            json_store.update_item("documents.json", document_id, {"status": "parsing", "updated_at": utc_now_iso()})
            parsed = self._parse_file(storage_path, file_type, document_id, safe_file_name)
            cleaned = self.cleaner.clean_workbook(parsed)

            sheet_records = self._create_sheet_records(document_id, cleaned)
            existing_sheets = json_store.list_items("sheets.json")
            json_store.write_json("sheets.json", [*existing_sheets, *sheet_records])

            json_store.update_item("documents.json", document_id, {"status": "chunking", "updated_at": utc_now_iso()})
            sheet_ids = {sheet["sheet_name"]: sheet["id"] for sheet in sheet_records}
            current_document = json_store.get_item("documents.json", document_id) or document
            chunks = self.chunker.chunk_workbook(cleaned, current_document, sheet_ids)
            existing_chunks = json_store.list_items("chunks.json")
            json_store.write_json("chunks.json", [*existing_chunks, *chunks])

            json_store.update_item("documents.json", document_id, {"status": "embedding", "updated_at": utc_now_iso()})
            embeddings = self._create_embeddings(chunks)
            existing_embeddings = json_store.list_items("embeddings.json")
            json_store.write_json("embeddings.json", [*existing_embeddings, *embeddings])

            row_count = sum(sheet["row_count"] for sheet in sheet_records)
            column_count = max((sheet["column_count"] for sheet in sheet_records), default=0)
            updates = {
                "status": "indexed",
                "sheet_count": len(sheet_records),
                "chunk_count": len(chunks),
                "row_count": row_count,
                "column_count": column_count,
                "updated_at": utc_now_iso(),
            }
            final_document = json_store.update_item("documents.json", document_id, updates)
            return {
                "document_id": document_id,
                "status": final_document["status"] if final_document else "indexed",
                "sheet_count": len(sheet_records),
                "chunk_count": len(chunks),
            }
        except Exception as error:
            json_store.update_item(
                "documents.json",
                document_id,
                {"status": "failed", "error_message": str(error), "updated_at": utc_now_iso()},
            )
            raise

    def list_documents(
        self,
        keyword: str | None = None,
        status: str | None = None,
        department: str | None = None,
        doc_type: str | None = None,
    ) -> list[dict]:
        documents = json_store.list_items("documents.json")
        if keyword:
            documents = [item for item in documents if keyword.lower() in item.get("file_name", "").lower()]
        if status:
            documents = [item for item in documents if item.get("status") == status]
        if department:
            documents = [item for item in documents if item.get("department") == department]
        if doc_type:
            documents = [item for item in documents if item.get("doc_type") == doc_type]
        return sorted(documents, key=lambda item: item.get("created_at", ""), reverse=True)

    def get_document(self, document_id: str) -> dict | None:
        return json_store.get_item("documents.json", document_id)

    def list_sheets(self, document_id: str) -> list[dict]:
        return [sheet for sheet in json_store.list_items("sheets.json") if sheet.get("document_id") == document_id]

    def list_chunks(self, document_id: str, page: int, page_size: int) -> dict:
        chunks = [chunk for chunk in json_store.list_items("chunks.json") if chunk.get("document_id") == document_id]
        chunks.sort(key=lambda item: item.get("chunk_index", 0))
        start = max(page - 1, 0) * page_size
        end = start + page_size
        return {"items": chunks[start:end], "total": len(chunks), "page": page, "page_size": page_size}

    def delete_document(self, document_id: str) -> bool:
        document = self.get_document(document_id)
        if not document:
            return False
        for file_name in ("sheets.json", "chunks.json", "embeddings.json"):
            items = [item for item in json_store.list_items(file_name) if item.get("document_id") != document_id]
            json_store.write_json(file_name, items)
        json_store.delete_item("documents.json", document_id)
        storage_path = settings.backend_dir / document.get("storage_path", "")
        if storage_path.exists() and storage_path.is_file():
            storage_path.unlink()
        return True

    def _parse_file(self, path: Path, file_type: str, document_id: str, file_name: str) -> dict:
        if file_type == "csv":
            return self.csv_parser.parse(path, document_id, file_name)
        return self.excel_parser.parse(path, document_id, file_name)

    def _create_sheet_records(self, document_id: str, workbook: dict) -> list[dict]:
        records = []
        for sheet in workbook.get("sheets", []):
            records.append(
                {
                    "id": new_id("sheet"),
                    "document_id": document_id,
                    "sheet_name": sheet["sheet_name"],
                    "sheet_index": sheet["sheet_index"],
                    "header_row": sheet["header_row"],
                    "headers": sheet["headers"],
                    "row_count": len(sheet.get("rows", [])),
                    "column_count": len(sheet.get("headers", [])),
                    "created_at": utc_now_iso(),
                }
            )
        return records

    def _create_embeddings(self, chunks: list[dict]) -> list[dict]:
        vectors = embedding_service.embed_batch([chunk["content"] for chunk in chunks])
        model = embedding_service.embedding_model()
        now = utc_now_iso()
        return [
            {
                "chunk_id": chunk["id"],
                "document_id": chunk["document_id"],
                "sheet_id": chunk["sheet_id"],
                "embedding_model": model,
                "vector": vector,
                "metadata": chunk.get("metadata", {}),
                "created_at": now,
            }
            for chunk, vector in zip(chunks, vectors, strict=False)
        ]


document_pipeline = DocumentPipeline()
