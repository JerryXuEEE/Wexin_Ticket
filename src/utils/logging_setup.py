"""日志配置 — 基于 loguru。"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger


def setup_logging(config: dict) -> None:
    """根据配置初始化 loguru logger。"""
    logger.remove()

    level = config.get("level", "DEBUG").upper()
    log_file = config.get("log_file", "logs/ticket.log")
    rotation = config.get("rotation", "10 MB")

    # 控制台输出
    logger.add(
        sys.stderr,
        level=level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    # 文件输出
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger.add(
        str(log_path),
        level=level,
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
            "{level: <8} | "
            "{name}:{function}:{line} | "
            "{message}"
        ),
        rotation=rotation,
        encoding="utf-8",
    )

    logger.info("日志系统初始化完成 (level={}, file={})", level, log_file)
