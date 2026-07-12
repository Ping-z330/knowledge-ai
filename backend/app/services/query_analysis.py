"""Agentic RAG 查询分析服务。

功能：
- analyze_query_complexity: 判断查询是简单还是复杂
- 复杂查询自动拆分为原子性子问题
"""

from dataclasses import dataclass

from ..services.llm_agent import ToolCallingLLMProvider


class QueryAnalysisError(Exception):
    """Raised when query analysis fails."""


@dataclass(frozen=True)
class QueryAnalysisResult:
    is_complex: bool
    sub_questions: list[str]


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
    )
