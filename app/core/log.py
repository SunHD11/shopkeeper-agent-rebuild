"""Configure Loguru once for consistent console and file output."""

import sys
from pathlib import Path
from typing import Any

from loguru import logger as base_logger

from app.conf.app_config import PROJECT_ROOT, LoggingConfig, app_config
from app.core.context import request_id_ctx_var

LOG_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<magenta>request_id={extra[request_id]}</magenta> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)


def _inject_request_id(record: dict[str, Any]) -> None:
    """Attach the current request ID without leaking configuration secrets."""

    record["extra"]["request_id"] = request_id_ctx_var.get()


def configure_logger(config: LoggingConfig):
    """Replace default sinks and return the project's patched logger."""

    base_logger.remove()
    configured_logger = base_logger.patch(_inject_request_id)

    if config.console.enable:
        configured_logger.add(
            sink=sys.stdout,
            level=config.console.level,
            format=LOG_FORMAT,
        )

    if config.file.enable:
        log_dir = Path(config.file.path)
        if not log_dir.is_absolute():
            log_dir = PROJECT_ROOT / log_dir
        log_dir.mkdir(parents=True, exist_ok=True)
        configured_logger.add(
            sink=log_dir / "app.log",
            level=config.file.level,
            format=LOG_FORMAT,
            rotation=config.file.rotation,
            retention=config.file.retention,
            encoding="utf-8",
        )

    return configured_logger


logger = configure_logger(app_config.logging)
