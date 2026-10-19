from pathlib import Path
import math

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
from app.utils.file_utils import ensure_supported_file, validate_source_relative_path
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
        source_relative_path: str | None = None,
    ) -> dict:
        original_name = upload_file.filename or "uploaded_file"
        file_type = ensure_supported_file(original_name)
        source_relative_path = validate_source_relative_path(source_relative_path)
        document_id = new_id("doc")
        safe_file_name = file_name.strip() if file_name and file_name.strip() else original_name
        stored_name = f"{document_id}.{file_type}"
        storage_path = settings.storage_dir / stored_name
        now = utc_now_iso()
        document = {
            "id": document_id,
            "file_name": safe_file_name,
            "original_name": original_name,
            "source_relative_path": source_relative_path,
            "file_type": file_type,
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

            json_store.update_item("documents.json", document_id, {"status": "chunking", "updated_at": utc_now_iso()})
            sheet_ids = {sheet["sheet_name"]: sheet["id"] for sheet in sheet_records}
            current_document = json_store.get_item("documents.json", document_id) or document
            chunks = self.chunker.chunk_workbook(cleaned, current_document, sheet_ids)

            json_store.update_item("documents.json", document_id, {"status": "embedding", "updated_at": utc_now_iso()})
            embeddings = self._create_embeddings(chunks)

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
            final_document = self._publish(document_id, sheet_records, chunks, embeddings, updates)
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
        with json_store._lock:
            document = self.get_document(document_id)
            if not document:
                return False
            collections = {name: [item for item in json_store.list_items(name)
                                  if item.get("document_id") != document_id]
                           for name in ("sheets.json", "chunks.json", "embeddings.json")}
            collections["documents.json"] = [item for item in json_store.list_items("documents.json")
                                             if item["id"] != document_id]
            storage_path = settings.storage_dir / Path(document.get("storage_path", "")).name
            original = storage_path.read_bytes() if storage_path.is_file() else None
            if original is not None:
                storage_path.unlink()
            try:
                json_store.write_batch(collections)
            except BaseException:
                if original is not None:
                    storage_path.write_bytes(original)
                raise
            return True

    def reindex_document(self, document_id: str) -> dict:
        """Build replacement artifacts first; keep old indexed data usable on failure."""
        with json_store._lock:
            document = self.get_document(document_id)
            if document is None:
                raise ValueError("文档不存在。")
            options = self.chunker._chunk_options(None, None)
            profile = embedding_service.profile()
        path = settings.storage_dir / Path(document["storage_path"]).name
        parsed = self._parse_file(path, document["file_type"], document_id, document["file_name"])
        cleaned = self.cleaner.clean_workbook(parsed)
        sheets = self._create_sheet_records(document_id, cleaned)
        chunks = self.chunker.chunk_workbook(cleaned, document, {item["sheet_name"]: item["id"] for item in sheets},
                                             chunk_size=options[0], overlap=options[1])
        embeddings = self._create_embeddings(chunks)
        updates = {"status": "indexed", "error_message": None, "sheet_count": len(sheets),
                   "chunk_count": len(chunks), "row_count": sum(item["row_count"] for item in sheets),
                   "column_count": max((item["column_count"] for item in sheets), default=0),
                   "parse_warnings": parsed.get("warnings", []), "updated_at": utc_now_iso()}
        with json_store._lock:
            if self.chunker._chunk_options(None, None) != options or embedding_service.profile() != profile:
                raise ValueError("索引配置已变更，请重新执行索引。")
            self._publish(document_id, sheets, chunks, embeddings, updates, expected=document)
        return {"document_id": document_id, "status": "indexed", "chunk_count": len(chunks), "sheet_count": len(sheets)}

    def _publish(self, document_id: str, sheets: list[dict], chunks: list[dict], embeddings: list[dict],
                 updates: dict, expected: dict | None = None) -> dict:
        with json_store._lock:
            current = self.get_document(document_id)
            if current is None or (expected is not None and current != expected):
                raise ValueError("文档已变更或删除，请重试。")
            if any(item.get("embedding_profile") != embedding_service.profile() for item in embeddings):
                raise ValueError("Embedding 配置已变更，请重新索引。")
            updated = {**current, **updates, "index_revision": new_id("rev")}
            collections = {}
            for name, replacements in (("sheets.json", sheets), ("chunks.json", chunks), ("embeddings.json", embeddings)):
                collections[name] = [item for item in json_store.list_items(name)
                                     if item.get("document_id") != document_id] + replacements
            collections["documents.json"] = [updated if item["id"] == document_id else item
                                             for item in json_store.list_items("documents.json")]
            json_store.write_batch(collections)
            return updated

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
        with json_store._lock:
            json_store.write_batch({name: [item for item in json_store.list_items(name)
                                           if item.get("document_id") != document_id]
                                   for name in ("sheets.json", "chunks.json", "embeddings.json")})
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
        if not chunks:
            return []
        profile = embedding_service.profile()
        vectors = embedding_service.embed_batch([chunk["content"] for chunk in chunks])
        if embedding_service.profile() != profile:
            raise ValueError("Embedding 配置已变更，请重新索引。")
        if len(vectors) != len(chunks):
            raise ValueError(
                f"Embedding response count mismatch: expected {len(chunks)}, received {len(vectors)}."
            )

        dimensions = {len(vector) for vector in vectors}
        if any(dimension == 0 for dimension in dimensions) or len(dimensions) > 1:
            raise ValueError("Embedding response contains empty or inconsistent vector dimensions.")
        if any(not all(math.isfinite(value) for value in vector) or not any(vector) for vector in vectors):
            raise ValueError("Embedding response contains non-finite or zero vectors.")

        model = profile["model"]
        now = utc_now_iso()
        return [
            {
                "chunk_id": chunk["id"],
                "document_id": chunk["document_id"],
                "sheet_id": chunk["sheet_id"],
                "embedding_model": model,
                "embedding_profile": profile,
                "vector": vector,
                "metadata": chunk.get("metadata", {}),
                "created_at": now,
            }
            for chunk, vector in zip(chunks, vectors)
        ]


document_pipeline = DocumentPipeline()
