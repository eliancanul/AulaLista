"""Literal digital text from one verified source snapshot for review context.

This is separate from interpreted dossier fields. No OCR, layout reconstruction,
field confirmation, model call or source mutation occurs here.
"""
import hashlib
import io

from pypdf import PdfReader

from curriculum.teacher_review_provider import ReviewProviderError

# A source this large cannot fit in the existing 4 MiB full-request envelope.
# Reject the whole request; never return or transmit an extracted prefix.
MAX_SOURCE_TEXT_BYTES = 4 * 1024 * 1024


def source_document_context(job, dossier):
    try:
        with job.pdf.open("rb") as stream:
            content = stream.read()
    except (OSError, ValueError):
        raise ReviewProviderError("source_context_unavailable") from None
    source_sha256 = hashlib.sha256(content).hexdigest()
    if source_sha256 != dossier.source_sha256.lower():
        raise ReviewProviderError("source_context_changed")
    try:
        # Hash and extract the same immutable bytes, never reopen the path.
        reader = PdfReader(io.BytesIO(content))
        page_count = len(reader.pages)
    except Exception:
        raise ReviewProviderError("source_context_unavailable") from None
    if page_count != dossier.page_count:
        raise ReviewProviderError("source_context_changed")

    pages = []
    text_bytes = 0
    for index in range(page_count):
        try:
            text = reader.pages[index].extract_text()
            if text is None:
                text = ""
            if not isinstance(text, str):
                raise ValueError("Non-text extraction result")
            text_bytes += len(text.encode("utf-8"))
            if text_bytes > MAX_SOURCE_TEXT_BYTES:
                raise ReviewProviderError("gemini_full_context_too_large")
            status = "text" if text.strip() else "no_digital_text"
        except ReviewProviderError:
            raise
        except Exception:
            text, status = None, "extraction_unavailable"
        pages.append({"page_number": index + 1, "text": text, "status": status})
    return {"source_sha256": source_sha256, "page_count": page_count,
            "representation": "pypdf_digital_text", "ocr_performed": False,
            "missing_text_pages": [page["page_number"] for page in pages if page["status"] != "text"],
            "pages": pages}
