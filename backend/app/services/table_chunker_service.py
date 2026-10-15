from app.core.config import settings
from app.services.json_store_service import json_store
from app.utils.id_utils import new_id
from app.utils.time_utils import utc_now_iso


class TableChunkerService:
    def chunk_workbook(
        self,
        workbook: dict,
        document: dict,
        sheet_ids: dict[str, str],
        chunk_size: int | None = None,
        overlap: int | None = None,
    ) -> list[dict]:
        max_size, overlap_size = self._chunk_options(chunk_size, overlap)
        chunks = []
        chunk_index = 1

        for sheet in workbook.get("sheets", []):
            content_type = sheet.get("content_type", workbook.get("content_type", "table"))
            current_rows = []
            sheet_name = sheet["sheet_name"]

            for row in sheet.get("rows", []):
                row_text = self._row_to_text(row, content_type)
                if not row_text:
                    continue

                current_text = [entry["text"] for entry in current_rows]
                candidate_size = len("\n".join(current_text + [row_text]))
                if current_rows and candidate_size > max_size:
                    chunks.append(self._make_chunk(
                        document,
                        sheet_ids[sheet_name],
                        sheet,
                        chunk_index,
                        current_rows,
                        content_type,
                    ))
                    chunk_index += 1
                    current_rows = self._tail_rows(current_rows, overlap_size)

                current_rows.append({"row_number": row["row_number"], "text": row_text})

            if current_rows:
                chunks.append(self._make_chunk(
                    document,
                    sheet_ids[sheet_name],
                    sheet,
                    chunk_index,
                    current_rows,
                    content_type,
                ))
                chunk_index += 1

        return chunks

    def _chunk_options(self, chunk_size: int | None, overlap: int | None) -> tuple[int, int]:
        retrieval_settings = json_store.read_json("settings.json")
        retrieval = retrieval_settings.get("retrieval", {}) if isinstance(retrieval_settings, dict) else {}

        configured_chunk_size = chunk_size if chunk_size is not None else retrieval.get("chunk_size")
        configured_overlap = overlap if overlap is not None else retrieval.get("overlap")

        max_size = self._as_int(configured_chunk_size, settings.default_chunk_size, minimum=1)
        overlap_size = self._as_int(configured_overlap, settings.default_overlap, minimum=0)
        return max_size, min(overlap_size, max_size - 1)

    def _tail_rows(self, rows: list[dict], overlap_size: int) -> list[dict]:
        if overlap_size <= 0:
            return []

        selected = []
        total_size = 0
        for row in reversed(rows):
            row_size = len(row["text"]) + (1 if selected else 0)
            if selected and total_size + row_size > overlap_size:
                break
            selected.insert(0, row)
            total_size += row_size
        return selected

    def _as_int(self, value, default: int, minimum: int) -> int:
        try:
            return max(int(value), minimum)
        except (TypeError, ValueError):
            return default

    def _row_to_text(self, row: dict, content_type: str) -> str:
        values = [
            str(value).strip() if content_type == "document" else f"{column}={value}"
            for column, value in row.get("values", {}).items()
            if str(value).strip() != ""
        ]
        if not values:
            return ""
        if content_type == "document":
            return "；".join(values)
        return f"行 {row['row_number']}：" + "；".join(values)

    def _make_chunk(
        self,
        document: dict,
        sheet_id: str,
        sheet: dict,
        chunk_index: int,
        rows: list[dict],
        content_type: str,
    ) -> dict:
        file_name = document["file_name"]
        sheet_name = sheet["sheet_name"]
        lines = [row["text"] for row in rows]
        row_start = rows[0]["row_number"]
        row_end = rows[-1]["row_number"]
        is_document = content_type == "document"
        content = "\n".join([f"文件：{file_name}", f"Sheet：{sheet_name}", *lines])
        return {
            "id": new_id("chunk"),
            "document_id": document["id"],
            "sheet_id": sheet_id,
            "chunk_index": chunk_index,
            "chunk_type": "document_blocks" if is_document else "table_rows",
            "sheet_name": sheet_name,
            "row_start": row_start,
            "row_end": row_end,
            "columns": sheet.get("headers", []),
            "title": (
                f"{sheet_name} 第{row_start}-{row_end}个内容块"
                if is_document
                else f"{sheet_name} 第{row_start}-{row_end}行"
            ),
            "content": content,
            "token_count": len(content),
            "metadata": {
                "file_name": file_name,
                "sheet_name": sheet_name,
                "row_start": row_start,
                "row_end": row_end,
                "content_type": content_type,
            },
            "created_at": utc_now_iso(),
        }
