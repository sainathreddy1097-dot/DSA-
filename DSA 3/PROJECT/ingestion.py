"""Bounded, local-only document validation, extraction, and segmentation."""

from dataclasses import dataclass
import hashlib
from io import BytesIO
from pathlib import Path
import re
from zipfile import BadZipFile, ZipFile

from docx import Document
from pypdf import PdfReader


MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MEDIA_TYPES = {
    ".txt": "text/plain",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pdf": "application/pdf",
}


class IngestionError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class DocumentInput:
    filename: str
    extension: str
    media_type: str
    sha256: str
    content: bytes


@dataclass(frozen=True)
class Segment:
    key: str
    title: str
    text: str
    position: int


def validate_upload(filename: str, content: bytes) -> DocumentInput:
    safe_name = Path(filename).name
    extension = Path(safe_name).suffix.casefold()
    if extension not in MEDIA_TYPES:
        raise IngestionError("unsupported_document", "Only PDF, DOCX, or TXT documents are supported")
    if not content:
        raise IngestionError("empty_document", "The selected document is empty")
    if len(content) > MAX_UPLOAD_BYTES:
        raise IngestionError("document_too_large", "The document exceeds the 10 MiB upload limit")
    if extension == ".pdf" and not content.startswith(b"%PDF-"):
        raise IngestionError("invalid_document", "The file is not a valid PDF document")
    if extension == ".docx":
        try:
            with ZipFile(BytesIO(content)) as archive:
                names = set(archive.namelist())
                if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                    raise IngestionError("invalid_document", "The file is not a valid DOCX document")
        except BadZipFile as error:
            raise IngestionError("invalid_document", "The file is not a valid DOCX document") from error
    if extension == ".txt":
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise IngestionError("invalid_encoding", "TXT documents must use UTF-8 encoding") from error
    return DocumentInput(
        filename=safe_name,
        extension=extension,
        media_type=MEDIA_TYPES[extension],
        sha256=hashlib.sha256(content).hexdigest(),
        content=content,
    )


def _normalize_text(value: str) -> str:
    lines = [line.rstrip() for line in value.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    normalized: list[str] = []
    previous_blank = False
    for line in lines:
        blank = not line.strip()
        if blank and previous_blank:
            continue
        normalized.append(line)
        previous_blank = blank
    return "\n".join(normalized).strip()


def extract_text(document: DocumentInput) -> str:
    try:
        if document.extension == ".txt":
            text = document.content.decode("utf-8")
        elif document.extension == ".pdf":
            reader = PdfReader(BytesIO(document.content))
            text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
        else:
            source = Document(BytesIO(document.content))
            blocks: list[str] = []
            for item in source.iter_inner_content():
                if hasattr(item, "rows"):
                    for row in item.rows:
                        blocks.append(" | ".join(cell.text.strip() for cell in row.cells))
                elif item.text.strip():
                    blocks.append(item.text.strip())
            text = "\n".join(blocks)
    except IngestionError:
        raise
    except Exception as error:
        raise IngestionError("invalid_document", "The document could not be read") from error
    normalized = _normalize_text(text)
    if not normalized:
        raise IngestionError(
            "document_text_unavailable",
            "No extractable text was found; OCR is not configured for scanned documents",
        )
    return normalized


NUMBERED_HEADING = re.compile(r"^(\d+(?:\.\d+)*)(?:[.)])?\s+(.{2,160})$")
NAMED_HEADING = re.compile(r"^(?:ARTICLE|SECTION)\s+[A-Z0-9IVX.-]+\s*[:.-]?\s*(.{2,160})$", re.IGNORECASE)


def _heading_title(line: str) -> str | None:
    numbered = NUMBERED_HEADING.match(line)
    if numbered:
        return numbered.group(2).strip(" .:-")
    named = NAMED_HEADING.match(line)
    if named:
        return named.group(1).strip(" .:-")
    stripped = line.strip()
    if 3 <= len(stripped) <= 100 and stripped == stripped.upper() and any(character.isalpha() for character in stripped):
        return stripped.title()
    return None


def segment_clauses(text: str) -> list[Segment]:
    normalized = _normalize_text(text)
    if not normalized:
        raise IngestionError("document_text_unavailable", "No extractable text was found")
    raw_segments: list[tuple[str, list[str]]] = []
    current_title: str | None = None
    current_lines: list[str] = []
    found_heading = False
    for line in normalized.splitlines():
        title = _heading_title(line.strip())
        if title:
            if current_lines:
                raw_segments.append((current_title or "Preamble", current_lines))
            current_title = title
            current_lines = []
            found_heading = True
        else:
            current_lines.append(line)
    if current_lines:
        raw_segments.append((current_title or "Full document text", current_lines))
    if not found_heading:
        return [Segment(key="C01", title="Full document text", text=normalized, position=1)]
    return [
        Segment(key=f"C{position:02d}", title=title, text=_normalize_text("\n".join(lines)), position=position)
        for position, (title, lines) in enumerate(raw_segments, 1)
        if _normalize_text("\n".join(lines))
    ]
