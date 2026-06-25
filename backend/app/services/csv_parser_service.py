import csv
from pathlib import Path


class CsvParserService:
    def parse(self, file_path: str | Path, document_id: str, file_name: str) -> dict:
        path = Path(file_path)
        rows = self._read_rows(path)
        if not rows:
            raise ValueError("CSV file is empty.")

        header_index = self._find_header_row(rows)
        if header_index is None:
            raise ValueError("CSV file has no header row.")

        headers = [cell.strip() or f"列{index + 1}" for index, cell in enumerate(rows[header_index])]
        parsed_rows = []
        for row_number, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
            values = {
                header: row[index] if index < len(row) else ""
                for index, header in enumerate(headers)
            }
            if any(str(value).strip() for value in values.values()):
                parsed_rows.append({"row_number": row_number, "values": values})

        return {
            "document_id": document_id,
            "file_name": file_name,
            "sheets": [
                {
                    "sheet_name": Path(file_name).stem,
                    "sheet_index": 1,
                    "header_row": header_index + 1,
                    "headers": headers,
                    "rows": parsed_rows,
                }
            ],
        }

    def _read_rows(self, path: Path) -> list[list[str]]:
        last_error = None
        for encoding in ("utf-8-sig", "utf-8", "gbk"):
            try:
                with path.open("r", encoding=encoding, newline="") as file:
                    return list(csv.reader(file))
            except UnicodeDecodeError as error:
                last_error = error
        raise ValueError(f"Unable to decode CSV file: {last_error}")

    def _find_header_row(self, rows: list[list[str]]) -> int | None:
        for index, row in enumerate(rows):
            if any(cell.strip() for cell in row):
                return index
        return None
