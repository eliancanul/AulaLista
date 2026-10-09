"""PDF extraction with explicit page coverage and reviewable source segments.

Offsets refer to ``pages[n].text``, not PDF coordinates or legacy interpreter
anchors. ``raw_text`` retains pypdf plain output for comparison. Layout ordering
and structural hints require human review; this module performs no OCR.
"""

from __future__ import annotations

import hashlib
import io
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import PurePath
from typing import Callable, Literal

from pypdf import PdfReader

from curriculum.source_segments import extracted_page_segments


class DocumentExtractionError(ValueError):
    """An upload cannot be processed as a supported PDF."""


class DocumentExtractionCancelled(DocumentExtractionError):
    """The caller cancelled extraction between pages."""


@dataclass(frozen=True)
class ExtractedPage:
    page: int
    text: str
    raw_text: str
    status: Literal["extracted", "empty", "failed"]
    method: Literal["pypdf-layout", "pypdf-plain", "none"]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class ExtractedDocument:
    document_id: str
    pages: tuple[ExtractedPage, ...]

    @property
    def status(self) -> str:
        readable = sum(page.status == "extracted" for page in self.pages)
        return "complete" if readable == len(self.pages) else "partial" if readable else "unreadable"

    @property
    def source_segments(self) -> list[dict]:
        return [segment for page in self.pages for segment in
                extracted_page_segments(page.text, self.document_id, page.page)]

    def to_dict(self) -> dict:
        return {
            "document_id": self.document_id,
            "status": self.status,
            "page_count": len(self.pages),
            "pages": [asdict(page) for page in self.pages],
            "source_segments": self.source_segments,
            "requires_review": True,
            "warnings": [
                "Revisa el orden de lectura, los encabezados y las filas de las tablas contra el PDF original.",
                *(warning for page in self.pages for warning in page.warnings),
            ],
        }


def _tokens(text: str) -> Counter:
    return Counter(re.findall(r"\w+|[^\w\s]", text))


def _extract_page(page, number: int) -> ExtractedPage:
    try:
        raw = page.extract_text() or ""
    except Exception:
        # pypdf may raise unrelated decoder and font exceptions on a single page.
        return ExtractedPage(number, "", "", "failed", "none", (
            f"No se pudo leer la página {number}. Revisa esa página en el PDF original.",
        ))
    if not raw.strip():
        return ExtractedPage(number, raw, raw, "empty", "pypdf-plain", (
            f"La página {number} no contiene texto digital legible. Puede estar vacía o ser una imagen; no se aplicó OCR.",
        ))
    try:
        layout = page.extract_text(
            extraction_mode="layout", layout_mode_space_vertically=False,
            layout_mode_strip_rotated=False,
        ) or ""
    except Exception:
        return ExtractedPage(number, raw, raw, "extracted", "pypdf-plain", (
            f"No se pudo reconstruir la distribución de la página {number}. Se conservó el texto lineal; revisa su orden.",
        ))
    if _tokens(layout) != _tokens(raw):
        return ExtractedPage(number, raw, raw, "extracted", "pypdf-plain", (
            f"La reconstrucción de la página {number} cambió el contenido. Se conservó el texto lineal; revisa sus tablas y columnas.",
        ))
    return ExtractedPage(number, layout, raw, "extracted", "pypdf-layout", ())


def extract_document(
    content: bytes, *, filename: str = "documento.pdf",
    max_bytes: int = 25 * 1024 * 1024, max_pages: int = 500,
    is_cancelled: Callable[[], bool] | None = None,
) -> ExtractedDocument:
    """Extract uploaded bytes, preserving every physical page and its warnings.

    The caller owns authentication, upload settings and persistence. Limits reject
    the whole document, never truncate it. A complete final EOF marker is required;
    only PDF whitespace may follow it. Cancellation propagates to the caller.
    """
    if type(max_bytes) is not int or max_bytes < 1 or type(max_pages) is not int or max_pages < 1:
        raise ValueError("Los límites de extracción deben ser enteros positivos.")
    if not isinstance(content, bytes):
        raise TypeError("La extracción requiere el contenido binario del PDF.")
    if PurePath(filename).suffix.lower() != ".pdf":
        raise DocumentExtractionError("Este lector admite archivos PDF. Convierte el documento a PDF e inténtalo de nuevo.")
    if len(content) > max_bytes:
        raise DocumentExtractionError("El PDF supera el tamaño permitido. Divide el documento antes de cargarlo.")
    if not content.startswith(b"%PDF-"):
        raise DocumentExtractionError("El archivo no contiene un PDF válido.")
    if is_cancelled and is_cancelled():
        raise DocumentExtractionCancelled("La lectura del PDF fue cancelada.")
    if not content.rstrip(b"\x00\t\n\x0c\r ").endswith(b"%%EOF"):
        raise DocumentExtractionError(
            "No se pudo abrir el PDF: no tiene un cierre completo al final del archivo. "
            "Puede estar truncado o contener datos posteriores. Vuelve a exportarlo o cargarlo."
        )
    try:
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted:
            raise DocumentExtractionError("El PDF está protegido. Carga una copia sin contraseña que tengas autorización para usar.")
        page_count = len(reader.pages)
        if not page_count:
            raise DocumentExtractionError("El PDF no contiene páginas.")
        if page_count > max_pages:
            raise DocumentExtractionError("El PDF supera el límite de páginas. Divide el documento antes de cargarlo.")
    except DocumentExtractionError:
        raise
    except Exception as error:
        raise DocumentExtractionError("No se pudo abrir el PDF. Revisa el archivo e inténtalo de nuevo.") from error
    pages = []
    for index in range(page_count):
        if is_cancelled and is_cancelled():
            raise DocumentExtractionCancelled("La lectura del PDF fue cancelada.")
        pages.append(_extract_page(reader.pages[index], index + 1))
    return ExtractedDocument(hashlib.sha256(content).hexdigest(), tuple(pages))
