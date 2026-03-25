"""企业微信 Webhook 通知。"""

from __future__ import annotations

import aiohttp
from loguru import logger


class WeChatWorkNotifier:
    """通过企业微信群机器人 Webhook 发送通知。"""

    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url

    async def send(self, title: str, body: str, level: str = "info") -> bool:
        """发送 Markdown 格式消息到企业微信。"""
        color_map = {"success": "info", "error": "warning", "warning": "comment"}
        color = color_map.get(level, "info")

        content = f"### {title}\n\n<font color=\"{color}\">{body}</font>"

        payload = {
            "msgtype": "markdown",
            "markdown": {"content": content},
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    data = await resp.json()
                    if data.get("errcode") == 0:
                        logger.debug("企业微信通知发送成功")
                        return True
                    else:
                        logger.warning("企业微信通知失败: {}", data)
                        return False
        except Exception as e:
            logger.error("企业微信通知异常: {}", e)
            return False
