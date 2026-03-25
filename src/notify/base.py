"""通知系统基础 — Protocol 定义 + NotifierChain 聚合。"""

from __future__ import annotations

import asyncio
from typing import Protocol

from loguru import logger


class Notifier(Protocol):
    """通知器协议，所有通知实现需满足此接口。"""

    async def send(self, title: str, body: str, level: str = "info") -> bool: ...


class NotifierChain:
    """聚合多个通知器，并发发送，失败不阻塞。"""

    def __init__(self, notifiers: list[Notifier]) -> None:
        self.notifiers = notifiers

    async def notify_all(self, title: str, body: str, level: str = "info") -> None:
        """向所有通知器并发发送消息。"""
        if not self.notifiers:
            logger.debug("无通知器配置，跳过通知")
            return

        results = await asyncio.gather(
            *[self._safe_send(n, title, body, level) for n in self.notifiers],
            return_exceptions=True,
        )

        success = sum(1 for r in results if r is True)
        failed = len(results) - success
        if failed:
            logger.warning("通知发送: 成功={} 失败={}", success, failed)
        else:
            logger.info("通知发送完成: {} 个渠道", success)

    async def _safe_send(
        self, notifier: Notifier, title: str, body: str, level: str
    ) -> bool:
        """安全地发送通知，捕获所有异常。"""
        try:
            return await notifier.send(title, body, level)
        except Exception as e:
            logger.error("通知发送失败 [{}]: {}", type(notifier).__name__, e)
            return False


def build_notifier_chain(notify_config: dict) -> NotifierChain:
    """根据配置构建 NotifierChain。"""
    from src.notify.console import ConsoleNotifier
    from src.notify.dingtalk import DingTalkNotifier
    from src.notify.email_notify import EmailNotifier
    from src.notify.wechat_work import WeChatWorkNotifier

    notifiers: list[Notifier] = []
    channels = notify_config.get("enabled_channels", ["console"])

    for channel in channels:
        channel = channel.lower().strip()

        if channel == "console":
            notifiers.append(ConsoleNotifier())

        elif channel == "wechat_work":
            cfg = notify_config.get("wechat_work", {})
            if cfg.get("webhook_url"):
                notifiers.append(WeChatWorkNotifier(cfg["webhook_url"]))
            else:
                logger.warning("企业微信通知已启用但未配置 webhook_url")

        elif channel == "dingtalk":
            cfg = notify_config.get("dingtalk", {})
            if cfg.get("webhook_url"):
                notifiers.append(DingTalkNotifier(cfg["webhook_url"], cfg.get("secret", "")))
            else:
                logger.warning("钉钉通知已启用但未配置 webhook_url")

        elif channel == "email":
            cfg = notify_config.get("email", {})
            if cfg.get("username") and cfg.get("to_addrs"):
                notifiers.append(EmailNotifier(cfg))
            else:
                logger.warning("邮件通知已启用但未配置 username 或 to_addrs")

        else:
            logger.warning("未知通知渠道: {}", channel)

    logger.info("通知系统初始化: {} 个渠道 ({})", len(notifiers), ", ".join(channels))
    return NotifierChain(notifiers)
