"""Agentic RAG 的状态定义。"""

from pydantic import BaseModel, Field


class AgenticState(BaseModel):
    """LangGraph 中流转的 Agent 状态。"""

    # ---- 输入 ----
    kb_id: str = ""
    question: str = ""
    conversation_history: list[dict] = Field(default_factory=list)
    top_k: int = 5
    max_rounds: int = 3
    enable_web_search: bool = False

    # ---- 查询分析 ----
    is_complex: bool = False
    sub_queries: list[str] = Field(default_factory=list)
    current_sub_query_idx: int = 0

    # ---- 检索累积 ----
    retrieved_chunks_json: list[dict] = Field(default_factory=list)
    seen_chunk_ids: set[str] = Field(default_factory=set)
    retrieval_rounds: int = 0
    current_query: str = ""
    pending_new_chunks: list[dict] = Field(default_factory=list, exclude=True)

    # ---- 评估 ----
    context_score: int = 0  # 1-5
    context_evaluation: str = ""

    # ---- Web 搜索 ----
    web_search_results: list[dict] = Field(default_factory=list)
    web_search_used: bool = False

    # ---- 输出 ----
    final_answer: str = ""
    sources_json: list[dict] = Field(default_factory=list)
    retrieval_rounds_used: int = 0
    error: str = ""

    class Config:
        arbitrary_types_allowed = True
