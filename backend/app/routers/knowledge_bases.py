from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status

from ..database import connection_scope
from ..repositories.chunks import ChunkRepository
from ..repositories.documents import DocumentRepository
from ..repositories.knowledge_bases import KnowledgeBaseRepository
from ..repositories.question_answers import QuestionAnswerRepository
from ..schemas import (
    ChunkRead,
    DocumentParseResult,
    DocumentRead,
    KnowledgeBaseCreate,
    KnowledgeBaseRead,
    KnowledgeBaseUpdate,
    QuestionAnswerRead,
    QuestionRequest,
    QuestionResponse,
    RetrievalRequest,
    RetrievalResponse,
)
from ..services.answering import AnsweringError, answer_question
from ..services.chunker import chunk_document
from ..services.document_parser import DocumentParseError, parse_document
from ..services.document_storage import (
    build_storage_path,
    save_upload_file,
    validate_upload_filename,
)
from ..services.indexing import IndexingError, index_document_chunks
from ..services.retrieval import RetrievalError, retrieve_chunks

# 创建API路由器，所有路由都以/api/knowledge-bases为前缀，并且属于knowledge-bases标签
router = APIRouter(prefix="/api/knowledge-bases", tags=["knowledge-bases"])


def _source_to_dict(source: object) -> dict:
    return {
        "citation": source.citation,
        "vector_id": source.vector_id,
        "text": source.text,
        "score": source.score,
        "metadata": source.metadata,
    }


# 列出所有知识库
@router.get("", response_model=list[KnowledgeBaseRead])
def list_knowledge_bases() -> list[dict]:
    with connection_scope() as connection:
        return KnowledgeBaseRepository(connection).list()

# 创建一个新的知识库，接收KnowledgeBaseCreate模型作为请求体，并返回创建的知识库信息，状态码为201 Created
@router.post(
    "",
    response_model=KnowledgeBaseRead,
    status_code=status.HTTP_201_CREATED,
)
def create_knowledge_base(payload: KnowledgeBaseCreate) -> dict:
    with connection_scope() as connection:
        return KnowledgeBaseRepository(connection).create(payload)

# 获取指定ID的知识库信息，如果知识库不存在则返回404 Not Found错误
@router.get("/{knowledge_base_id}", response_model=KnowledgeBaseRead)
def get_knowledge_base(knowledge_base_id: str) -> dict:
    with connection_scope() as connection:
        knowledge_base = KnowledgeBaseRepository(connection).get(knowledge_base_id)
    if knowledge_base is None:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return knowledge_base


@router.patch("/{knowledge_base_id}", response_model=KnowledgeBaseRead)
def update_knowledge_base(
    knowledge_base_id: str,
    payload: KnowledgeBaseUpdate,
) -> dict:
    with connection_scope() as connection:
        knowledge_base = KnowledgeBaseRepository(connection).update(knowledge_base_id, payload)
    if knowledge_base is None:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return knowledge_base


@router.delete("/{knowledge_base_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_knowledge_base(knowledge_base_id: str) -> Response:
    with connection_scope() as connection:
        deleted = KnowledgeBaseRepository(connection).delete(knowledge_base_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{knowledge_base_id}/documents", response_model=list[DocumentRead])
def list_documents(knowledge_base_id: str) -> list[dict]:
    with connection_scope() as connection:
        knowledge_base = KnowledgeBaseRepository(connection).get(knowledge_base_id)
        if knowledge_base is None:
            raise HTTPException(status_code=404, detail="Knowledge base not found")
        return DocumentRepository(connection).list_for_knowledge_base(knowledge_base_id)


@router.post(
    "/{knowledge_base_id}/documents",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
)
def upload_document(
    knowledge_base_id: str,
    file: UploadFile = File(...),
) -> dict:
    try:
        filename = validate_upload_filename(file.filename or "")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    with connection_scope() as connection:
        knowledge_base = KnowledgeBaseRepository(connection).get(knowledge_base_id)
        if knowledge_base is None:
            raise HTTPException(status_code=404, detail="Knowledge base not found")

        storage_path = build_storage_path(knowledge_base_id, filename)
        try:
            save_upload_file(file, storage_path)
        except OSError as exc:
            raise HTTPException(status_code=500, detail="Failed to save upload") from exc

        return DocumentRepository(connection).create_uploaded(
            knowledge_base_id=knowledge_base_id,
            filename=filename,
            content_type=file.content_type or "application/octet-stream",
            storage_path=str(storage_path),
        )


@router.delete(
    "/{knowledge_base_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_document(knowledge_base_id: str, document_id: str) -> Response:
    with connection_scope() as connection:
        deleted = DocumentRepository(connection).delete(knowledge_base_id, document_id)

    if deleted is None:
        raise HTTPException(status_code=404, detail="Document not found")

    storage_path = Path(deleted["storage_path"])
    if storage_path.exists():
        storage_path.unlink()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{knowledge_base_id}/documents/{document_id}/parse",
    response_model=DocumentParseResult,
)
def parse_uploaded_document(knowledge_base_id: str, document_id: str) -> dict:
    with connection_scope() as connection:
        document_repository = DocumentRepository(connection)
        document = document_repository.get(document_id)
        if document is None or document["knowledge_base_id"] != knowledge_base_id:
            raise HTTPException(status_code=404, detail="Document not found")

        path = Path(document["storage_path"])
        if not path.exists():
            updated = document_repository.update_parse_status(
                document_id,
                parse_status="failed",
                error_message="Uploaded file is missing from storage",
            )
            connection.commit()
            raise HTTPException(status_code=500, detail=updated["error_message"])

        try:
            extracted = parse_document(path, document["filename"])
            chunks = chunk_document(extracted)
            if not chunks:
                raise DocumentParseError("No chunks could be created from document text")
        except DocumentParseError as exc:
            updated = document_repository.update_parse_status(
                document_id,
                parse_status="failed",
                error_message=str(exc),
            )
            connection.commit()
            raise HTTPException(status_code=400, detail=updated["error_message"]) from exc

        chunk_rows = ChunkRepository(connection).replace_for_document(
            knowledge_base_id=knowledge_base_id,
            document_id=document_id,
            chunks=chunks,
        )
        updated = document_repository.update_parse_status(
            document_id,
            parse_status="parsed",
            error_message=None,
        )
        return {"document": updated, "chunks": chunk_rows}


@router.get(
    "/{knowledge_base_id}/documents/{document_id}/chunks",
    response_model=list[ChunkRead],
)
def list_document_chunks(knowledge_base_id: str, document_id: str) -> list[dict]:
    with connection_scope() as connection:
        document = DocumentRepository(connection).get(document_id)
        if document is None or document["knowledge_base_id"] != knowledge_base_id:
            raise HTTPException(status_code=404, detail="Document not found")
        return ChunkRepository(connection).list_for_document(document_id)


@router.post(
    "/{knowledge_base_id}/documents/{document_id}/index",
    response_model=DocumentRead,
)
def index_uploaded_document(knowledge_base_id: str, document_id: str) -> dict:
    with connection_scope() as connection:
        document_repository = DocumentRepository(connection)
        chunk_repository = ChunkRepository(connection)

        document = document_repository.get(document_id)
        if document is None or document["knowledge_base_id"] != knowledge_base_id:
            raise HTTPException(status_code=404, detail="Document not found")

        chunks = chunk_repository.list_for_document(document_id)
        try:
            result = index_document_chunks(
                knowledge_base_id=knowledge_base_id,
                document=document,
                chunks=chunks,
            )
        except IndexingError as exc:
            updated = document_repository.update_index_status(
                document_id,
                index_status="failed",
                error_message=str(exc),
            )
            connection.commit()
            raise HTTPException(status_code=400, detail=updated["error_message"]) from exc

        chunk_repository.set_vector_ids(result.vector_ids_by_chunk_id)
        updated = document_repository.update_index_status(
            document_id,
            index_status="indexed",
            error_message=None,
        )
        return updated


@router.post("/{knowledge_base_id}/retrieve", response_model=RetrievalResponse)
def retrieve_from_knowledge_base(
    knowledge_base_id: str,
    payload: RetrievalRequest,
) -> dict:
    with connection_scope() as connection:
        knowledge_base = KnowledgeBaseRepository(connection).get(knowledge_base_id)
        if knowledge_base is None:
            raise HTTPException(status_code=404, detail="Knowledge base not found")

    try:
        results = retrieve_chunks(
            knowledge_base_id=knowledge_base_id,
            query=payload.query,
            top_k=payload.top_k,
        )
    except RetrievalError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "query": payload.query,
        "results": [
            {
                "vector_id": result.vector_id,
                "text": result.text,
                "score": result.score,
                "metadata": result.metadata,
            }
            for result in results
        ],
    }


@router.post("/{knowledge_base_id}/questions", response_model=QuestionResponse)
def answer_from_knowledge_base(
    knowledge_base_id: str,
    payload: QuestionRequest,
) -> dict:
    with connection_scope() as connection:
        knowledge_base = KnowledgeBaseRepository(connection).get(knowledge_base_id)
        if knowledge_base is None:
            raise HTTPException(status_code=404, detail="Knowledge base not found")

    try:
        result = answer_question(
            knowledge_base_id=knowledge_base_id,
            question=payload.question,
            top_k=payload.top_k,
        )
    except AnsweringError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    sources = [_source_to_dict(source) for source in result.sources]
    with connection_scope() as connection:
        QuestionAnswerRepository(connection).create(
            knowledge_base_id=knowledge_base_id,
            question=payload.question,
            answer=result.answer,
            sources=sources,
            top_k=payload.top_k,
        )

    return {
        "question": payload.question,
        "answer": result.answer,
        "sources": sources,
    }


@router.get(
    "/{knowledge_base_id}/question-answers",
    response_model=list[QuestionAnswerRead],
)
def list_question_answers(knowledge_base_id: str) -> list[dict]:
    with connection_scope() as connection:
        knowledge_base = KnowledgeBaseRepository(connection).get(knowledge_base_id)
        if knowledge_base is None:
            raise HTTPException(status_code=404, detail="Knowledge base not found")
        return QuestionAnswerRepository(connection).list_for_knowledge_base(
            knowledge_base_id,
        )


@router.delete(
    "/{knowledge_base_id}/question-answers/{answer_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_question_answer(knowledge_base_id: str, answer_id: str) -> Response:
    with connection_scope() as connection:
        knowledge_base = KnowledgeBaseRepository(connection).get(knowledge_base_id)
        if knowledge_base is None:
            raise HTTPException(status_code=404, detail="Knowledge base not found")
        deleted = QuestionAnswerRepository(connection).delete(knowledge_base_id, answer_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Question answer not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
