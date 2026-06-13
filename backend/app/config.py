from functools import lru_cache
from pathlib import Path
from pydantic import BaseModel
import os


class Settings(BaseModel):
    app_name: str = "Knowledge Agent API"
    database_url: str
    storage_dir: Path
    chroma_dir: Path
    embedding_base_url: str
    embedding_api_key: str
    embedding_model: str
    llm_base_url: str
    llm_api_key: str
    llm_model: str


def _default_database_url() -> str:
    backend_dir = Path(__file__).resolve().parents[1]
    return f"sqlite:///{backend_dir / 'data' / 'knowledge_agent.db'}"


def _default_storage_dir() -> Path:
    backend_dir = Path(__file__).resolve().parents[1]
    return backend_dir / "data" / "uploads"


def _default_chroma_dir() -> Path:
    backend_dir = Path(__file__).resolve().parents[1]
    return backend_dir / "data" / "chroma"


@lru_cache
def get_settings() -> Settings:
    return Settings(
        database_url=os.getenv("DATABASE_URL", _default_database_url()),
        storage_dir=Path(os.getenv("STORAGE_DIR", _default_storage_dir())),
        chroma_dir=Path(os.getenv("CHROMA_DIR", _default_chroma_dir())),
        embedding_base_url=os.getenv("EMBEDDING_BASE_URL", ""),
        embedding_api_key=os.getenv("EMBEDDING_API_KEY", ""),
        embedding_model=os.getenv("EMBEDDING_MODEL", ""),
        llm_base_url=os.getenv("LLM_BASE_URL", ""),
        llm_api_key=os.getenv("LLM_API_KEY", ""),
        llm_model=os.getenv("LLM_MODEL", ""),
    )
