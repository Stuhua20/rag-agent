from datetime import date, datetime
from decimal import Decimal
from typing import Any


class TableCleanerService:
    def clean_workbook(self, workbook: dict) -> dict:
        cleaned_sheets = []
        for sheet in workbook.get("sheets", []):
            headers = [self.clean_cell(header) or f"列{index + 1}" for index, header in enumerate(sheet["headers"])]
            rows = []
            for row in sheet.get("rows", []):
                values = {}
                for header, value in row.get("values", {}).items():
                    clean_header = self.clean_cell(header)
                    if clean_header:
                        values[clean_header] = self.clean_cell(value)
                if any(value != "" for value in values.values()):
                    rows.append({"row_number": row["row_number"], "values": values})
            cleaned_sheets.append({**sheet, "headers": headers, "rows": rows})
        return {**workbook, "sheets": cleaned_sheets}

    def clean_cell(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, datetime):
            return value.isoformat(sep=" ", timespec="seconds")
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, Decimal):
            return str(value)
        text = str(value).replace("\r\n", "\n").replace("\r", "\n").strip()
        return "\n".join(line.strip() for line in text.split("\n") if line.strip())

