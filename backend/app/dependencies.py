"""FastAPI 依赖工厂。

每个工厂返回进程级单例，供路由和服务层获取。
测试中可通过 get_keyword_engine().reset() / get_task_queue().reset() 隔离状态。
"""

from .services.keyword_search import KeywordSearchEngine, get_keyword_engine
from .task_queue import TaskQueue, task_queue as _task_queue


def get_kw_engine() -> KeywordSearchEngine:
    """返回进程级 KeywordSearchEngine 单例。"""
    return get_keyword_engine()


def get_tq() -> TaskQueue:
    """返回进程级 TaskQueue 单例。"""
    return _task_queue
