# Notes: Document parser implementation

## Current pipeline

- `backend/app/services/document_pipeline.py` dispatches by extension, then runs every parser output through `TableCleanerService`, `TableChunkerService`, and embedding generation.
- `pdf_parser_service.py` currently uses `pypdf.PdfReader.page.extract_text()`, splits on newlines, and exposes each page as a sheet.
- `word_parser_service.py` currently iterates body paragraphs and tables with `python-docx`, exposing one `正文` sheet.
- `table_chunker_service.py` converts every parsed row into a row-style chunk. This is compatible with the current storage/retrieval contract but is not fully semantic for prose.

## Constraints

- The working tree already contains broad user changes. Only parser-related files and focused tests/docs should be touched.
- `reindex` is not implemented, so previously indexed documents will not be repaired automatically by a parser change.
- The first milestone must remain text-based and must not add OCR or broad format conversion.

## Implementation notes

- PyMuPDF 1.28.2 is installed in the project virtual environment and declared in `backend/requirements.txt`; the parser uses `pymupdf` and extracts line-level text blocks from `page.get_text("dict")` so adjacent columns are not merged into one block.
- The PDF adapter emits the existing `sheets`/`rows` shape, detects common two-column splits, preserves page sheets, and records skipped textless pages as `warnings`.
- Standard DOCX section columns are generally stored in document reading order; improve diagnostics and preserve paragraphs/tables without pretending to support floating text boxes.
- If an input contains no extractable PDF text, return a clear unsupported/scanned-PDF error rather than silently indexing empty content.
- Document chunks now use `document_blocks` and prose text without the table-style `行 N：` prefix; table chunks retain their existing format.
- Parser warnings are stored on `documents.json` and displayed in the document preview.
