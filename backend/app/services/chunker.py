from dataclasses import dataclass
import re

from .document_parser import ExtractedDocument, ExtractedSection


@dataclass(frozen=True)
class TextChunk:
    chunk_index: int
    text: str
    source_label: str
    page_number: int | None
    section_title: str | None


_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")


def chunk_document(
    document: ExtractedDocument,
    *,
    chunk_size: int = 1200,
    chunk_overlap: int = 200,
) -> list[TextChunk]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError(
            "chunk_overlap must be greater than or equal to zero and less than chunk_size"
        )

    chunks: list[TextChunk] = []
    for section in document.sections:
        paragraphs = _extract_paragraphs(section.text)
        section_chunks = _build_chunks_from_paragraphs(
            paragraphs,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        for text in section_chunks:
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


def _extract_paragraphs(text: str) -> list[str]:
    """按空行切段落，每段内规范化空白。"""
    parts = _PARAGRAPH_SPLIT.split(text)
    result: list[str] = []
    for part in parts:
        normalized = " ".join(part.split())
        if normalized:
            result.append(normalized)
    return result


def _build_chunks_from_paragraphs(
    paragraphs: list[str],
    *,
    chunk_size: int,
    chunk_overlap: int,
) -> list[str]:
    """将段落累积成 chunk，超长段落用滑窗拆分。"""
    chunks: list[str] = []
    buffer: list[str] = []
    buffer_len = 0

    for paragraph in paragraphs:
        para_len = len(paragraph)

        # 单段落超过 chunk_size，先 flush buffer 再滑窗切割
        if para_len > chunk_size:
            if buffer:
                chunks.append("\n\n".join(buffer))
                buffer = []
                buffer_len = 0
            chunks.extend(
                _sliding_window_chunks(paragraph, chunk_size, chunk_overlap)
            )
            continue

        # 加入当前段落会超出，flush buffer
        if buffer and buffer_len + 2 + para_len > chunk_size:
            chunks.append("\n\n".join(buffer))
            buffer = []
            buffer_len = 0

        buffer.append(paragraph)
        buffer_len += (2 if buffer_len > 0 else 0) + para_len

    if buffer:
        chunks.append("\n\n".join(buffer))

    return chunks


def _sliding_window_chunks(
    text: str,
    chunk_size: int,
    chunk_overlap: int,
) -> list[str]:
    """字符滑窗切割长文本。"""
    pieces: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        piece = text[start:end].strip()
        if piece:
            pieces.append(piece)
        if end == len(text):
            break
        start = end - chunk_overlap
    return pieces
