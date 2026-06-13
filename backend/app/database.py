from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from sqlite3 import Connection
import sqlite3

from .config import get_settings


def _database_path() -> Path:
    database_url = get_settings().database_url
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError("Only sqlite:/// DATABASE_URL values are supported in the MVP")
    return Path(database_url.removeprefix(prefix))


def connect() -> Connection:
    path = _database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


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


def init_db() -> None:
    with connection_scope() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS knowledge_bases (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_knowledge_bases_created_at
            ON knowledge_bases(created_at);

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
            """
        )
