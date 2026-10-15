import re
from decimal import Decimal, InvalidOperation

from app.services.json_store_service import json_store


class TableAnalysisService:
    """对能够明确识别的表格统计请求执行全量、确定性计算。"""

    SUM_WORDS = ("总计", "合计", "总和", "累计", "汇总")
    AVERAGE_WORDS = ("平均", "均值")
    COUNT_WORDS = ("多少条", "多少笔", "多少行", "多少个", "多少家", "记录数")
    UNIQUE_COUNT_WORDS = ("多少个", "多少家", "多少种", "多少名", "多少位", "多少类")
    RANKING_WORDS = ("排名", "最高", "最多", "最大", "最低", "最少", "最小")
    TREND_WORDS = ("趋势", "变化", "同比", "环比")
    TEMPORAL_WORDS = (
        "年",
        "月",
        "日期",
        "时间",
        "季度",
        "周",
        "year",
        "month",
        "date",
        "time",
        "quarter",
        "week",
        "period",
    )
    NUMBER_PATTERN = re.compile(r"^[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?$")
    TOP_N_PATTERN = re.compile(r"前\s*(\d+)")
    ROW_PATTERN = re.compile(r"^行\s+(\d+)：(.+)$")

    def analyze(
        self,
        question: str,
        intent: str,
        filters: dict | None = None,
        query_variants: list[str] | None = None,
    ) -> dict | None:
        query_texts = self._unique_queries([question, *(query_variants or [])])
        operation = self._detect_operation(question, intent)
        if not operation:
            return None

        rows = self._load_rows(filters or {})
        if not rows:
            return None

        headers = self._unique(header for row in rows for header in row["values"])
        metric = self._find_header(query_texts, headers, rows)
        explicit_values = self._explicit_values(query_texts, rows)
        matched_rows = [row for row in rows if self._matches_explicit_values(row, explicit_values)]
        if not matched_rows:
            return None

        if operation == "count":
            values = [str(row["values"].get(metric, "")).strip() for row in matched_rows] if metric else []
            if metric and any(word in question for word in self.UNIQUE_COUNT_WORDS):
                count = len({value for value in values if value})
            else:
                count = sum(1 for row in matched_rows if metric is None or str(row["values"].get(metric, "")).strip())
            return {
                "answer": f"全量统计结果：共 {count} 条记录。",
                "chunk_ids": self._unique(row["chunk_id"] for row in matched_rows),
            }

        if not metric:
            return None

        numeric_rows = []
        for row in matched_rows:
            number = self._to_decimal(row["values"].get(metric))
            if number is not None:
                numeric_rows.append((row, number))
        if not numeric_rows:
            return None

        if operation == "sum":
            total = sum((number for _, number in numeric_rows), Decimal("0"))
            return {
                "answer": (
                    f"全量统计结果：{metric}合计为 {self._format_decimal(total)}，"
                    f"基于 {len(numeric_rows)} 条记录。"
                ),
                "chunk_ids": self._unique(row["chunk_id"] for row, _ in numeric_rows),
            }

        if operation == "average":
            total = sum((number for _, number in numeric_rows), Decimal("0"))
            average = total / Decimal(len(numeric_rows))
            return {
                "answer": (
                    f"全量统计结果：{metric}平均值为 {self._format_decimal(average)}，"
                    f"基于 {len(numeric_rows)} 条记录。"
                ),
                "chunk_ids": self._unique(row["chunk_id"] for row, _ in numeric_rows),
            }

        if operation == "ranking":
            return self._ranking(question, query_texts, metric, numeric_rows, headers)

        if operation == "trend":
            return self._trend(question, query_texts, metric, numeric_rows, headers)

        return None

    def _load_rows(self, filters: dict) -> list[dict]:
        allowed_ids = set(filters["document_ids"]) if "document_ids" in filters else None
        documents = {
            item["id"]: item
            for item in json_store.list_items("documents.json")
            if item.get("status") == "indexed" and item.get("id")
            and (allowed_ids is None or item["id"] in allowed_ids)
        }
        rows = []
        seen_rows = set()
        for chunk in json_store.list_items("chunks.json"):
            document = documents.get(chunk.get("document_id"))
            if not document or not self._matches_filters(chunk, filters):
                continue
            chunk_metadata = chunk.get("metadata", {}) or {}
            for row_number, values in self._parse_chunk_rows(chunk):
                row_key = (document["id"], chunk.get("sheet_id") or chunk.get("sheet_name"), row_number)
                if row_key in seen_rows:
                    continue
                seen_rows.add(row_key)
                rows.append(
                    {
                        "document_id": document["id"],
                        "chunk_id": chunk.get("id", ""),
                        "file_name": document.get("file_name", chunk_metadata.get("file_name", "")),
                        "sheet_name": chunk.get("sheet_name", ""),
                        "row_number": row_number,
                        "values": values,
                    }
                )
        return rows

    def _matches_filters(self, chunk: dict, filters: dict) -> bool:
        metadata = chunk.get("metadata", {}) or {}
        sheet_name = filters.get("sheet_name")
        if sheet_name and chunk.get("sheet_name", metadata.get("sheet_name")) != sheet_name:
            return False
        return True

    def _parse_chunk_rows(self, chunk: dict) -> list[tuple[int, dict[str, str]]]:
        rows = []
        for line in str(chunk.get("content", "")).splitlines():
            match = self.ROW_PATTERN.match(line.strip())
            if not match:
                continue
            row_number = int(match.group(1))
            values = {}
            for field in re.split(r"[；;]", match.group(2)):
                header, separator, value = field.partition("=")
                if separator and header.strip():
                    values[header.strip()] = value.strip()
            if values:
                rows.append((row_number, values))
        return rows

    def _detect_operation(self, question: str, intent: str) -> str | None:
        if any(word in question for word in self.AVERAGE_WORDS):
            return "average"
        if any(word in question for word in self.SUM_WORDS):
            return "sum"
        if any(word in question for word in self.RANKING_WORDS) or self.TOP_N_PATTERN.search(question):
            return "ranking"
        if any(word in question for word in self.TREND_WORDS):
            return "trend"
        if any(word in question for word in self.COUNT_WORDS):
            return "count"
        if intent in {"summary", "ranking", "trend"}:
            return None
        return None

    def _find_header(self, query_texts: list[str], headers: list[str], rows: list[dict]) -> str | None:
        matches = [header for header in headers if self._header_in_queries(header, query_texts)]
        if not matches:
            return None
        numeric_matches = [
            header
            for header in matches
            if any(self._to_decimal(row["values"].get(header)) is not None for row in rows)
        ]
        return max(numeric_matches or matches, key=len)

    def _find_group_header(
        self,
        query_texts: list[str],
        headers: list[str],
        metric: str,
        temporal: bool = False,
    ) -> str | None:
        candidates = [
            header
            for header in headers
            if header != metric and self._header_in_queries(header, query_texts)
        ]
        if temporal:
            temporal_candidates = [
                header for header in candidates if any(word in header for word in self.TEMPORAL_WORDS)
            ]
            candidates = temporal_candidates or candidates
        return max(candidates, key=len) if candidates else None

    def _ranking(
        self,
        question: str,
        query_texts: list[str],
        metric: str,
        numeric_rows: list[tuple[dict, Decimal]],
        headers: list[str],
    ) -> dict | None:
        group_header = self._find_group_header(query_texts, headers, metric)
        if not group_header:
            return None

        grouped: dict[str, Decimal] = {}
        grouped_chunks: dict[str, list[str]] = {}
        for row, number in numeric_rows:
            group = str(row["values"].get(group_header, "")).strip()
            if not group:
                continue
            grouped[group] = grouped.get(group, Decimal("0")) + number
            grouped_chunks.setdefault(group, []).append(row["chunk_id"])
        if not grouped:
            return None

        reverse = not any(word in question for word in ("最低", "最少", "最小"))
        ranked = sorted(grouped.items(), key=lambda item: item[1], reverse=reverse)
        top_match = self.TOP_N_PATTERN.search(question)
        limit = int(top_match.group(1)) if top_match else (1 if any(word in question for word in ("最高", "最低", "最多", "最少")) else 10)
        ranked = ranked[: max(1, min(limit, len(ranked)))]

        lines = ["全量统计结果：", "", f"| {group_header} | {metric} |", "|---|---:|"]
        for group, total in ranked:
            lines.append(f"| {group} | {self._format_decimal(total)} |")
        chunk_ids = self._unique(chunk_id for group, _ in ranked for chunk_id in grouped_chunks[group])
        return {"answer": "\n".join(lines), "chunk_ids": chunk_ids}

    def _trend(
        self,
        question: str,
        query_texts: list[str],
        metric: str,
        numeric_rows: list[tuple[dict, Decimal]],
        headers: list[str],
    ) -> dict | None:
        group_header = self._find_group_header(query_texts, headers, metric, temporal=True)
        if not group_header:
            return None

        grouped: dict[str, Decimal] = {}
        grouped_chunks: dict[str, list[str]] = {}
        for row, number in numeric_rows:
            period = str(row["values"].get(group_header, "")).strip()
            if not period:
                continue
            grouped[period] = grouped.get(period, Decimal("0")) + number
            grouped_chunks.setdefault(period, []).append(row["chunk_id"])
        if not grouped:
            return None

        lines = ["全量统计结果：", "", f"| {group_header} | {metric} |", "|---|---:|"]
        for period, total in grouped.items():
            lines.append(f"| {period} | {self._format_decimal(total)} |")
        chunk_ids = self._unique(chunk_id for period in grouped for chunk_id in grouped_chunks[period])
        return {"answer": "\n".join(lines), "chunk_ids": chunk_ids}

    def _explicit_values(self, query_texts: list[str], rows: list[dict]) -> list[str]:
        candidates = set()
        for query in query_texts:
            query_lower = query.casefold()
            for row in rows:
                for value in row["values"].values():
                    text = str(value).strip()
                    if len(text) >= 2 and text.casefold() in query_lower:
                        candidates.add(text)
                for value in (row["file_name"], row["sheet_name"]):
                    text = str(value).strip()
                    if len(text) >= 2 and text.casefold() in query_lower:
                        candidates.add(text)

        ordered = sorted(candidates, key=len, reverse=True)
        return [candidate for candidate in ordered if not any(candidate != other and candidate.casefold() in other.casefold() for other in ordered)]

    def _matches_explicit_values(self, row: dict, explicit_values: list[str]) -> bool:
        searchable = [str(value).casefold() for value in row["values"].values()]
        searchable.extend((str(row["file_name"]).casefold(), str(row["sheet_name"]).casefold()))
        return all(any(value.casefold() == item for item in searchable) for value in explicit_values)

    def _header_in_question(self, header: str, question: str) -> bool:
        question_lower = question.casefold()
        header_lower = header.casefold()
        if header_lower in question_lower:
            return True
        base_header = re.split(r"[（(]", header, maxsplit=1)[0].strip().casefold()
        return bool(base_header) and base_header in question_lower

    def _header_in_queries(self, header: str, query_texts: list[str]) -> bool:
        return any(self._header_in_question(header, query) for query in query_texts)

    def _unique_queries(self, queries: list[str]) -> list[str]:
        result = []
        seen = set()
        for query in queries:
            text = str(query).strip()
            key = text.casefold()
            if not text or key in seen:
                continue
            seen.add(key)
            result.append(text)
        return result

    def _to_decimal(self, value) -> Decimal | None:
        text = str(value or "").strip().replace("，", ",").replace(" ", "")
        if not self.NUMBER_PATTERN.fullmatch(text):
            return None
        try:
            return Decimal(text.replace(",", ""))
        except InvalidOperation:
            return None

    def _format_decimal(self, value: Decimal) -> str:
        text = format(value, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text or "0"

    def _unique(self, values) -> list:
        result = []
        seen = set()
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            result.append(value)
        return result


table_analysis_service = TableAnalysisService()
