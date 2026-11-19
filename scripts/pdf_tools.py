#!/usr/bin/env python3
"""Extract actual PDF pages and render/OCR selected pages with explicit provenance."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from runtime import utc_now, write_json_atomic


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def page_numbers(value, count):
    if value.lower() == "all":
        return list(range(1, count + 1))
    numbers = set()
    for term in value.split(","):
        parts = term.strip().split("-", 1)
        try:
            if len(parts) == 1:
                numbers.add(int(parts[0]))
            else:
                start, end = map(int, parts)
                if end < start:
                    raise ValueError("descending page range")
                numbers.update(range(start, end + 1))
        except ValueError as error:
            raise ValueError("pages must be all or comma-separated 1-based pages/ranges") from error
    if not numbers or min(numbers) < 1 or max(numbers) > count:
        raise ValueError("page is outside the actual document")
    return sorted(numbers)


def mupdf_warnings():
    try:
        import fitz
        if hasattr(fitz.TOOLS, "mupdf_display_errors"):
            fitz.TOOLS.mupdf_display_errors(False)
        if hasattr(fitz.TOOLS, "mupdf_warnings"):
            text = fitz.TOOLS.mupdf_warnings()
            return str(text) if text else ""
        return ""
    except Exception as error:
        return "warning collection failed: " + type(error).__name__


def pymupdf_version():
    import fitz
    return str(getattr(fitz, "__doc__", "PyMuPDF (version unavailable)")).splitlines()[0]


def def_document(pdf):
    try:
        import fitz
        broken = mupdf_warnings()
        with fitz.open(str(pdf)) as document:
            return document.is_pdf, len(document), broken
    except Exception as error:
        raise ValueError("PDF open failed for %s: %s" % (pdf.name, type(error).__name__)) from error


def text_document(pdf, numbers, work, engine):
    output = work / ("pages-" + engine + ".jsonl")
    warnings = [mupdf_warnings()] if engine == "pymupdf" else []
    errors = []
    count = 0
    sparse = []
    if engine == "pymupdf":
        import fitz
        document = fitz.open(str(pdf))
        engine_version = pymupdf_version()
    else:
        import pypdf
        document = pypdf.PdfReader(str(pdf))
        engine_version = str(getattr(pypdf, "__version__", "unknown"))
    with output.open("w", encoding="utf-8") as stream:
        for number in numbers:
            text = ""
            error = None
            try:
                if engine == "pymupdf":
                    page = document[number - 1]
                    text = page.get_text(sort=True)
                    label = page.get_label() if hasattr(page, "get_label") else ""
                else:
                    text = document.pages[number - 1].extract_text() or ""
                    label = ""
                if not text.strip():
                    sparse.append(number)
            except Exception as exc:
                error = type(exc).__name__
                errors.append({"page": number, "error": error})
            count += 1
            stream.write(json.dumps({
                "pdf_page_index": number,
                "page_label": label,
                "status": "error" if error else ("sparse_text" if number in sparse else "text_extracted"),
                "error_type": error,
                "text_characters": len(text),
                "text": text
            }, ensure_ascii=False) + "\n")
    warnings.extend(w for w in [mupdf_warnings() if engine == "pymupdf" else ""] if w)
    return {
        "engine": engine, "engine_version": engine_version, "output": str(output), "pages_requested": count,
        "pages_with_errors": errors, "sparse_text_pages": sparse,
        "warnings": warnings,
        "parser_warnings_are_not_semantic_validation": True
    }


def external_text(pdf, numbers, work):
    executable = shutil.which("pdftotext")
    if not executable:
        raise RuntimeError("pdftotext is unavailable")
    output = work / "pages-pdftotext.jsonl"
    errors = []
    sparse = []
    with output.open("w", encoding="utf-8") as stream:
        for number in numbers:
            process = subprocess.run(
                [executable, "-f", str(number), "-l", str(number), "-layout", str(pdf), "-"],
                capture_output=True, text=True, timeout=90, shell=False,
            )
            text = process.stdout
            error = None if process.returncode == 0 else "exit_%d" % process.returncode
            if error:
                errors.append({"page": number, "error": error, "stderr": process.stderr[-500:]})
            if not text.strip():
                sparse.append(number)
            stream.write(json.dumps({
                "pdf_page_index": number, "page_label": "", "status": "error" if error else ("sparse_text" if number in sparse else "text_extracted"),
                "error_type": error, "text_characters": len(text), "text": text
            }, ensure_ascii=False) + "\n")
    return {"engine": "pdftotext", "output": str(output), "pages_requested": len(numbers), "pages_with_errors": errors, "sparse_text_pages": sparse, "warnings": []}


def render(pdf, numbers, work, dpi, ocr):
    executable = shutil.which("gs")
    rendered = []
    errors = []
    for number in numbers:
        target = work / ("page-%04d.png" % number)
        try:
            import fitz
            with fitz.open(str(pdf)) as document:
                page = document[number - 1]
                pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False)
                pix.save(str(target))
            renderer = "pymupdf"
        except ImportError:
            if not executable:
                raise RuntimeError("Neither PyMuPDF nor Ghostscript is available for rendering")
            process = subprocess.run([
                executable, "-q", "-dSAFER", "-dBATCH", "-dNOPAUSE", "-sDEVICE=png16m", "-r%d" % dpi,
                "-dFirstPage=%d" % number, "-dLastPage=%d" % number, "-sOutputFile=" + str(target), str(pdf)
            ], capture_output=True, text=True, timeout=90, shell=False)
            if process.returncode:
                errors.append({"page": number, "error": process.stderr[-500:]})
                continue
            renderer = "ghostscript"
        if not target.is_file() or target.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
            errors.append({"page": number, "error": "renderer did not produce a valid PNG"})
            continue
        record = {"pdf_page_index": number, "png": str(target), "renderer": renderer, "png_sha256": digest(target)}
        if ocr:
            ocr_engine = shutil.which("tesseract")
            if not ocr_engine:
                record["ocr"] = {"status": "unavailable", "semantic_review_required": True}
            else:
                text_path = work / ("page-%04d-ocr.txt" % number)
                process = subprocess.run([ocr_engine, str(target), "stdout"], capture_output=True, text=True, timeout=90, shell=False)
                text_path.write_text(process.stdout, encoding="utf-8")
                record["ocr"] = {
                    "status": "completed" if process.returncode == 0 else "failed",
                    "path": str(text_path), "stderr": process.stderr[-500:],
                    "ocr_confidence_is_not_measurement_uncertainty": True,
                }
        rendered.append(record)
    warning_text = mupdf_warnings()
    return {"rendered": rendered, "errors": errors, "warnings": [warning_text] if warning_text else [], "inspection_required": bool(rendered)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("extract", "render"):
        command = subparsers.add_parser(name)
        command.add_argument("--pdf", required=True, type=Path)
        command.add_argument("--work", required=True, type=Path)
        command.add_argument("--pages", default="all")
        if name == "extract":
            command.add_argument("--reader", choices=("auto", "pymupdf", "pypdf", "pdftotext"), default="auto")
        else:
            command.add_argument("--dpi", type=int, default=150)
            command.add_argument("--ocr", action="store_true")
    arguments = parser.parse_args()
    pdf = arguments.pdf.expanduser().resolve()
    work = arguments.work.expanduser().resolve()
    work.mkdir(parents=True, exist_ok=True)
    report = {
        "command": arguments.command, "started_at": utc_now(),
        "source": {"path": str(pdf), "sha256": None}, "status": "failed",
        "finished_at": None,
    }
    try:
        report["source"]["sha256"] = digest(pdf)
        is_pdf, count, open_warnings = def_document(pdf)
        if not is_pdf:
            raise ValueError("input is not a valid PDF")
        report["source"]["pages"] = count
        report["source"]["open_warnings"] = open_warnings
        numbers = page_numbers(arguments.pages, count)
        report["requested_pages"] = numbers
        if arguments.command == "extract":
            choices = [arguments.reader] if arguments.reader != "auto" else ["pdftotext", "pymupdf", "pypdf"]
            report["results"] = []
            for engine in choices:
                try:
                    if engine == "pdftotext":
                        result = external_text(pdf, numbers, work)
                    else:
                        result = text_document(pdf, numbers, work, engine)
                    report["results"].append(result)
                    if not result["pages_with_errors"]:
                        report["primary_output"] = result["output"]
                        break
                except Exception as error:
                    unavailable = isinstance(error, ImportError) or str(error).endswith("is unavailable")
                    report["results"].append({"engine": engine, "status": "unavailable" if unavailable else "failed", "error_type": type(error).__name__})
            report["status"] = "partial" if "primary_output" not in report else ("complete" if all(not result.get("pages_with_errors") for result in report["results"]) else "partial")
            warnings = [warning for result in report["results"] for warning in result.get("warnings", [])]
            sparse_pages = sorted({page for result in report["results"] for page in result.get("sparse_text_pages", [])})
            report["sparse_pages_requiring_review"] = sparse_pages
            if warnings and report["status"] == "complete":
                report["status"] = "partial_with_parser_warnings"
            if sparse_pages:
                report["status"] = "partial_with_sparse_text"
        else:
            if arguments.dpi < 36 or arguments.dpi > 600:
                raise ValueError("dpi must be between 36 and 600")
            report["result"] = render(pdf, numbers, work, arguments.dpi, arguments.ocr)
            report["status"] = "complete" if len(report["result"]["rendered"]) == len(numbers) and not report["result"]["errors"] else "partial"
        report["finished_at"] = utc_now()
        write_json_atomic(work / (arguments.command + "-manifest.json"), report)
        print(json.dumps({"status": report["status"], "manifest": str(work / (arguments.command + "-manifest.json")), "primary_output": report.get("primary_output")}, ensure_ascii=False))
        return 0 if report["status"] == "complete" else 2
    except Exception as error:
        report["error_type"] = type(error).__name__
        report["finished_at"] = utc_now()
        write_json_atomic(work / (arguments.command + "-manifest.json"), report)
        print(json.dumps({"status": "failed", "error_type": type(error).__name__, "manifest": str(work / (arguments.command + "-manifest.json"))}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
