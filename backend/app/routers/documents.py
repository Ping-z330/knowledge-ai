"""文档上传、列表、删除、解析、索引相关端点和后台任务处理器。"""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status

from ..auth import require_api_token
from ..database import connection_scope
from ..dependencies import get_tq
from ..repositories.chunks import ChunkRepository
from ..repositories.documents import DocumentRepository
from ..repositories.knowledge_bases import KnowledgeBaseRepository
from ..schemas import BatchTaskResponse, ChunkRead, DocumentRead, PaginatedResponse
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
    invalidate_keyword_index,
    rebuild_keyword_index,
)
from ..task_queue import TASK_INDEX, TASK_PARSE

router = APIRouter(
    prefix="/api/knowledge-bases",
    tags=["documents"],
    dependencies=[Depends(require_api_token)],
)

# ── 后台任务处理器 ──────────────────────────────────────────────


def _run_parse_document_task(knowledge_base_id: str, document_id: str) -> None:
    """解析文档 + 分块 + 写库。由任务队列 worker 调用。"""
    with connection_scope() as connection:
        document_repository = DocumentRepository(connection)
        document = document_repository.get(document_id)
        if document is None or document["knowledge_base_id"] != knowledge_base_id:
            return

        try:
            delete_document_vectors(
                knowledge_base_id=knowledge_base_id,
                document_id=document_id,
            )
            path = Path(document["storage_path"])
            if not path.exists():
                raise DocumentParseError("Uploaded file is missing from storage")

            extracted = parse_document(path, document["filename"])
            chunks = chunk_document(extracted)
            if not chunks:
                raise DocumentParseError("No chunks could be created from document text")

            ChunkRepository(connection).replace_for_document(
                knowledge_base_id=knowledge_base_id,
                document_id=document_id,
                chunks=chunks,
            )
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


def _run_index_document_task(knowledge_base_id: str, document_id: str) -> None:
    """索引文档的全部 chunks 到向量库和 BM25。由任务队列 worker 调用。"""
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


# ── 端点 ────────────────────────────────────────────────────────


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
        if KnowledgeBaseRepository(connection).get(knowledge_base_id) is None:
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
        if KnowledgeBaseRepository(connection).get(knowledge_base_id) is None:
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

        invalidate_keyword_index(knowledge_base_id=knowledge_base_id)

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
    get_tq().enqueue(
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
        if KnowledgeBaseRepository(connection).get(knowledge_base_id) is None:
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

    tq = get_tq()
    for document in documents:
        tq.enqueue(
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
    get_tq().enqueue(
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
        if KnowledgeBaseRepository(connection).get(knowledge_base_id) is None:
            raise HTTPException(status_code=404, detail="Knowledge base not found")

        document_repository = DocumentRepository(connection)
        documents = document_repository.list_pending_index(knowledge_base_id)
        for document in documents:
            document_repository.update_index_status(
                document["id"],
                index_status="running",
                error_message=None,
            )

    tq = get_tq()
    for document in documents:
        tq.enqueue(
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
        if KnowledgeBaseRepository(connection).get(knowledge_base_id) is None:
            raise HTTPException(status_code=404, detail="Knowledge base not found")

        document_repository = DocumentRepository(connection)
        documents = document_repository.list_parsed(knowledge_base_id)
        for document in documents:
            document_repository.update_index_status(
                document["id"],
                index_status="running",
                error_message=None,
            )

    tq = get_tq()
    for document in documents:
        tq.enqueue(
            TASK_INDEX,
            knowledge_base_id=knowledge_base_id,
            document_id=document["id"],
        )

    return {
        "scheduled": len(documents),
        "document_ids": [document["id"] for document in documents],
    }
