"""认证管理器 — Token 生命周期管理。"""

from __future__ import annotations

import aiohttp
from loguru import logger

from src.auth.token_store import TokenStore


class AuthManager:
    """
    管理 API 认证 token。

    当前实现: 从配置或缓存文件读取 token，检测 401 响应。
    未来扩展: 可对接自动续期接口。
    """

    def __init__(self, auth_config: dict, token_store: TokenStore) -> None:
        self.config = auth_config
        self.store = token_store
        self.token_header = auth_config.get("token_header", "Authorization")
        self.token_prefix = auth_config.get("token_prefix", "Bearer ")

        # 优先使用配置中的 token，其次从文件缓存加载
        self._token = auth_config.get("token", "").strip()
        if not self._token:
            self._token = self.store.load()

        # 如果配置中有 token，同步到缓存
        if self._token:
            self.store.save(self._token)
            logger.info("Token 已就绪 (长度={}, header={})", len(self._token), self.token_header)
        else:
            logger.warning("未配置 Token — 请在 config.yaml 中填入或通过抓包获取")

    def get_token(self) -> str:
        """返回当前 token。"""
        return self._token

    def is_token_valid(self) -> bool:
        """检查 token 是否非空（基础校验）。"""
        return bool(self._token)

    async def get_headers(self) -> dict[str, str]:
        """返回包含认证信息的请求头。"""
        if not self._token:
            return {}
        value = f"{self.token_prefix}{self._token}" if self.token_prefix else self._token
        return {self.token_header: value}

    async def on_auth_failure(self, response: aiohttp.ClientResponse) -> bool:
        """
        处理 401 认证失败。

        返回 True 表示 token 已刷新，调用方应重试。
        返回 False 表示无法恢复。
        """
        logger.error("认证失败 (HTTP {})", response.status)

        refreshed = await self.refresh_token()
        if refreshed:
            logger.info("Token 已自动刷新")
            return True

        logger.error("Token 无法刷新 — 请手动更新 config.yaml 中的 token")
        return False

    async def refresh_token(self) -> bool:
        """
        尝试自动刷新 token。

        PLACEHOLDER: 抓包后如果发现有 token 续期接口，在此实现。
        典型的微信小程序可能有 /auth/refresh 或类似接口。
        """
        # TODO: 实现自动续期
        # renewal_url = self.config.get("renewal_url")
        # if not renewal_url:
        #     return False
        # async with aiohttp.ClientSession() as session:
        #     async with session.post(renewal_url, json={...}) as resp:
        #         data = await resp.json()
        #         new_token = data.get("token")
        #         if new_token:
        #             self._token = new_token
        #             self.store.save(new_token)
        #             return True
        return False

    def update_token(self, new_token: str) -> None:
        """手动更新 token。"""
        self._token = new_token.strip()
        self.store.save(self._token)
        logger.info("Token 已手动更新 (长度={})", len(self._token))
