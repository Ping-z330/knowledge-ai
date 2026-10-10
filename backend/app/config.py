"""环境变量配置和加载。

使用 pydantic-settings 从环境变量和 .env 文件自动加载配置。
优先级：环境变量 > .env 文件 > 默认值；项目根 .env 优先于后端目录 .env。
"""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 定义项目目录和后端目录
BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent


# 默认数据库 URL，位于后端目录下的 data/knowledge_agent.db
def _default_database_url() -> str:
    return f"sqlite:///{BACKEND_DIR / 'data' / 'knowledge_agent.db'}"


# 默认存储目录，位于后端目录下的 data/uploads
def _default_storage_dir() -> Path:
    return BACKEND_DIR / "data" / "uploads"


# 默认 Chroma 目录，位于后端目录下的 data/chroma
def _default_chroma_dir() -> Path:
    return BACKEND_DIR / "data" / "chroma"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # 后端目录 .env 先加载，项目根 .env 后加载覆盖（项目根优先）
        env_file=(BACKEND_DIR / ".env", PROJECT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Knowledge Agent API"
    api_token: str = ""
    # Auth — single admin user, JWT-based UI auth
    admin_username: str = "admin"
    admin_password: str = ""
    jwt_secret: str = ""
    jwt_expire_hours: int = 24
    cors_origins: str = "*"
    log_json: bool = False
    database_url: str = _default_database_url()
    storage_dir: Path = _default_storage_dir()
    chroma_dir: Path = _default_chroma_dir()
    max_upload_bytes: int = 50 * 1024 * 1024
    embedding_batch_size: int = 20
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = ""
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    # Agentic RAG
    agentic_enabled: bool = True
    agentic_max_retrieval_rounds: int = 3
    agentic_web_search_provider: str = "duckduckgo"
    # Cross-encoder rerank
    cross_encoder_enabled: bool = False
    cross_encoder_provider: str = "siliconflow"  # "siliconflow" or "local"
    cross_encoder_model: str = "BAAI/bge-reranker-v2-m3"
    siliconflow_api_key: str = ""
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"
    # Rate limiting
    rate_limit_requests: int = 60
    rate_limit_window: float = 60.0

    @field_validator("storage_dir", "chroma_dir", mode="after")
    @classmethod
    def _resolve_relative_path(cls, v: Path) -> Path:
        """相对路径基于项目目录解析为绝对路径。"""
        if not v.is_absolute():
            return PROJECT_DIR / v
        return v


@lru_cache
def get_settings() -> Settings:
    """缓存 Settings 单例，避免重复加载环境变量。"""
    return Settings()
