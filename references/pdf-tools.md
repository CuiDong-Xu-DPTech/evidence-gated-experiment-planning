# Actual-PDF extraction and proof of reading

Use the source files referenced by the actual case; do not assume a PDF named `primary.pdf`, a pre-extracted answer layer, or a domain based on a filename. `scripts/pdf_tools.py` operates on the actual PDF bytes each run. It has no bundled papers or case-specific content and does not fetch sources from the network.

## Text pages

```bash
python3 "$SKILL_ROOT/scripts/pdf_tools.py" extract \
  --pdf "$ACTUAL_SOURCE_PDF" --work /app/work/pdf --pages all
```

`--pages` accepts `all`, a single 1-based page, or comma-separated 1-based ranges such as `1,5-7,11`. Do not treat a printed journal page as the PDF index without inspecting the page mapping. Each output page records both its `pdf_page_index` and the printed label where the parser can provide it, its requested extraction status and the actual text. Text from all pages need not be loaded into the model context at once: use the manifest and relevant method/table pages as the evidence requires.

The normal reader order is the declared Poppler executable when present, PyMuPDF, then pypdf. These are conditional choices, not undeclared mandatory dependencies. Force an available parser with `--reader pymupdf` or `--reader pypdf` to compare difficult text. A different extraction library is not an independent scientific source or confirmation of a claim. Missing modules/tools are logged separately from unreadable documents.

Read `extract-manifest.json` before reporting facts. It contains the source path/hash, actual PDF page count, requested pages, parser output filenames, failures, sparse pages, and actual MuPDF warnings. Warnings may be cosmetic font substitutions or structural cross-reference/stream repairs; inspect the wording instead of lumping both into a generic `complete` or `failed`. A source can be readable while still needing a second parser or image verification for the decision-critical table, glyph, unit, or formula. Parser confidence is not scientific certainty, and `primary_output` does not imply that every claim in the paper is verified.

## Render and inspect selected pages

```bash
python3 "$SKILL_ROOT/scripts/pdf_tools.py" render \
  --pdf "$ACTUAL_SOURCE_PDF" --work /app/work/pdf \
  --pages "$DECISION_CRITICAL_PAGES" --dpi 160
```

Add `--ocr` when a relevant page has no usable text layer; it creates real PNGs and per-page OCR text when Tesseract is available. Every render records the source hash, page, renderer, output PNG hash, execution errors and the next inspection requirement. Do not put rendered images or extracted original papers in the submitted Skill. These are runtime artifacts belonging under `/app/work` or case-approved output locations.

Use the environment's actual image/PDF viewing tool to inspect decision-critical pages: tables and merged cells, plots, exponent signs, chemical names, Greek letters, negative signs, unit headers, and handwritten annotations. If the evaluator cannot expose image content, state that visual verification was `not_run`; OCR alone does not resolve those ambiguities. Do not invent a missing value after a failed render or OCR call.

At the end, retain the requested-page manifest, relevant extracted text and warnings, the rendering/OCR tool versions and actions, and which critical facts were cross-checked visually. Text retrieval verifies the provenance of a locator, not citation entailment, experimental suitability, measurement uncertainty, or future performance.
