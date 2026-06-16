from collections.abc import Iterator
from dataclasses import dataclass

from .llm import LLMError, LLMProvider, OpenAICompatibleLLMProvider
from .retrieval import RetrievedChunk, RetrievalError, retrieve_chunks

NO_CONTEXT_ANSWER = "无法从当前知识库确认该问题的答案。"


class AnsweringError(Exception):
    """Raised when an answer cannot be generated."""


@dataclass(frozen=True)
class AnswerSource:
    citation: int
    vector_id: str
    text: str
    score: float | None
    metadata: dict


@dataclass(frozen=True)
class AnswerResult:
    answer: str
    sources: list[AnswerSource]


def answer_question(
    *,
    knowledge_base_id: str,
    question: str,
    top_k: int = 5,
    conversation_history: list[dict] | None = None,
    llm_provider: LLMProvider | None = None,
    retrieved_chunks: list[RetrievedChunk] | None = None,
) -> AnswerResult:
    clean_question = question.strip()
    if not clean_question:
        raise AnsweringError("Question is required")

    try:
        chunks = (
            retrieved_chunks
            if retrieved_chunks is not None
            else retrieve_chunks(
                knowledge_base_id=knowledge_base_id,
                query=clean_question,
                top_k=top_k,
            )
        )
    except RetrievalError as exc:
        raise AnsweringError(str(exc)) from exc

    sources = [_to_source(index, chunk) for index, chunk in enumerate(chunks, start=1)]
    if not sources:
        return AnswerResult(answer=NO_CONTEXT_ANSWER, sources=[])

    provider = llm_provider or OpenAICompatibleLLMProvider.from_settings()
    try:
        answer = provider.answer(
            system_prompt=_system_prompt(),
            user_prompt=_user_prompt(clean_question, sources, conversation_history or []),
        )
    except LLMError as exc:
        raise AnsweringError(str(exc)) from exc

    return AnswerResult(answer=answer, sources=sources)


def answer_question_stream(
    *,
    knowledge_base_id: str,
    question: str,
    top_k: int = 5,
    conversation_history: list[dict] | None = None,
    llm_provider: LLMProvider | None = None,
    retrieved_chunks: list[RetrievedChunk] | None = None,
) -> tuple[list[AnswerSource], Iterator[str]]:
    """流式问答：返回 (来源列表, token 迭代器)。"""
    clean_question = question.strip()
    if not clean_question:
        raise AnsweringError("Question is required")

    try:
        chunks = (
            retrieved_chunks
            if retrieved_chunks is not None
            else retrieve_chunks(
                knowledge_base_id=knowledge_base_id,
                query=clean_question,
                top_k=top_k,
            )
        )
    except RetrievalError as exc:
        raise AnsweringError(str(exc)) from exc

    sources = [_to_source(index, chunk) for index, chunk in enumerate(chunks, start=1)]
    if not sources:
        def _no_context_tokens() -> Iterator[str]:
            yield NO_CONTEXT_ANSWER

        return sources, _no_context_tokens()

    provider = llm_provider or OpenAICompatibleLLMProvider.from_settings()
    try:
        tokens = provider.stream_answer(
            system_prompt=_system_prompt(),
            user_prompt=_user_prompt(clean_question, sources, conversation_history or []),
        )
    except LLMError as exc:
        raise AnsweringError(str(exc)) from exc

    return sources, tokens


def _to_source(citation: int, chunk: RetrievedChunk) -> AnswerSource:
    return AnswerSource(
        citation=citation,
        vector_id=chunk.vector_id,
        text=chunk.text,
        score=chunk.score,
        metadata=chunk.metadata,
    )


def _system_prompt() -> str:
    return (
        "You are a grounded enterprise knowledge-base assistant. "
        "Answer only from the provided context. "
        "If the context does not contain enough evidence, say that the answer "
        "cannot be confirmed from the current knowledge base. "
        "Use citation markers like [1] and [2] for claims that rely on context. "
        "Do not invent facts or cite sources that are not provided."
    )


def _user_prompt(
    question: str, sources: list[AnswerSource], history: list[dict] | None = None
) -> str:
    context_blocks = "\n\n".join(
        f"[{source.citation}] {source.text}" for source in sources
    )
    parts: list[str] = []

    if history:
        parts.append("Conversation history:")
        for msg in history:
            role_label = "User" if msg["role"] == "user" else "Assistant"
            parts.append(f"{role_label}: {msg['content']}")
        parts.append("")

    parts.append(f"Question:\n{question}")
    parts.append(f"Context:\n{context_blocks}")
    parts.append(
        "Answer in Chinese when the question is Chinese; otherwise answer in the "
        "same language as the question. Include citation markers for supported claims."
    )
    return "\n\n".join(parts)

