import logging

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"

# setup_logging函数配置了日志记录的基本设置，包括日志级别、日志格式和日期格式。它还将一些第三方库的日志级别设置为WARNING，以减少不必要的日志输出。
def setup_logging(*, level: int = logging.INFO) -> None:
    logging.basicConfig(level=level, format=_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # 抑制过于吵闹的第三方库日志
    logging.getLogger("chromadb").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("sqlite3").setLevel(logging.WARNING)
