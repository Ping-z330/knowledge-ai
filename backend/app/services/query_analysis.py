"""Agentic RAG 查询分析服务。

功能：
- analyze_query_complexity: 判断查询是简单还是复杂
- 复杂查询自动拆分为原子性子问题
"""

import re
from dataclasses import dataclass
from typing import Literal

from ..services.llm_agent import ToolCallingLLMProvider


class QueryAnalysisError(Exception):
    """Raised when query analysis fails."""


@dataclass(frozen=True)
class QueryAnalysisResult:
    is_complex: bool
    sub_questions: list[str]
    route_source: Literal["rule", "llm", "fallback"] = "llm"
    route_reason: str = "llm_complexity_analysis"
    complexity_signals: tuple[str, ...] = ()


@dataclass(frozen=True)
class QueryStructureResult:
    decision: Literal["force_agentic", "force_standard", "needs_llm"]
    reason: str
    complexity_signals: tuple[str, ...]


_COMPLEX_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "explicit_comparison",
        re.compile(r"(?:比较|对比|区别|差异|有何不同|有什么不同|不同之处)"),
    ),
    (
        "cross_source_synthesis",
        re.compile(r"(?:配合阅读|共同说明|综合(?:说明|分析|比较)|以.+为准)"),
    ),
    (
        "temporal_multi_hop",
        re.compile(r"(?:之后|以后|变.+后|完成.+后).{0,24}(?:如何|为什么|怎样)"),
    ),
    (
        "causal_relationship",
        re.compile(r"为什么.{0,40}不会.{0,30}(?:时|之前|之后|中途)"),
    ),
    (
        "multiple_impacts",
        re.compile(r"(?:影响|作用于).{0,30}(?:和|与).{0,30}"),
    ),
    (
        "multiple_actors",
        re.compile(r"(?:和|与).{1,24}(?:在.+时|面对.+时).{0,20}(?:如何|怎样|应如何)"),
    ),
    (
        "contrast_clause",
        re.compile(r"(?:和|与).{0,40}(?:但|而).{0,40}(?:不同|区别|关系)"),
    ),
)

_AMBIGUOUS_REFERENCES = re.compile(
    r"(?:这个|那个|这些|那些|上述|前者|后者|它们|刚才|上面提到)"
)
_SIMPLE_PATTERNS = (
    re.compile(r"^(?:什么是|何为)"),
    re.compile(r"(?:是什么意思|意味着什么|有什么作用|哪个优先)[？?]?$"),
    re.compile(r"分别.{0,24}(?:是什么|什么意思|什么风险|什么场景)[？?]?$"),
)


_ANALYSIS_SYSTEM_PROMPT = """\
You are a query analysis expert. Analyze the user's question and determine:

1. Is this a SIMPLE question (answerable with a single retrieval from a knowledge base)?\
 Or is it a COMPLEX question (requiring multiple pieces of information that may be \
found in different parts of the knowledge base)?
2. If COMPLEX, decompose it into 2-4 atomic sub-questions. Each sub-question should be \
answerable with a SINGLE retrieval pass. Do NOT break it down more than necessary.

Guidelines:
- Factual lookup ("What is X?") → SIMPLE
- Definitional ("Define Y") → SIMPLE
- Questions with multiple parts ("How does A work and what about B?") → COMPLEX
- Comparison questions ("Compare X and Y") → COMPLEX (split into "What is X?" + "What is Y?")
- Multi-hop reasoning ("Based on X, what does Y imply?") → COMPLEX

Respond ONLY with a JSON object:
{
  "is_complex": true/false,
  "sub_questions": ["sub-question 1", "sub-question 2"]
}
If is_complex is false, sub_questions should be an empty list [].
"""

_DECOMPOSITION_SYSTEM_PROMPT = """\
You are decomposing a query that has ALREADY been classified as complex.
Split it into 2-3 atomic retrieval questions.

Requirements:
- Each question must contain one retrieval intent.
- Together they must cover the original question.
- Preserve important qualifiers, versions, actors, and stages.
- Do not repeat or paraphrase the same question.
- Do not decide whether the query is complex; decomposition is mandatory.

Respond ONLY with a JSON object:
{
  "sub_questions": ["sub-question 1", "sub-question 2"]
}
"""


def analyze_query_complexity(
    *,
    question: str,
    conversation_history: list[dict],
    llm_provider: ToolCallingLLMProvider,
) -> QueryAnalysisResult:
    """分析查询复杂度，必要时拆分为子问题。"""
    if not question.strip():
        raise QueryAnalysisError("Question is required")

    # 构建用户 prompt
    history_text = ""
    if conversation_history:
        parts = ["Previous conversation:"]
        for msg in conversation_history[-4:]:  # 只取最近 4 条
            role = "User" if msg["role"] == "user" else "Assistant"
            parts.append(f"{role}: {msg['content']}")
        history_text = "\n".join(parts) + "\n\n"

    user_prompt = f"{history_text}Question to analyze:\n{question}"

    try:
        result = llm_provider.chat_json(
            system_prompt=_ANALYSIS_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
    except Exception as exc:
        raise QueryAnalysisError(str(exc)) from exc

    is_complex = bool(result.get("is_complex", False))
    sub_questions = result.get("sub_questions", [])

    if not isinstance(sub_questions, list):
        sub_questions = []

    # 验证子问题
    sub_questions = [
        q.strip() for q in sub_questions if isinstance(q, str) and q.strip()
    ]

    # 如果标记为复杂但没有有效的子问题，降级为简单
    if is_complex and not sub_questions:
        is_complex = False

    return QueryAnalysisResult(
        is_complex=is_complex,
        sub_questions=sub_questions,
        route_source="llm",
        route_reason="llm_complexity_analysis",
    )


def classify_query_structure(
    *,
    question: str,
    conversation_history: list[dict],
) -> QueryStructureResult:
    """Classify clear structural intent before paying for an LLM route decision."""
    clean_question = question.strip()
    if not clean_question:
        raise QueryAnalysisError("Question is required")

    signals = tuple(
        name for name, pattern in _COMPLEX_PATTERNS if pattern.search(clean_question)
    )
    if signals:
        return QueryStructureResult(
            decision="force_agentic",
            reason=f"complex_structure:{','.join(signals)}",
            complexity_signals=signals,
        )

    if conversation_history or _AMBIGUOUS_REFERENCES.search(clean_question):
        return QueryStructureResult(
            decision="needs_llm",
            reason="context_or_reference_requires_llm",
            complexity_signals=(),
        )

    simple_signal = next(
        (pattern.pattern for pattern in _SIMPLE_PATTERNS if pattern.search(clean_question)),
        "single_intent_without_complex_signal",
    )
    return QueryStructureResult(
        decision="force_standard",
        reason=f"simple_structure:{simple_signal}",
        complexity_signals=(),
    )


def decompose_complex_query(
    *,
    question: str,
    conversation_history: list[dict],
    llm_provider: ToolCallingLLMProvider,
) -> list[str]:
    """Decompose a query whose complex route has already been decided."""
    clean_question = question.strip()
    if not clean_question:
        raise QueryAnalysisError("Question is required")
    history_text = ""
    if conversation_history:
        parts = ["Previous conversation:"]
        for msg in conversation_history[-4:]:
            role = "User" if msg["role"] == "user" else "Assistant"
            parts.append(f"{role}: {msg['content']}")
        history_text = "\n".join(parts) + "\n\n"
    try:
        result = llm_provider.chat_json(
            system_prompt=_DECOMPOSITION_SYSTEM_PROMPT,
            user_prompt=f"{history_text}Complex question to decompose:\n{clean_question}",
        )
    except Exception as exc:
        raise QueryAnalysisError(str(exc)) from exc
    values = result.get("sub_questions", [])
    if not isinstance(values, list):
        return []
    return normalize_sub_questions(
        original_question=clean_question,
        sub_questions=values,
    )


def normalize_sub_questions(
    *,
    original_question: str,
    sub_questions: list[object],
    max_items: int = 3,
) -> list[str]:
    """Filter and deduplicate atomic retrieval intents without another LLM call."""
    normalized: list[str] = []
    comparison_keys: list[str] = []
    for value in sub_questions:
        if not isinstance(value, str):
            continue
        clean = " ".join(value.split()).strip()
        if not clean:
            continue
        key = re.sub(r"[\W_]+", "", clean, flags=re.UNICODE).casefold()
        if not key:
            continue
        if any(
            key == existing
            or (len(key) >= 8 and key in existing)
            or (len(existing) >= 8 and existing in key)
            for existing in comparison_keys
        ):
            continue
        normalized.append(clean)
        comparison_keys.append(key)
        if len(normalized) == max_items:
            break

    if len(normalized) < 2:
        return []
    return normalized
