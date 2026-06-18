from pathlib import Path

import json
import logging

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import StreamingResponse

from ..auth import require_api_token
from ..database import connection_scope
from ..task_queue import TASK_INDEX, TASK_PARSE, task_queue
from ..repositories.chunks import ChunkRepository
from ..repositories.documents import DocumentRepository
from ..repositories.knowledge_bases import KnowledgeBaseRepository
from ..repositories.question_answers import QuestionAnswerRepository
from ..schemas import (
    BatchTaskResponse,
    ChunkRead,
    DocumentRead,
    KnowledgeBaseCreate,
    KnowledgeBaseRead,
    KnowledgeBaseUpdate,
    PaginatedResponse,
    QuestionAnswerRead,
    QuestionRequest,
    QuestionResponse,
    RatingUpdate,
    RetrievalRequest,
    RetrievalResponse,
)
from ..services.answering import AnsweringError, answer_question, answer_question_stream
from ..services.chunker import chunk_document
from ..services.document_parser import DocumentParseError, parse_document
from ..services.document_storage import (
    build_storage_path,
    save_upload_file,
    validate_upload_filename,
)
from ..services.indexing import (
    IndexingError,
    delete_document_vectors,
    index_document_chunks,
    rebuild_keyword_index,
)
from ..services.retrieval import RetrievalError, retrieve_chunks

# 创建API路由器，所有路由都以/api/knowledge-bases为前缀，并且属于knowledge-bases标签
router = APIRouter(
    prefix="/api/knowledge-bases",
    tags=["knowledge-bases"],
    dependencies=[Depends(require_api_token)],
)


def _source_to_dict(source: object) -> dict:
    return {
        "citation": source.citation,
        "vector_id": source.vector_id,
        "text": source.text,
        "score": source.score,
        "metadata": source.metadata,
    }

# 运行文档解析任务，从数据库中获取文档信息，删除旧的向量数据，解析文档内容并分块，
# 然后将新的分块数据保存到数据库中，并更新文档的解析状态和索引状态
def _run_parse_document_task(knowledge_base_id: str, document_id: str) -> None:
    with connection_scope() as connection:
        # 验证文档是否存在且属于指定的知识库
        document_repository = DocumentRepository(connection)
        # 获取文档信息，如果文档不存在或者不属于指定的知识库，则直接返回
        document = document_repository.get(document_id)
        if document is None or document["knowledge_base_id"] != knowledge_base_id:
            return

        try:
            # 删除文档相关的旧向量数据，以便后续重新索引时不会有冲突
            delete_document_vectors(
                knowledge_base_id=knowledge_base_id,
                document_id=document_id,
            )
            # 验证上传的文件是否存在于存储路径中，如果文件丢失则抛出解析错误
            path = Path(document["storage_path"])
            if not path.exists():
                raise DocumentParseError("Uploaded file is missing from storage")

            # 解析文档内容并分块，如果解析失败或者无法生成任何分块，则抛出解析错误
            extracted = parse_document(path, document["filename"])
            chunks = chunk_document(extracted)
            if not chunks:
                raise DocumentParseError("No chunks could be created from document text")

            # 将新的分块数据保存到数据库中，并更新文档的解析状态为parsed，索引状态为pending，错误信息清空
            ChunkRepository(connection).replace_for_document(
                knowledge_base_id=knowledge_base_id,
                document_id=document_id,
                chunks=chunks,
            )

            # 更新文档的解析状态为parsed，索引状态为pending，错误信息清空，以便前端可以知道文档已经解析完成并且准备好进行索引了
            document_repository.update_parse_and_index_status(
                document_id,
                parse_status="parsed",
                index_status="pending",
                error_message=None,
            )
        except (DocumentParseError, IndexingError) as exc:
            document_repository.update_parse_status(
                document_id,
                parse_status="failed",
                error_message=str(exc),
            )

# 运行文档索引任务，从数据库中获取文档信息和分块数据，删除旧的向量数据，索引新的分块数据，
# 然后更新文档的索引状态为indexed，如果索引过程中发生错误则更新索引状态为failed并保存错误信息
def _run_index_document_task(knowledge_base_id: str, document_id: str) -> None:
    with connection_scope() as connection:
        document_repository = DocumentRepository(connection)
        chunk_repository = ChunkRepository(connection)
        document = document_repository.get(document_id)
        if document is None or document["knowledge_base_id"] != knowledge_base_id:
            return

        chunks = chunk_repository.list_for_document(document_id)
        try:
            delete_document_vectors(
                knowledge_base_id=knowledge_base_id,
                document_id=document_id,
            )
            result = index_document_chunks(
                knowledge_base_id=knowledge_base_id,
                document=document,
                chunks=chunks,
            )
            chunk_repository.set_vector_ids(result.vector_ids_by_chunk_id)
            document_repository.update_index_status(
                document_id,
                index_status="indexed",
                error_message=None,
            )
            # 重建关键词索引
            try:
                rebuild_keyword_index(
                    knowledge_base_id=knowledge_base_id,
                    chunks=chunk_repository.list_for_knowledge_base(knowledge_base_id),
                )
            except Exception:
                logging.getLogger(__name__).warning(
                    "Failed to rebuild keyword index for kb %s", knowledge_base_id
                )
        except IndexingError as exc:
            document_repository.update_index_status(
                document_id,
                index_status="failed",
                error_message=str(exc),
            )


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


@router.get(
    "/{knowledge_base_id}/documents",
    response_model=PaginatedResponse[DocumentRead],
)
def list_documents(
    knowledge_base_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    with connection_scope() as connection:
        knowledge_base = KnowledgeBaseRepository(connection).get(knowledge_base_id)
        if knowledge_base is None:
            raise HTTPException(status_code=404, detail="Knowledge base not found")
        repo = DocumentRepository(connection)
        items = repo.list_for_knowledge_base(knowledge_base_id, limit=limit, offset=offset)
        total = repo.count_for_knowledge_base(knowledge_base_id)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


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
        document_repository = DocumentRepository(connection)
        existing = document_repository.get(document_id)
        if existing is None or existing["knowledge_base_id"] != knowledge_base_id:
            raise HTTPException(status_code=404, detail="Document not found")

        try:
            delete_document_vectors(
                knowledge_base_id=knowledge_base_id,
                document_id=document_id,
            )
        except IndexingError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        # 清除 BM25 缓存
        from ..services.indexing import _collection_name
        from ..services.keyword_search import keyword_engine

        keyword_engine.invalidate(_collection_name(knowledge_base_id))

        deleted = document_repository.delete(knowledge_base_id, document_id)
        if deleted is None:
            raise HTTPException(status_code=404, detail="Document not found")

    storage_path = Path(deleted["storage_path"])
    if storage_path.exists():
        storage_path.unlink()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{knowledge_base_id}/documents/{document_id}/parse",
    response_model=DocumentRead,
)
def parse_uploaded_document(
    knowledge_base_id: str,
    document_id: str,
) -> dict:
    with connection_scope() as connection:
        document_repository = DocumentRepository(connection)
        document = document_repository.get(document_id)
        if document is None or document["knowledge_base_id"] != knowledge_base_id:
            raise HTTPException(status_code=404, detail="Document not found")

        updated = document_repository.update_parse_and_index_status(
            document_id,
            parse_status="running",
            index_status="pending",
            error_message=None,
        )
    task_queue.enqueue(
        TASK_PARSE,
        knowledge_base_id=knowledge_base_id,
        document_id=document_id,
    )
    return updated


@router.post(
    "/{knowledge_base_id}/documents/parse-pending",
    response_model=BatchTaskResponse,
)
def parse_pending_documents(
    knowledge_base_id: str,
) -> dict:
    with connection_scope() as connection:
        knowledge_base = KnowledgeBaseRepository(connection).get(knowledge_base_id)
        if knowledge_base is None:
            raise HTTPException(status_code=404, detail="Knowledge base not found")

        document_repository = DocumentRepository(connection)
        documents = document_repository.list_pending_parse(knowledge_base_id)
        for document in documents:
            document_repository.update_parse_and_index_status(
                document["id"],
                parse_status="running",
                index_status="pending",
                error_message=None,
            )

    for document in documents:
        task_queue.enqueue(
            TASK_PARSE,
            knowledge_base_id=knowledge_base_id,
            document_id=document["id"],
        )

    return {
        "scheduled": len(documents),
        "document_ids": [document["id"] for document in documents],
    }


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
def index_uploaded_document(
    knowledge_base_id: str,
    document_id: str,
) -> dict:
    with connection_scope() as connection:
        document_repository = DocumentRepository(connection)

        document = document_repository.get(document_id)
        if document is None or document["knowledge_base_id"] != knowledge_base_id:
            raise HTTPException(status_code=404, detail="Document not found")

        document = document_repository.update_index_status(
            document_id,
            index_status="running",
            error_message=None,
        )
    task_queue.enqueue(
        TASK_INDEX,
        knowledge_base_id=knowledge_base_id,
        document_id=document_id,
    )
    return document


@router.post(
    "/{knowledge_base_id}/documents/index-pending",
    response_model=BatchTaskResponse,
)
def index_pending_documents(
    knowledge_base_id: str,
) -> dict:
    with connection_scope() as connection:
        knowledge_base = KnowledgeBaseRepository(connection).get(knowledge_base_id)
        if knowledge_base is None:
            raise HTTPException(status_code=404, detail="Knowledge base not found")

        document_repository = DocumentRepository(connection)
        documents = document_repository.list_pending_index(knowledge_base_id)
        for document in documents:
            document_repository.update_index_status(
                document["id"],
                index_status="running",
                error_message=None,
            )

    for document in documents:
        task_queue.enqueue(
            TASK_INDEX,
            knowledge_base_id=knowledge_base_id,
            document_id=document["id"],
        )

    return {
        "scheduled": len(documents),
        "document_ids": [document["id"] for document in documents],
    }


@router.post(
    "/{knowledge_base_id}/documents/reindex-all",
    response_model=BatchTaskResponse,
)
def reindex_all_documents(
    knowledge_base_id: str,
) -> dict:
    with connection_scope() as connection:
        knowledge_base = KnowledgeBaseRepository(connection).get(knowledge_base_id)
        if knowledge_base is None:
            raise HTTPException(status_code=404, detail="Knowledge base not found")

        document_repository = DocumentRepository(connection)
        documents = document_repository.list_parsed(knowledge_base_id)
        for document in documents:
            document_repository.update_index_status(
                document["id"],
                index_status="running",
                error_message=None,
            )

    for document in documents:
        task_queue.enqueue(
            TASK_INDEX,
            knowledge_base_id=knowledge_base_id,
            document_id=document["id"],
        )

    return {
        "scheduled": len(documents),
        "document_ids": [document["id"] for document in documents],
    }


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
            conversation_history=[
                {"role": m.role, "content": m.content}
                for m in payload.conversation_history
            ],
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


@router.post("/{knowledge_base_id}/questions/stream")
def answer_from_knowledge_base_stream(
    knowledge_base_id: str,
    payload: QuestionRequest,
) -> StreamingResponse:
    with connection_scope() as connection:
        knowledge_base = KnowledgeBaseRepository(connection).get(knowledge_base_id)
        if knowledge_base is None:
            raise HTTPException(status_code=404, detail="Knowledge base not found")

    try:
        sources, tokens = answer_question_stream(
            knowledge_base_id=knowledge_base_id,
            question=payload.question,
            top_k=payload.top_k,
            conversation_history=[
                {"role": m.role, "content": m.content}
                for m in payload.conversation_history
            ],
        )
    except AnsweringError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    sources_data = [_source_to_dict(source) for source in sources]

    def sse_events():
        # 先发送来源信息
        yield f"data: {json.dumps({'type': 'sources', 'sources': sources_data}, ensure_ascii=False)}\n\n"
        # 逐 token 发送
        full_answer_parts: list[str] = []
        try:
            for token in tokens:
                full_answer_parts.append(token)
                yield f"data: {json.dumps({'type': 'token', 'content': token}, ensure_ascii=False)}\n\n"
        except Exception:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Stream interrupted'})}\n\n"
            return

        full_answer = "".join(full_answer_parts)
        answer_id = ""
        # 保存到问答历史
        try:
            with connection_scope() as connection:
                created = QuestionAnswerRepository(connection).create(
                    knowledge_base_id=knowledge_base_id,
                    question=payload.question,
                    answer=full_answer,
                    sources=sources_data,
                    top_k=payload.top_k,
                )
                answer_id = created["id"]
        except Exception:
            logging.getLogger(__name__).exception("Failed to persist streamed answer")

        yield f"data: {json.dumps({'type': 'done', 'answer_id': answer_id})}\n\n"

    return StreamingResponse(
        sse_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/{knowledge_base_id}/question-answers",
    response_model=PaginatedResponse[QuestionAnswerRead],
)
def list_question_answers(
    knowledge_base_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict:
    with connection_scope() as connection:
        knowledge_base = KnowledgeBaseRepository(connection).get(knowledge_base_id)
        if knowledge_base is None:
            raise HTTPException(status_code=404, detail="Knowledge base not found")
        repo = QuestionAnswerRepository(connection)
        items = repo.list_for_knowledge_base(knowledge_base_id, limit=limit, offset=offset)
        total = repo.count_for_knowledge_base(knowledge_base_id)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.patch(
    "/{knowledge_base_id}/question-answers/{answer_id}/rating",
    response_model=QuestionAnswerRead,
)
def rate_question_answer(
    knowledge_base_id: str,
    answer_id: str,
    payload: RatingUpdate,
) -> dict:
    with connection_scope() as connection:
        knowledge_base = KnowledgeBaseRepository(connection).get(knowledge_base_id)
        if knowledge_base is None:
            raise HTTPException(status_code=404, detail="Knowledge base not found")
        updated = QuestionAnswerRepository(connection).update_rating(
            answer_id, payload.rating
        )
    if updated is None:
        raise HTTPException(status_code=404, detail="Question answer not found")
    return updated


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
