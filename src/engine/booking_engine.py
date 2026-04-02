"""抢票引擎 — 按时间段分轮抢票核心编排器。"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict

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
    1. 按时间段优先级遍历
    2. 每个时段内并发抢所有场地，失败后等 round_delay_ms 重试同一时段
    3. 仅"不可预约"等明确消息标记死目标，限频不标死
    4. 首个成功即停止所有后续尝试
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
        self.book_all_slots = engine_config.get("book_all_slots", False)
        fallback_cfg = engine_config.get("smart_fallback", {})
        self.fallback_enabled = fallback_cfg.get("enabled", False)

    @staticmethod
    def _group_by_time_slot(targets: list[BookingTarget]) -> OrderedDict[str, list[BookingTarget]]:
        """按时间段分组，保持优先级顺序。"""
        groups: OrderedDict[str, list[BookingTarget]] = OrderedDict()
        for t in sorted(targets, key=lambda x: x.priority):
            groups.setdefault(t.time_slot, []).append(t)
        return groups

    async def run(self, context: BookingContext) -> list[BookingResult]:
        """
        执行完整的抢票流程。

        策略：按时间段优先级遍历，每个时段内并发抢所有场地，
        失败则等 round_delay_ms 后重试同一时段（排除死目标），
        每时段最多 attempt_rounds 轮，成功即停。
        """
        all_results: list[BookingResult] = []
        success_event = asyncio.Event()
        semaphore = asyncio.Semaphore(self.concurrency)
        start_time = time.perf_counter()

        slot_groups = self._group_by_time_slot(context.targets)

        logger.info(
            "抢票引擎启动: {} 个目标, {} 个时间段, 每时段最多 {} 轮, 并发={}",
            len(context.targets), len(slot_groups), self.attempt_rounds, self.concurrency,
        )

        dead_targets: set[tuple[int, str]] = set()

        first_slot = True
        for time_slot, group_targets in slot_groups.items():
            if success_event.is_set() and not self.book_all_slots:
                logger.info("已成功，跳过时段 {}", time_slot)
                break

            # 全时段模式：每个时段独立，重置成功状态
            if self.book_all_slots:
                success_event.clear()

            # 时段间等待（从第二个时段开始）
            if not first_slot:
                logger.debug("时段间等待 {}ms", self.round_delay_ms)
                await asyncio.sleep(self.round_delay_ms / 1000)
            first_slot = False

            logger.info("=== 开始抢时段: {} ({} 个场地) ===", time_slot, len(group_targets))

            for round_num in range(1, self.attempt_rounds + 1):
                if success_event.is_set():
                    break

                # 过滤死目标
                live_targets = [
                    t for t in group_targets
                    if (t.court_id, t.time_slot) not in dead_targets
                ]

                if not live_targets:
                    logger.warning("时段 {} 第 {} 轮: 所有场地已标死，跳过", time_slot, round_num)
                    break

                logger.info(
                    "--- 时段 {} 第 {} / {} 轮 ({} 个场地并发) ---",
                    time_slot, round_num, self.attempt_rounds, len(live_targets),
                )

                # 并发发出所有请求
                tasks = [
                    asyncio.create_task(
                        self._attempt_booking(target, semaphore, success_event, context.dry_run)
                    )
                    for target in live_targets
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                for result in results:
                    if isinstance(result, Exception):
                        logger.error("任务异常: {}", result)
                    elif isinstance(result, BookingResult):
                        all_results.append(result)
                        if result.success:
                            success_event.set()
                        elif result.is_business_failure:
                            dead_key = (result.target.court_id, result.target.time_slot)
                            if dead_key not in dead_targets:
                                dead_targets.add(dead_key)
                                logger.info(
                                    "标记死目标: {} {} ({})",
                                    result.target.court_name,
                                    result.target.time_slot,
                                    result.error,
                                )

                # 轮间等待（同一时段的下一轮重试前）
                if not success_event.is_set() and round_num < self.attempt_rounds:
                    logger.debug("轮间等待 {}ms", self.round_delay_ms)
                    await asyncio.sleep(self.round_delay_ms / 1000)

        total_ms = (time.perf_counter() - start_time) * 1000
        successes = [r for r in all_results if r.success]
        logger.info("抢票完成: 总耗时={:.0f}ms, 成功={}, 失败={}", total_ms, len(successes), len(all_results) - len(successes))

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
                success_event.set()
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
            if result.success:
                success_event.set()
            return result

    async def _discover_fallbacks(
        self,
        original_targets: list[BookingTarget],
        dead_targets: set[tuple[int, str]],
    ) -> list[BookingTarget]:
        """查询 API 发现同时段其他可用场地作为降级目标。"""
        if not original_targets:
            return []

        template = original_targets[0]
        time_slots = {t.time_slot for t in original_targets}
        preferred_court_ids = {t.court_id for t in original_targets}
        seen_dates = {t.date for t in original_targets}
        max_priority = max((t.priority for t in original_targets), default=0)

        fallbacks: list[BookingTarget] = []
        priority = max_priority + 1

        for date in seen_dates:
            try:
                slots = await self.api.query_available_slots(
                    date=date,
                    venue_id=template.venue_id,
                    venuetype_id=template.venuetype_id,
                )
            except Exception as e:
                logger.warning("查询可用场地失败: {}", e)
                continue

            for slot in slots:
                if slot.set_time not in time_slots:
                    continue
                if not slot.available:
                    continue
                if (slot.site_id, slot.set_time) in dead_targets:
                    continue
                if slot.site_id in preferred_court_ids:
                    continue

                fallbacks.append(BookingTarget(
                    date=slot.set_date,
                    time_slot=slot.set_time,
                    court_id=slot.site_id,
                    court_name=slot.site_name,
                    venue_id=template.venue_id,
                    venue_name=template.venue_name,
                    venuetype_id=template.venuetype_id,
                    venuetype_name=template.venuetype_name,
                    price=slot.price,
                    priority=priority,
                ))
                priority += 1

        logger.info("发现 {} 个替代场地", len(fallbacks))
        for fb in fallbacks:
            logger.debug("  替代: {} {} (P{})", fb.court_name, fb.time_slot, fb.priority)

        return fallbacks

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
