from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree
import re
import zipfile


class DocumentParseError(Exception):
    """Raised when a document cannot be parsed into text."""


@dataclass(frozen=True)
class ExtractedSection:
    text: str
    source_label: str
    page_number: int | None = None
    section_title: str | None = None


@dataclass(frozen=True)
class ExtractedDocument:
    sections: list[ExtractedSection]


def parse_document(path: Path, filename: str) -> ExtractedDocument:
    extension = Path(filename).suffix.lower()
    if extension == ".txt":
        return _parse_plain_text(path, filename)
    if extension == ".md":
        return _parse_markdown(path, filename)
    if extension == ".docx":
        return _parse_docx(path, filename)
    if extension == ".doc":
        raise DocumentParseError("Legacy .doc files are not supported yet; use .docx")
    if extension == ".pdf":
        return _parse_pdf(path, filename)
    raise DocumentParseError(f"Unsupported file type: {extension}")


def _parse_plain_text(path: Path, filename: str) -> ExtractedDocument:
    text = _read_text_file(path)
    return _document_from_text(text, filename, source_label=filename)


def _parse_markdown(path: Path, filename: str) -> ExtractedDocument:
    text = _read_text_file(path)
    sections: list[ExtractedSection] = []
    current_title: str | None = None
    current_lines: list[str] = []

    for line in text.splitlines():
        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            _append_markdown_section(sections, filename, current_title, current_lines)
            current_title = heading.group(2).strip()
            current_lines = []
        else:
            current_lines.append(line)

    _append_markdown_section(sections, filename, current_title, current_lines)
    if not sections:
        return _document_from_text(text, filename, source_label=filename)
    return ExtractedDocument(sections=sections)


def _append_markdown_section(
    sections: list[ExtractedSection],
    filename: str,
    section_title: str | None,
    lines: list[str],
) -> None:
    text = "\n".join(lines).strip()
    if not text:
        return
    label = f"{filename}#{section_title}" if section_title else filename
    sections.append(
        ExtractedSection(
            text=text,
            source_label=label,
            section_title=section_title,
        )
    )


def _parse_docx(path: Path, filename: str) -> ExtractedDocument:
    try:
        with zipfile.ZipFile(path) as archive:
            xml = archive.read("word/document.xml")
    except (KeyError, zipfile.BadZipFile) as exc:
        raise DocumentParseError("Invalid .docx file") from exc

    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    root = ElementTree.fromstring(xml)
    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:p", namespace):
        text_parts = [
            node.text
            for node in paragraph.findall(".//w:t", namespace)
            if node.text
        ]
        paragraph_text = "".join(text_parts).strip()
        if paragraph_text:
            paragraphs.append(paragraph_text)

    return _document_from_text("\n\n".join(paragraphs), filename, source_label=filename)


def _parse_pdf(path: Path, filename: str) -> ExtractedDocument:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise DocumentParseError("PDF parsing requires the pypdf package") from exc

    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        raise DocumentParseError("Invalid PDF file") from exc

    sections: list[ExtractedSection] = []
    for index, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            sections.append(
                ExtractedSection(
                    text=text,
                    source_label=f"{filename} page {index}",
                    page_number=index,
                )
            )

    if not sections:
        raise DocumentParseError("No text could be extracted from the PDF")
    return ExtractedDocument(sections=sections)


def _read_text_file(path: Path) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise DocumentParseError("Text file encoding is not supported")


def _document_from_text(
    text: str,
    filename: str,
    *,
    source_label: str,
) -> ExtractedDocument:
    clean_text = text.strip()
    if not clean_text:
        raise DocumentParseError(f"No text could be extracted from {filename}")
    return ExtractedDocument(
        sections=[
            ExtractedSection(
                text=clean_text,
                source_label=source_label,
            )
        ]
    )

