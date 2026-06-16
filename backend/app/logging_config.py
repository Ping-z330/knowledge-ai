import logging

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"


def setup_logging(*, level: int = logging.INFO) -> None:
    logging.basicConfig(level=level, format=_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # 抑制过于吵闹的第三方库日志
    logging.getLogger("chromadb").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("sqlite3").setLevel(logging.WARNING)
