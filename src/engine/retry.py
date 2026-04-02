"""智能重试策略 — 指数退避 + 抖动。"""

from __future__ import annotations

import asyncio
import random
import time
from typing import Awaitable, Callable

import aiohttp
from loguru import logger

from src.api.models import BookingResponse
from src.context import BookingResult, BookingTarget

# 仅当服务器消息包含以下关键词时，才认定场地真正不可预约（标记为死目标）
_VENUE_DEAD_KEYWORDS = ("不可预约", "已被预约", "已满", "不可用", "已过期", "已关闭", "已结束")


def _is_venue_unavailable(message: str) -> bool:
    """判断服务器返回的错误消息是否表示场地真正不可预约。"""
    return any(kw in message for kw in _VENUE_DEAD_KEYWORDS)


class RetryPolicy:
    """
    可配置的重试策略。

    退避公式: delay = min(base * 2^attempt + jitter, max)
    抖动防止多实例同时重试造成的雷群效应。
    """

    def __init__(
        self,
        max_retries: int = 3,
        backoff_base_ms: int = 100,
        backoff_max_ms: int = 2000,
        retryable_status_codes: set[int] | None = None,
    ) -> None:
        self.max_retries = max_retries
        self.backoff_base_ms = backoff_base_ms
        self.backoff_max_ms = backoff_max_ms
        self.retryable_status_codes = retryable_status_codes or {502, 503, 429}

    def _compute_delay(self, attempt: int) -> float:
        """计算第 N 次重试的退避延迟（秒）。"""
        base_delay = self.backoff_base_ms * (2 ** attempt)
        jitter = random.uniform(0, self.backoff_base_ms)
        delay_ms = min(base_delay + jitter, self.backoff_max_ms)
        return delay_ms / 1000

    async def execute(
        self,
        func: Callable[[], Awaitable[BookingResponse]],
        target: BookingTarget,
    ) -> BookingResult:
        """
        带重试地执行异步函数。

        重试条件:
        - HTTP 状态码在 retryable_status_codes 中 (502, 503, 429)
        - 网络错误 (aiohttp.ClientError)
        - 超时 (asyncio.TimeoutError)

        不重试:
        - 401 (认证失败，由上层处理)
        - 成功响应
        - 业务层失败（如"场地已被预约"）
        """
        last_error: str | None = None

        for attempt in range(self.max_retries + 1):
            start = time.perf_counter()
            try:
                response = await func()
                elapsed_ms = (time.perf_counter() - start) * 1000

                # 成功
                if response.success:
                    return BookingResult(
                        success=True,
                        target=target,
                        response_data=response.raw_data,
                        attempt_number=attempt + 1,
                        latency_ms=elapsed_ms,
                        order_id=getattr(response, "order_id", None),
                    )

                # 可重试的 HTTP 状态码
                if response.status_code in self.retryable_status_codes:
                    last_error = f"HTTP {response.status_code}: {response.message}"
                    if attempt < self.max_retries:
                        delay = self._compute_delay(attempt)
                        logger.warning(
                            "重试 {}/{} [场地={} 时段={}] {} (等待 {:.0f}ms)",
                            attempt + 1,
                            self.max_retries,
                            target.court_id,
                            target.time_slot,
                            last_error,
                            delay * 1000,
                        )
                        await asyncio.sleep(delay)
                        continue

                # 业务失败判定：仅当消息明确表示场地不可预约时才标记为死目标
                # "访问过于频繁" 等限频错误不标死，下轮可重试
                return BookingResult(
                    success=False,
                    target=target,
                    response_data=response.raw_data,
                    error=response.message,
                    attempt_number=attempt + 1,
                    latency_ms=elapsed_ms,
                    is_business_failure=_is_venue_unavailable(response.message),
                )

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                elapsed_ms = (time.perf_counter() - start) * 1000
                last_error = f"{type(e).__name__}: {e}"

                if attempt < self.max_retries:
                    delay = self._compute_delay(attempt)
                    logger.warning(
                        "重试 {}/{} [场地={} 时段={}] {} (等待 {:.0f}ms)",
                        attempt + 1,
                        self.max_retries,
                        target.court_id,
                        target.time_slot,
                        last_error,
                        delay * 1000,
                    )
                    await asyncio.sleep(delay)
                    continue

                return BookingResult(
                    success=False,
                    target=target,
                    error=last_error,
                    attempt_number=attempt + 1,
                    latency_ms=elapsed_ms,
                )

        # 理论上不会到达这里
        return BookingResult(
            success=False,
            target=target,
            error=last_error or "重试次数耗尽",
            attempt_number=self.max_retries + 1,
            latency_ms=0,
        )
