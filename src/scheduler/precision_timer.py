"""精准定时器 — 三阶段等待策略实现毫秒级触发。"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta
from typing import Awaitable, Callable

from loguru import logger

from src.scheduler.ntp_sync import NTPSynchronizer


class PrecisionTimer:
    """
    高精度定时触发器。

    三阶段等待策略:
    1. T-∞ → T-2s:  asyncio.sleep(0.5) 粗等待（省 CPU）
    2. T-2s → T-10ms: asyncio.sleep(0.001) 细等待
    3. T-10ms → T:    time.perf_counter() 自旋（Windows sleep 精度仅 ~15ms）
    """

    def __init__(self, ntp: NTPSynchronizer, config: dict) -> None:
        self.ntp = ntp
        self.trigger_time_str: str = config["trigger_time"]  # "09:30:00.000"
        self.pre_connect_ms: int = config.get("pre_connect_ms", 1500)
        self.ntp_sync_interval: float = config.get("ntp_sync_interval_s", 300)

    def _compute_target_timestamp(self) -> float:
        """
        计算下一次触发的 Unix 时间戳。

        如果今天的触发时间已过，则瞄准明天。
        """
        parts = self.trigger_time_str.split(".")
        time_str = parts[0]
        ms = int(parts[1]) if len(parts) > 1 else 0

        now = datetime.now()
        h, m, s = map(int, time_str.split(":"))
        target = now.replace(hour=h, minute=m, second=s, microsecond=ms * 1000)

        # 如果目标时间已过（留 5 秒缓冲），瞄准明天
        if target.timestamp() - self.ntp.get_precise_time() < -5:
            target += timedelta(days=1)

        return target.timestamp()

    async def schedule_booking(
        self,
        trigger_callback: Callable[[], Awaitable[None]],
        pre_connect_callback: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        """
        等待到精确时间点，然后触发回调。

        流程:
        1. 启动 NTP 后台同步
        2. 在 T - pre_connect_ms 执行预连接回调
        3. 在 T 精确触发抢票回调
        """
        target_ts = self._compute_target_timestamp()
        target_dt = datetime.fromtimestamp(target_ts)
        logger.info("目标触发时间: {} ({})", target_dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3], self.trigger_time_str)

        now_ts = self.ntp.get_precise_time()
        wait_seconds = target_ts - now_ts
        logger.info("距离触发还有 {:.3f} 秒", wait_seconds)

        if wait_seconds < 0:
            logger.warning("目标时间已过 {:.3f}s，立即触发", abs(wait_seconds))
            await trigger_callback()
            return

        # 启动后台 NTP 同步
        ntp_task = asyncio.create_task(self.ntp.periodic_sync(self.ntp_sync_interval))

        try:
            pre_connect_done = False

            # ======== 阶段 1: 粗等待 (T-2s 之前) ========
            while True:
                now_ts = self.ntp.get_precise_time()
                remaining = target_ts - now_ts

                if remaining <= 2.0:
                    break

                # 预连接时机
                if not pre_connect_done and remaining <= self.pre_connect_ms / 1000 + 1.0:
                    if pre_connect_callback:
                        logger.info("阶段 0: 执行预连接 (T-{:.3f}s)", remaining)
                        await pre_connect_callback()
                    pre_connect_done = True

                sleep_time = min(0.5, remaining - 2.0)
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

            # 确保预连接已执行
            if not pre_connect_done and pre_connect_callback:
                logger.info("执行预连接 (紧急)")
                await pre_connect_callback()

            logger.info("阶段 2: 细等待开始 (T-{:.3f}s)", target_ts - self.ntp.get_precise_time())

            # ======== 阶段 2: 细等待 (T-2s → T-10ms) ========
            while True:
                now_ts = self.ntp.get_precise_time()
                remaining = target_ts - now_ts
                if remaining <= 0.01:  # 10ms
                    break
                await asyncio.sleep(0.001)

            logger.debug("阶段 3: 自旋等待 (T-{:.6f}s)", target_ts - self.ntp.get_precise_time())

            # ======== 阶段 3: 自旋 busy-wait (最后 10ms) ========
            # 切换到 perf_counter 以避免 time.time() 的系统调用开销
            # 计算 perf_counter 目标值
            perf_now = time.perf_counter()
            time_now = self.ntp.get_precise_time()
            perf_target = perf_now + (target_ts - time_now)

            while time.perf_counter() < perf_target:
                pass  # 自旋

            # ======== 触发！ ========
            actual_time = self.ntp.get_precise_time()
            deviation_ms = (actual_time - target_ts) * 1000
            logger.success(
                "触发！偏差: {:.3f}ms ({})",
                deviation_ms,
                datetime.fromtimestamp(actual_time).strftime("%H:%M:%S.%f")[:-3],
            )

            await trigger_callback()

        finally:
            ntp_task.cancel()
            try:
                await ntp_task
            except asyncio.CancelledError:
                pass
