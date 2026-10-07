from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover - the dependency is declared in requirements.txt
    fitz = None


@dataclass(frozen=True)
class _TextBlock:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    block_no: int


class PdfParserService:
    """Extract text-based PDFs in visual reading order for common page layouts."""

    def parse(self, file_path: str | Path, document_id: str, file_name: str) -> dict:
        if fitz is None:
            raise ValueError("PDF layout parsing requires the PyMuPDF dependency.")

        path = Path(file_path)
        try:
            pdf = fitz.open(str(path))
        except Exception as error:
            raise ValueError(f"Unable to read PDF file: {error}") from error

        warnings: list[str] = []
        sheets = []
        try:
            if pdf.needs_pass and not pdf.authenticate(""):
                raise ValueError("Encrypted PDFs are not supported. Please upload an unencrypted PDF.")

            for page_index in range(pdf.page_count):
                page_number = page_index + 1
                try:
                    page = pdf.load_page(page_index)
                    blocks = self._extract_blocks(page)
                except Exception as error:
                    raise ValueError(f"Unable to extract text from PDF page {page_number}: {error}") from error

                if not blocks:
                    warnings.append(
                        f"第{page_number}页没有可提取的文字，可能是扫描页或图片页，已跳过。"
                    )
                    continue

                ordered_blocks = self._order_blocks(blocks, float(page.rect.width))
                lines = [block.text for block in ordered_blocks if block.text]
                if not lines:
                    warnings.append(f"第{page_number}页没有可提取的文字，已跳过。")
                    continue

                sheets.append(
                    {
                        "sheet_name": f"第{page_number}页",
                        "sheet_index": page_number,
                        "header_row": 1,
                        "headers": ["文本"],
                        "content_type": "document",
                        "rows": [
                            {"row_number": row_number, "values": {"文本": line}}
                            for row_number, line in enumerate(lines, start=1)
                        ],
                    }
                )
        finally:
            pdf.close()

        if not sheets:
            raise ValueError(
                "PDF contains no extractable text. Scanned or image-only PDFs are not supported yet."
            )

        return {
            "document_id": document_id,
            "file_name": file_name,
            "content_type": "document",
            "warnings": warnings,
            "sheets": sheets,
        }

    def _extract_blocks(self, page: Any) -> list[_TextBlock]:
        blocks: list[_TextBlock] = []
        text_page = page.get_text("dict", sort=False)
        for raw_block in text_page.get("blocks", []):
            if raw_block.get("type") != 0:
                continue

            raw_lines = raw_block.get("lines", [])
            for raw_line in raw_lines:
                text = self._normalize_block_text(
                    "".join(span.get("text", "") for span in raw_line.get("spans", []))
                )
                bbox = raw_line.get("bbox", raw_block.get("bbox"))
                if not text or not bbox or len(bbox) < 4:
                    continue

                blocks.append(
                    _TextBlock(
                        text=text,
                        x0=float(bbox[0]),
                        y0=float(bbox[1]),
                        x1=float(bbox[2]),
                        y1=float(bbox[3]),
                        block_no=len(blocks),
                    )
                )
        return blocks

    def _order_blocks(self, blocks: list[_TextBlock], page_width: float) -> list[_TextBlock]:
        if len(blocks) < 4:
            return self._sort_blocks(blocks)

        split = self._find_column_split(blocks, page_width)
        if split is None:
            return self._sort_blocks(blocks)

        left = [block for block in blocks if block.x1 <= split]
        right = [block for block in blocks if block.x0 >= split]
        full_width = [block for block in blocks if block not in left and block not in right]
        first_column_y = min(block.y0 for block in [*left, *right])
        leading_full_width = [block for block in full_width if block.y0 <= first_column_y + 12]
        remaining_full_width = [block for block in full_width if block not in leading_full_width]

        return [
            *self._sort_blocks(leading_full_width),
            *self._sort_blocks(left),
            *self._sort_blocks(right),
            *self._sort_blocks(remaining_full_width),
        ]

    def _find_column_split(self, blocks: list[_TextBlock], page_width: float) -> float | None:
        if page_width <= 0:
            return None

        minimum_gap = max(18.0, page_width * 0.04)
        candidates = {page_width / 2}
        for left_block in blocks:
            for right_block in blocks:
                gap = right_block.x0 - left_block.x1
                if gap >= minimum_gap:
                    candidates.add((left_block.x1 + right_block.x0) / 2)

        best_split = None
        best_score = float("-inf")
        minimum_assigned = max(4, int(len(blocks) * 0.6))
        minimum_column_gap = max(8.0, page_width * 0.01)

        for split in candidates:
            left = [block for block in blocks if block.x1 <= split]
            right = [block for block in blocks if block.x0 >= split]
            assigned = len(left) + len(right)
            if len(left) < 2 or len(right) < 2 or assigned < minimum_assigned:
                continue

            left_end = max(block.x1 for block in left)
            right_start = min(block.x0 for block in right)
            column_gap = right_start - left_end
            if column_gap < minimum_column_gap:
                continue

            left_width = max(block.x1 for block in left) - min(block.x0 for block in left)
            right_width = max(block.x1 for block in right) - min(block.x0 for block in right)
            if left_width >= page_width * 0.58 or right_width >= page_width * 0.58:
                continue

            balance = min(len(left), len(right)) / max(len(left), len(right))
            assigned_ratio = assigned / len(blocks)
            score = column_gap * 2 + balance * page_width + assigned_ratio * page_width * 0.25
            if score > best_score:
                best_score = score
                best_split = split

        return best_split

    def _sort_blocks(self, blocks: list[_TextBlock]) -> list[_TextBlock]:
        return sorted(blocks, key=lambda block: (round(block.y0, 2), round(block.x0, 2), block.block_no))

    def _normalize_block_text(self, value: str) -> str:
        lines = [line.strip() for line in value.replace("\x00", "").splitlines() if line.strip()]
        return " ".join(lines)
