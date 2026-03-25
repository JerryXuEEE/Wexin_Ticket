"""NTP 时间同步 — 多服务器查询，取中位数偏移。"""

from __future__ import annotations

import asyncio
import statistics
import time

import ntplib
from loguru import logger


class NTPSynchronizer:
    """通过多个 NTP 服务器校准本地时钟偏移。"""

    def __init__(self, servers: list[str]) -> None:
        self.servers = servers
        self.offset: float = 0.0  # 秒
        self._client = ntplib.NTPClient()

    async def sync(self) -> float:
        """查询所有 NTP 服务器，返回中位数偏移（秒）。"""
        tasks = [self._query_server(s) for s in self.servers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        offsets: list[float] = []
        for server, result in zip(self.servers, results):
            if isinstance(result, Exception):
                logger.warning("NTP 查询失败 [{}]: {}", server, result)
            else:
                offsets.append(result)
                logger.debug("NTP 偏移 [{}]: {:.6f}s", server, result)

        if not offsets:
            logger.error("所有 NTP 服务器查询失败，使用本地时钟 (offset=0)")
            self.offset = 0.0
            return self.offset

        self.offset = statistics.median(offsets)
        logger.info(
            "NTP 同步完成: 有效服务器={}/{}, 中位数偏移={:.6f}s ({:.3f}ms)",
            len(offsets),
            len(self.servers),
            self.offset,
            self.offset * 1000,
        )
        return self.offset

    async def _query_server(self, server: str) -> float:
        """查询单个 NTP 服务器，返回偏移量（秒）。"""
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, lambda: self._client.request(server, version=3, timeout=5)
        )
        return response.offset

    def get_precise_time(self) -> float:
        """返回 NTP 校准后的当前 Unix 时间戳。"""
        return time.time() + self.offset

    async def periodic_sync(self, interval_s: float = 300) -> None:
        """后台定期重新同步 NTP 偏移。"""
        while True:
            await asyncio.sleep(interval_s)
            try:
                await self.sync()
            except Exception as e:
                logger.warning("NTP 周期同步异常: {}", e)
