# 数据库管理模块

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from sqlite3 import Connection
import sqlite3

from .config import get_settings


# _database_path函数用于获取数据库文件的路径，解析DATABASE_URL环境变量，并确保它是一个SQLite URL。
def _database_path() -> Path:
    database_url = get_settings().database_url
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError("Only sqlite:/// DATABASE_URL values are supported in the MVP")
    return Path(database_url.removeprefix(prefix))

# connect函数用于连接到SQLite数据库，确保数据库文件所在的目录存在，并启用外键支持。
def connect() -> Connection:
    path = _database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection

# connection_scope函数是一个上下文管理器，用于管理数据库连接的生命周期，确保在使用完连接后正确提交或回滚事务，并关闭连接。
@contextmanager
def connection_scope() -> Generator[Connection, None, None]:
    connection = connect()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


# init_db函数用于初始化数据库，创建knowledge_bases、documents和chunks表，并为它们创建必要的索引，以支持知识库、文档和文本块的存储和查询。
def init_db() -> None:
    with connection_scope() as connection:
        connection.executescript(
            """
            -- 创建knowledge_bases表，用于存储知识库信息，包括名称、描述和创建/更新时间等，并为created_at列创建索引，以加速按创建时间查询
            CREATE TABLE IF NOT EXISTS knowledge_bases (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_knowledge_bases_created_at
            ON knowledge_bases(created_at);

            -- 创建documents表，用于存储上传的文档信息，包括文件名、内容类型、存储路径、解析状态、索引状态和错误信息等，并为knowledge_base_id和created_at列创建索引，以加速相关查询
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                knowledge_base_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                content_type TEXT NOT NULL,
                storage_path TEXT NOT NULL,
                parse_status TEXT NOT NULL,
                index_status TEXT NOT NULL,
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (knowledge_base_id)
                    REFERENCES knowledge_bases(id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_documents_knowledge_base_id
            ON documents(knowledge_base_id);

            CREATE INDEX IF NOT EXISTS idx_documents_created_at
            ON documents(created_at);

            -- 创建chunks表，用于存储文档分块信息，包括文本内容、来源标签、页码、章节标题和向量ID等，并为knowledge_base_id和document_id列创建索引，以加速相关查询
            CREATE TABLE IF NOT EXISTS chunks (
                id TEXT PRIMARY KEY,
                knowledge_base_id TEXT NOT NULL,
                document_id TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                text TEXT NOT NULL,
                source_label TEXT NOT NULL,
                page_number INTEGER,
                section_title TEXT,
                vector_id TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (knowledge_base_id)
                    REFERENCES knowledge_bases(id)
                    ON DELETE CASCADE,
                FOREIGN KEY (document_id)
                    REFERENCES documents(id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_chunks_knowledge_base_id
            ON chunks(knowledge_base_id);

            CREATE INDEX IF NOT EXISTS idx_chunks_document_id
            ON chunks(document_id);

            CREATE TABLE IF NOT EXISTS question_answers (
                id TEXT PRIMARY KEY,
                knowledge_base_id TEXT NOT NULL,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                sources_json TEXT NOT NULL,
                top_k INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (knowledge_base_id)
                    REFERENCES knowledge_bases(id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_question_answers_knowledge_base_id
            ON question_answers(knowledge_base_id);

            CREATE INDEX IF NOT EXISTS idx_question_answers_created_at
            ON question_answers(created_at);
            """
        )
