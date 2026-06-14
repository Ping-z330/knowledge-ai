# 环境变量配置和加载

from functools import lru_cache
from pathlib import Path
from dotenv import load_dotenv
from pydantic import BaseModel
import os

# 定义项目目录和后端目录
BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent

# 加载环境变量，优先级：项目根目录 > 后端目录
load_dotenv(PROJECT_DIR / ".env", override=False)
load_dotenv(BACKEND_DIR / ".env", override=False)


# 定义配置类
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


# 定义默认数据库URL、默认存储目录和默认Chroma目录的函数
def _default_database_url() -> str:
    return f"sqlite:///{BACKEND_DIR / 'data' / 'knowledge_agent.db'}"

# _default_storage_dir函数返回默认的存储目录路径，位于后端目录下的data/uploads文件夹中。
def _default_storage_dir() -> Path:
    return BACKEND_DIR / "data" / "uploads"


# _default_chroma_dir函数返回默认的Chroma目录路径，位于后端目录下的data/chroma文件夹中。
def _default_chroma_dir() -> Path:
    return BACKEND_DIR / "data" / "chroma"


# _env_path函数用于获取环境变量指定的路径，如果环境变量不存在或为空，则返回默认路径。
# 如果环境变量指定的路径是相对路径，则将其转换为绝对路径，基于项目目录。
def _env_path(name: str, default: Path) -> Path:
    value = os.getenv(name)
    if not value:
        return default

    path = Path(value)
    if path.is_absolute():
        return path
    return PROJECT_DIR / path


# get_settings函数使用lru_cache装饰器来缓存结果，避免重复加载环境变量和创建Settings实例
@lru_cache
def get_settings() -> Settings:
    return Settings(
        database_url=os.getenv("DATABASE_URL", _default_database_url()),
        storage_dir=_env_path("STORAGE_DIR", _default_storage_dir()),
        chroma_dir=_env_path("CHROMA_DIR", _default_chroma_dir()),
        embedding_base_url=os.getenv("EMBEDDING_BASE_URL", ""),
        embedding_api_key=os.getenv("EMBEDDING_API_KEY", ""),
        embedding_model=os.getenv("EMBEDDING_MODEL", ""),
        llm_base_url=os.getenv("LLM_BASE_URL", ""),
        llm_api_key=os.getenv("LLM_API_KEY", ""),
        llm_model=os.getenv("LLM_MODEL", ""),
    )
