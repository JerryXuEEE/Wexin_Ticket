"""Token 持久化存储。"""

from __future__ import annotations

from pathlib import Path

from loguru import logger


class TokenStore:
    """文件级 token 持久化，支持跨进程/重启保留。"""

    def __init__(self, file_path: str = ".token_cache") -> None:
        self.path = Path(file_path)

    def load(self) -> str:
        """从文件加载 token，不存在返回空字符串。"""
        if not self.path.exists():
            return ""
        try:
            token = self.path.read_text(encoding="utf-8").strip()
            logger.debug("从缓存加载 token (长度={})", len(token))
            return token
        except Exception as e:
            logger.warning("加载 token 缓存失败: {}", e)
            return ""

    def save(self, token: str) -> None:
        """保存 token 到文件。"""
        try:
            self.path.write_text(token.strip(), encoding="utf-8")
            logger.debug("Token 已保存到 {}", self.path)
        except Exception as e:
            logger.error("保存 token 失败: {}", e)

    def clear(self) -> None:
        """清除缓存的 token。"""
        if self.path.exists():
            self.path.unlink()
            logger.debug("Token 缓存已清除")
