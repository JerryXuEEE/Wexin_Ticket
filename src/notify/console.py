"""控制台通知 — 基于 loguru。"""

from __future__ import annotations

from loguru import logger


class ConsoleNotifier:
    """将通知输出到控制台日志。"""

    async def send(self, title: str, body: str, level: str = "info") -> bool:
        """通过 loguru 输出通知。"""
        log_func = {
            "success": logger.success,
            "error": logger.error,
            "warning": logger.warning,
        }.get(level, logger.info)

        log_func("📢 {}", title)
        for line in body.strip().splitlines():
            log_func("   {}", line)

        return True
