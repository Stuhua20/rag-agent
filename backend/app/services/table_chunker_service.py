from app.core.config import settings
from app.utils.id_utils import new_id
from app.utils.time_utils import utc_now_iso


class TableChunkerService:
    def chunk_workbook(
        self,
        workbook: dict,
        document: dict,
        sheet_ids: dict[str, str],
        chunk_size: int | None = None,
    ) -> list[dict]:
        max_size = chunk_size or settings.default_chunk_size
        chunks = []
        chunk_index = 1

        for sheet in workbook.get("sheets", []):
            current_lines = []
            row_start = None
            row_end = None
            sheet_name = sheet["sheet_name"]
            columns = sheet.get("headers", [])

            for row in sheet.get("rows", []):
                row_text = self._row_to_text(row)
                if not row_text:
                    continue
                candidate_size = len("\n".join(current_lines + [row_text]))
                if current_lines and candidate_size > max_size:
                    chunks.append(
                        self._make_chunk(document, sheet_ids[sheet_name], sheet, chunk_index, current_lines, row_start, row_end)
                    )
                    chunk_index += 1
                    current_lines = []
                    row_start = None

                if row_start is None:
                    row_start = row["row_number"]
                row_end = row["row_number"]
                current_lines.append(row_text)

            if current_lines:
                chunks.append(
                    self._make_chunk(document, sheet_ids[sheet_name], sheet, chunk_index, current_lines, row_start, row_end)
                )
                chunk_index += 1

        return chunks

    def _row_to_text(self, row: dict) -> str:
        values = [
            f"{column}={value}"
            for column, value in row.get("values", {}).items()
            if str(value).strip() != ""
        ]
        if not values:
            return ""
        return f"行 {row['row_number']}：" + "；".join(values)

    def _make_chunk(
        self,
        document: dict,
        sheet_id: str,
        sheet: dict,
        chunk_index: int,
        lines: list[str],
        row_start: int,
        row_end: int,
    ) -> dict:
        file_name = document["file_name"]
        sheet_name = sheet["sheet_name"]
        content = "\n".join([f"文件：{file_name}", f"Sheet：{sheet_name}", *lines])
        return {
            "id": new_id("chunk"),
            "document_id": document["id"],
            "sheet_id": sheet_id,
            "chunk_index": chunk_index,
            "chunk_type": "table_rows",
            "sheet_name": sheet_name,
            "row_start": row_start,
            "row_end": row_end,
            "columns": sheet.get("headers", []),
            "title": f"{sheet_name} 第{row_start}-{row_end}行",
            "content": content,
            "token_count": len(content),
            "metadata": {
                "file_name": file_name,
                "doc_type": document.get("doc_type"),
                "department": document.get("department"),
                "permission_level": document.get("permission_level"),
                "sheet_name": sheet_name,
                "row_start": row_start,
                "row_end": row_end,
            },
            "created_at": utc_now_iso(),
        }

