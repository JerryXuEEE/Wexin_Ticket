"""连接池预热 — 通过合法 API 请求建立 TCP+TLS 连接。"""

from __future__ import annotations

import aiohttp
from loguru import logger


class PoolWarmer:
    """
    在触发时间前预热 aiohttp 连接池。

    使用 POST /base/day（获取服务器时间）作为预热请求，
    这是微信小程序的正常调用，不会触发限频。
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        headers: dict[str, str],
        count: int = 1,
    ) -> None:
        self.session = session
        self.base_url = base_url.rstrip("/")
        self.headers = headers
        self.count = count

    async def warm(self) -> None:
        """发出合法 API 请求来预建连接。"""
        url = f"{self.base_url}/base/day"
        logger.info("预热连接: POST {} ({}次)", url, self.count)

        for i in range(self.count):
            try:
                async with self.session.post(
                    url,
                    json={},
                    headers=self.headers,
                    timeout=aiohttp.ClientTimeout(total=3),
                ) as resp:
                    data = await resp.json()
                    server_time = data.get("data", "unknown")
                    logger.info("预热成功: 服务器时间={}", server_time)
            except Exception as e:
                logger.warning("预热连接失败 (可忽略): {}", e)
