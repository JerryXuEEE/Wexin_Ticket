"""抢票引擎 — 多轮并发抢票核心编排器。"""

from __future__ import annotations

import asyncio
import time

from loguru import logger

from src.api.base_client import VenueAPIProtocol
from src.auth.manager import AuthManager
from src.context import BookingContext, BookingResult, BookingTarget
from src.engine.retry import RetryPolicy
from src.notify.base import NotifierChain


class BookingEngine:
    """
    核心抢票引擎。

    执行流程:
    1. 多轮抢票（attempt_rounds 轮）
    2. 每轮并发发出 concurrency 个请求（Semaphore 控制）
    3. 首个成功通过 Event 通知取消其余任务
    4. 所有轮次结束后发送通知
    """

    def __init__(
        self,
        api_client: VenueAPIProtocol,
        auth: AuthManager,
        retry_policy: RetryPolicy,
        notifier: NotifierChain,
        engine_config: dict,
    ) -> None:
        self.api = api_client
        self.auth = auth
        self.retry = retry_policy
        self.notifier = notifier
        self.concurrency = engine_config.get("concurrency", 8)
        self.attempt_rounds = engine_config.get("attempt_rounds", 3)
        self.round_delay_ms = engine_config.get("round_delay_ms", 200)

    async def run(self, context: BookingContext) -> list[BookingResult]:
        """执行完整的抢票流程。"""
        all_results: list[BookingResult] = []
        success_event = asyncio.Event()
        semaphore = asyncio.Semaphore(self.concurrency)
        start_time = time.perf_counter()

        targets = sorted(context.targets, key=lambda t: t.priority)
        logger.info("抢票引擎启动: {} 个目标, {} 轮 × {} 并发", len(targets), self.attempt_rounds, self.concurrency)

        for round_num in range(1, self.attempt_rounds + 1):
            if success_event.is_set():
                logger.info("已成功，跳过第 {} 轮", round_num)
                break

            logger.info("--- 第 {} / {} 轮 ---", round_num, self.attempt_rounds)

            tasks = [
                asyncio.create_task(
                    self._attempt_booking(target, semaphore, success_event, context.dry_run)
                )
                for target in targets
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    logger.error("任务异常: {}", result)
                elif isinstance(result, BookingResult):
                    all_results.append(result)
                    if result.success:
                        success_event.set()

            # 轮间等待
            if round_num < self.attempt_rounds and not success_event.is_set():
                await asyncio.sleep(self.round_delay_ms / 1000)

        total_ms = (time.perf_counter() - start_time) * 1000
        successes = [r for r in all_results if r.success]
        logger.info("抢票完成: 总耗时={:.0f}ms, 成功={}, 失败={}", total_ms, len(successes), len(all_results) - len(successes))

        # 发送通知
        await self._send_notification(all_results, total_ms)

        return all_results

    async def _attempt_booking(
        self,
        target: BookingTarget,
        semaphore: asyncio.Semaphore,
        success_event: asyncio.Event,
        dry_run: bool = False,
    ) -> BookingResult:
        """单个目标的抢票尝试（带信号量和成功信号）。"""
        async with semaphore:
            if success_event.is_set():
                return BookingResult(
                    success=False,
                    target=target,
                    error="已有其他任务成功，跳过",
                )

            if dry_run:
                logger.info("[DRY-RUN] 模拟预约: 场地={} 时段={}", target.court_id, target.time_slot)
                return BookingResult(
                    success=True,
                    target=target,
                    response_data={"dry_run": True},
                    latency_ms=0,
                )

            result = await self.retry.execute(
                func=lambda t=target: self.api.submit_booking(t),
                target=target,
            )
            return result

    async def _send_notification(self, results: list[BookingResult], total_ms: float) -> None:
        """根据结果发送通知。"""
        successes = [r for r in results if r.success]

        if successes:
            title = f"抢票成功！({len(successes)} 个场地)"
            lines = [f"总耗时: {total_ms:.0f}ms", ""]
            for r in successes:
                lines.append(
                    f"- {r.target.court_name} | {r.target.time_slot} | "
                    f"{r.target.date} | 订单={r.order_id} | {r.latency_ms:.0f}ms"
                )
            body = "\n".join(lines)
            await self.notifier.notify_all(title, body, level="success")
        else:
            title = "抢票失败"
            errors = set()
            for r in results:
                if r.error:
                    errors.add(r.error)
            body = f"总尝试: {len(results)} 次\n总耗时: {total_ms:.0f}ms\n错误: {'; '.join(errors) if errors else '未知'}"
            await self.notifier.notify_all(title, body, level="error")
