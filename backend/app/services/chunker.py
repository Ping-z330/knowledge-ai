from dataclasses import dataclass

from .document_parser import ExtractedDocument, ExtractedSection


@dataclass(frozen=True)
class TextChunk:
    chunk_index: int
    text: str
    source_label: str
    page_number: int | None
    section_title: str | None


def chunk_document(
    document: ExtractedDocument,
    *,
    chunk_size: int = 1200,
    chunk_overlap: int = 200,
) -> list[TextChunk]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be greater than or equal to zero and less than chunk_size")

    chunks: list[TextChunk] = []
    for section in document.sections:
        for text in _split_section_text(section.text, chunk_size, chunk_overlap):
            chunks.append(
                TextChunk(
                    chunk_index=len(chunks),
                    text=text,
                    source_label=section.source_label,
                    page_number=section.page_number,
                    section_title=section.section_title,
                )
            )
    return chunks


def _split_section_text(
    text: str,
    chunk_size: int,
    chunk_overlap: int,
) -> list[str]:
    clean_text = " ".join(text.split())
    if not clean_text:
        return []

    pieces: list[str] = []
    start = 0
    while start < len(clean_text):
        end = min(start + chunk_size, len(clean_text))
        piece = clean_text[start:end].strip()
        if piece:
            pieces.append(piece)
        if end == len(clean_text):
            break
        start = end - chunk_overlap
    return pieces

