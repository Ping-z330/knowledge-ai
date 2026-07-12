"""Agentic RAG 自纠正服务。

功能：
- evaluate_context_sufficiency: LLM 评估检索上下文是否足够回答问题
- rewrite_query_for_retrieval: LLM 改写查询以改善检索效果
"""

from dataclasses import dataclass

from ..services.llm_agent import ToolCallingLLMProvider


class SelfCorrectiveError(Exception):
    """Raised when self-corrective operations fail."""


@dataclass(frozen=True)
class ContextEvaluation:
    score: int  # 1-5
    reasoning: str


_EVALUATION_SYSTEM_PROMPT = """\
You are a context quality evaluator. Given a question and a set of retrieved text \
chunks, rate how well the context can answer the question.

Scoring:
1 = Completely irrelevant — the context does not address the question at all
2 = Marginally relevant — contains some related info but cannot answer the question
3 = Partially adequate — can answer partially but missing key details
4 = Mostly sufficient — answers well with only minor gaps
5 = Fully sufficient — completely and precisely answers the question

Respond ONLY with a JSON object:
{
  "score": <integer 1-5>,
  "reasoning": "<1-2 sentence explanation in the same language as the question>"
}
"""


def evaluate_context_sufficiency(
    *,
    question: str,
    retrieved_texts: list[str],
    llm_provider: ToolCallingLLMProvider,
) -> ContextEvaluation:
    """LLM 评分检索上下文是否足够回答问题。"""
    if not question.strip():
        raise SelfCorrectiveError("Question is required")

    # 截断过长文本（每段最多 800 字符）
    truncated = []
    for i, text in enumerate(retrieved_texts):
        t = text[:800] + ("..." if len(text) > 800 else "")
        truncated.append(f"[{i + 1}] {t}")

    context_block = "\n\n".join(truncated)
    user_prompt = f"Question:\n{question}\n\nRetrieved context:\n{context_block}"

    try:
        result = llm_provider.chat_json(
            system_prompt=_EVALUATION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
    except Exception as exc:
        raise SelfCorrectiveError(str(exc)) from exc

    score = result.get("score", 3)
    reasoning = result.get("reasoning", "")

    if not isinstance(score, int) or score < 1 or score > 5:
        # 尝试转换为 int
        try:
            score = int(score)
        except (ValueError, TypeError):
            score = 3
        score = max(1, min(5, score))

    if not isinstance(reasoning, str):
        reasoning = ""

    return ContextEvaluation(score=score, reasoning=reasoning)


_REWRITE_SYSTEM_PROMPT = """\
You are a query rewriter for a semantic search system. The original query did not \
retrieve sufficient context from the knowledge base.

Rewrite the query to improve retrieval. Try one or more of these strategies:
- Make it more SPECIFIC (narrow the focus to a concrete aspect)
- Make it more ABSTRACT (broaden or generalize the concept)
- Use DIFFERENT KEYWORDS or synonyms
- Ask from a DIFFERENT ANGLE (e.g., "how to use X" → "X configuration guide")

Return ONLY a single rewritten query string that is likely to match relevant \
documents in the knowledge base.

Respond ONLY with a JSON object:
{
  "rewritten_query": "<the new query string>"
}
"""


def rewrite_query_for_retrieval(
    *,
    original_question: str,
    previous_queries: list[str],
    evaluation_reasoning: str,
    llm_provider: ToolCallingLLMProvider,
) -> str:
    """LLM 改写查询词，返回新的查询字符串。"""
    if not original_question.strip():
        raise SelfCorrectiveError("Original question is required")

    tried = "\n".join(f"- {q}" for q in previous_queries)
    user_prompt = (
        f"Original question: {original_question}\n\n"
        f"Previously tried queries:\n{tried}\n\n"
        f"Why previous retrieval was insufficient:\n{evaluation_reasoning}\n\n"
        f"Rewrite the query to retrieve better context."
    )

    try:
        result = llm_provider.chat_json(
            system_prompt=_REWRITE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
    except Exception as exc:
        raise SelfCorrectiveError(str(exc)) from exc

    rewritten = result.get("rewritten_query", "")
    if not isinstance(rewritten, str) or not rewritten.strip():
        # 回退：在原问题上加关键词变体
        return f"{original_question} details guide documentation"

    return rewritten.strip()
