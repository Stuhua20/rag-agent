from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings
from app.services.csv_parser_service import CsvParserService
from app.services.embedding_service import embedding_service
from app.services.excel_parser_service import ExcelParserService
from app.services.json_store_service import json_store
from app.services.pdf_parser_service import PdfParserService
from app.services.table_chunker_service import TableChunkerService
from app.services.table_cleaner_service import TableCleanerService
from app.services.word_parser_service import WordParserService
from app.utils.file_utils import ensure_supported_file
from app.utils.id_utils import new_id
from app.utils.time_utils import utc_now_iso


class DocumentPipeline:
    def __init__(self) -> None:
        self.excel_parser = ExcelParserService()
        self.csv_parser = CsvParserService()
        self.pdf_parser = PdfParserService()
        self.word_parser = WordParserService()
        self.cleaner = TableCleanerService()
        self.chunker = TableChunkerService()

    async def upload_and_parse(
        self,
        upload_file: UploadFile,
        file_name: str | None,
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
            "permission_level": permission_level,
            "status": "uploaded",
            "storage_path": str(Path("storage/original") / stored_name),
            "sheet_count": 0,
            "chunk_count": 0,
            "row_count": 0,
            "column_count": 0,
            "parse_warnings": [],
            "error_message": None,
            "created_at": now,
            "updated_at": now,
        }
        json_store.add_item("documents.json", document)

        try:
            self._copy_upload(upload_file, storage_path)

            json_store.update_item("documents.json", document_id, {"status": "parsing", "updated_at": utc_now_iso()})
            parsed = self._parse_file(storage_path, file_type, document_id, safe_file_name)
            cleaned = self.cleaner.clean_workbook(parsed)
            parse_warnings = parsed.get("warnings", [])

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
                "parse_warnings": parse_warnings,
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
            error_message = str(error)
            try:
                self._cleanup_document_artifacts(document_id, storage_path)
            except Exception as cleanup_error:
                error_message = f"{error_message}; cleanup failed: {cleanup_error}"
            json_store.update_item(
                "documents.json",
                document_id,
                {"status": "failed", "error_message": error_message, "updated_at": utc_now_iso()},
            )
            raise

    def list_documents(
        self,
        keyword: str | None = None,
        status: str | None = None,
    ) -> list[dict]:
        documents = json_store.list_items("documents.json")
        if keyword:
            documents = [item for item in documents if keyword.lower() in item.get("file_name", "").lower()]
        if status:
            documents = [item for item in documents if item.get("status") == status]
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
        if file_type == "pdf":
            return self.pdf_parser.parse(path, document_id, file_name)
        if file_type == "docx":
            return self.word_parser.parse(path, document_id, file_name)
        return self.excel_parser.parse(path, document_id, file_name)

    def _copy_upload(self, upload_file: UploadFile, storage_path: Path) -> None:
        max_bytes = settings.max_upload_mb * 1024 * 1024
        if max_bytes <= 0:
            raise ValueError("MAX_UPLOAD_MB must be greater than zero.")

        settings.storage_dir.mkdir(parents=True, exist_ok=True)
        bytes_written = 0
        with storage_path.open("wb") as output:
            while True:
                chunk = upload_file.file.read(1024 * 1024)
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > max_bytes:
                    raise ValueError(f"Uploaded file exceeds the {settings.max_upload_mb} MB limit.")
                output.write(chunk)

    def _cleanup_document_artifacts(self, document_id: str, storage_path: Path) -> None:
        for file_name in ("sheets.json", "chunks.json", "embeddings.json"):
            items = [
                item
                for item in json_store.list_items(file_name)
                if item.get("document_id") != document_id
            ]
            json_store.write_json(file_name, items)
        storage_path.unlink(missing_ok=True)

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
                    "content_type": sheet.get("content_type", workbook.get("content_type", "table")),
                    "row_count": len(sheet.get("rows", [])),
                    "column_count": len(sheet.get("headers", [])),
                    "created_at": utc_now_iso(),
                }
            )
        return records

    def _create_embeddings(self, chunks: list[dict]) -> list[dict]:
        vectors = embedding_service.embed_batch([chunk["content"] for chunk in chunks])
        if len(vectors) != len(chunks):
            raise ValueError(
                f"Embedding response count mismatch: expected {len(chunks)}, received {len(vectors)}."
            )

        dimensions = {len(vector) for vector in vectors}
        if any(dimension == 0 for dimension in dimensions) or len(dimensions) > 1:
            raise ValueError("Embedding response contains empty or inconsistent vector dimensions.")

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
            for chunk, vector in zip(chunks, vectors)
        ]


document_pipeline = DocumentPipeline()
