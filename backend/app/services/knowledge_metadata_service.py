from app.services.json_store_service import json_store


class KnowledgeMetadataService:
    def snapshot(self, question: str = "") -> dict:
        documents = [item for item in json_store.list_items("documents.json") if item.get("status") == "indexed"]
        document_ids = {item.get("id") for item in documents}
        sheets = [item for item in json_store.list_items("sheets.json") if item.get("document_id") in document_ids]
        chunks = [item for item in json_store.list_items("chunks.json") if item.get("document_id") in document_ids]

        file_names = self._unique(item.get("file_name") for item in documents)
        sheet_names = self._unique(item.get("sheet_name") for item in sheets)
        headers = self._unique(header for sheet in sheets for header in sheet.get("headers", []))
        headers = self._unique([*headers, *(column for chunk in chunks for column in chunk.get("columns", []))])

        return {
            "file_names": self._rank(question, file_names, 30),
            "sheet_names": self._rank(question, sheet_names, 40),
            "headers": self._rank(question, headers, 80),
            "sheet_headers": self._sheet_headers(question, sheets),
        }

    def _sheet_headers(self, question: str, sheets: list[dict]) -> list[dict]:
        ranked_sheets = self._rank(question, sheets, 20, key=lambda item: item.get("sheet_name", ""))
        return [
            {
                "sheet_name": sheet.get("sheet_name", ""),
                "headers": sheet.get("headers", [])[:30],
            }
            for sheet in ranked_sheets
        ]

    def _unique(self, values) -> list[str]:
        result = []
        seen = set()
        for value in values:
            text = str(value or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            result.append(text)
        return result

    def _rank(self, question: str, items: list, limit: int, key=None) -> list:
        scored = []
        for index, item in enumerate(items):
            text = key(item) if key else item
            scored.append((self._score(question, str(text or "")), index, item))
        scored.sort(key=lambda row: (row[0], -row[1]), reverse=True)
        return [item for score, _, item in scored[:limit] if score > 0] or items[:limit]

    def _score(self, question: str, text: str) -> int:
        question = question.lower()
        text = text.lower().strip()
        if not question or not text:
            return 0
        if text in question:
            return len(text) + 10
        return len(set(text) & set(question))


knowledge_metadata_service = KnowledgeMetadataService()
