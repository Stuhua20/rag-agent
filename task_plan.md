# Task Plan: Improve common single-/double-column document parsing

## Goal
Improve ingestion for common text-based single- and double-column PDF and DOCX files without changing Excel/CSV behavior or attempting universal-format support.

## Phases
- [x] Phase 1: Re-read the current parser pipeline and inspect existing user changes
- [x] Phase 2: Implement layout-aware PDF extraction and parser diagnostics
- [x] Phase 3: Improve/validate DOCX extraction and semantic document chunking
- [x] Phase 4: Add focused fixtures/tests and update documentation
- [x] Phase 5: Run verification, review the diff, and deliver

## Confirmed scope
- In scope: text-based PDF, common one-/two-column PDF layout ordering, ordinary DOCX paragraphs/tables, standard DOCX columns, existing Excel/CSV compatibility.
- Out of scope: OCR/scanned PDFs, legacy `.doc`, arbitrary formats, complex floating text boxes/SmartArt, perfect table reconstruction.

## Key decisions
- Keep the existing upload and workbook-shaped storage contract where practical.
- Use layout-aware PDF extraction with text-block coordinates; do not rely on line-only `pypdf.extract_text()` for the primary path.
- Preserve page/section metadata in chunks so citations remain useful.
- Do not overwrite unrelated existing working-tree changes.
- Keep OCR, legacy `.doc`, and complex floating-layout support outside this milestone.

## Errors Encountered
- The first combined `apply_patch` was rejected because it targeted the same file with multiple operations; the changes were applied as separate safe patches.
- The first PDF fixture used a built-in font that could not render Chinese test text; the fixture was changed to ASCII so it tests layout ordering rather than font embedding.
- The sandbox could not resolve the configured package mirror during installation; PyMuPDF was installed successfully after the required escalated network approval.

## Status
**Complete** - the common single-/double-column parser changes are implemented and verified; unrelated pre-existing working-tree changes were preserved.
