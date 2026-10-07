# Document parser change deliverable

## Implemented

- Replaced line-only PDF extraction with PyMuPDF 1.28.2 text-block extraction.
- Added common two-column detection and left-column-before-right-column ordering.
- Added skipped-page warnings for textless/image-only PDF pages and a clear error for fully scanned PDFs.
- Added DOCX column-count detection and warnings for text boxes and header/footer text that is outside the indexed body.
- Added `document` content type metadata and document-specific chunks without table-style row prefixes.
- Preserved the existing table chunk format for Excel/CSV.
- Stored parser warnings in `documents.json` and displayed them in the file preview.
- Added focused parser, chunker, and PDF upload integration tests.

## Deliberately out of scope

- OCR for scanned PDFs or images.
- Legacy `.doc` conversion.
- Perfect extraction of floating text boxes, SmartArt, sidebars, footnotes, or complex tables.
- Automatic reindexing of documents uploaded before this change; those documents need to be uploaded again because the reindex endpoint is not implemented.

## Verification

- `compileall`: passed
- `pip check`: passed
- Focused unit tests: 6 passed
- P0 self-check: passed
- Existing smoke test: passed
- Frontend `tsc && vite build`: passed
- `git diff --check`: passed
- Secret filename scan: none found
- Debug statement scan: none found
