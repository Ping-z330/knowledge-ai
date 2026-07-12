from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)


class KnowledgeBaseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)


# 
class KnowledgeBaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    created_at: str
    updated_at: str


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    knowledge_base_id: str
    filename: str
    content_type: str
    storage_path: str
    parse_status: str
    index_status: str
    error_message: str | None
    created_at: str
    updated_at: str


class ChunkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    knowledge_base_id: str
    document_id: str
    chunk_index: int
    text: str
    source_label: str
    page_number: int | None
    section_title: str | None
    vector_id: str | None
    created_at: str


class DocumentParseResult(BaseModel):
    document: DocumentRead
    chunks: list[ChunkRead]


class BatchTaskResponse(BaseModel):
    scheduled: int
    document_ids: list[str]


class RetrievalRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)


class RetrievedChunkRead(BaseModel):
    vector_id: str
    text: str
    score: float | None
    metadata: dict


class RetrievalResponse(BaseModel):
    query: str
    results: list[RetrievedChunkRead]


class ConversationMessage(BaseModel):
    role: str = Field(pattern=r"^(user|assistant)$")
    content: str = Field(min_length=1, max_length=4000)


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)
    conversation_history: list[ConversationMessage] = Field(default_factory=list, max_length=20)
    conversation_id: str = ""


class AnswerSourceRead(BaseModel):
    citation: int
    vector_id: str
    text: str
    score: float | None
    metadata: dict


class QuestionResponse(BaseModel):
    question: str
    answer: str
    sources: list[AnswerSourceRead]


class QuestionAnswerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    knowledge_base_id: str
    conversation_id: str | None = None
    question: str
    answer: str
    sources: list[AnswerSourceRead]
    top_k: int
    rating: int | None = None
    created_at: str


class RatingUpdate(BaseModel):
    rating: int = Field(ge=-1, le=1)


class AgenticQuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)
    conversation_history: list[ConversationMessage] = Field(default_factory=list, max_length=20)
    max_retrieval_rounds: int = Field(default=3, ge=1, le=5)
    enable_web_search: bool = False
    conversation_id: str = ""


class AgenticQuestionResponse(BaseModel):
    question: str
    answer: str
    sources: list[AnswerSourceRead]
    retrieval_rounds_used: int
    context_score: int | None
    web_search_used: bool
    sub_queries_used: list[str]
