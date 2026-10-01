"""日志：统一走 loguru，并把 stdlib logging（requests / urllib3）接过来。"""

import logging
import sys
from typing import TYPE_CHECKING

import loguru

if TYPE_CHECKING:
    from loguru import Logger, Record

logger: "Logger" = loguru.logger


class LoguruHandler(logging.Handler):
    """把 stdlib logging 的记录转发给 loguru。"""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = sys._getframe(6), 6
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def default_filter(record: "Record") -> bool:
    """按 `extra.log_level` 阈值过滤，未配置时为 INFO。"""
    log_level = record["extra"].get("log_level", "INFO")
    levelno = logger.level(log_level).no if isinstance(log_level, str) else log_level
    return record["level"].no >= levelno


DEFAULT_FORMAT = (
    "<g>{time:MM-DD HH:mm:ss}</g> [<lvl>{level}</lvl>] <c><u>{name}</u></c> | {message}"
)

logger.remove()
logger.add(
    sys.stderr,
    level=0,
    diagnose=False,
    filter=default_filter,
    format=DEFAULT_FORMAT,
)
logger.configure(extra={"log_level": "INFO"})


def set_level(level: str) -> None:
    """调整全局日志阈值，供 CLI 的 -v / -q 使用。"""
    logger.configure(extra={"log_level": level})
