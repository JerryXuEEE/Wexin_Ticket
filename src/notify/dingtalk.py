"""钉钉 Webhook 通知（支持签名）。"""

from __future__ import annotations

import hashlib
import hmac
import base64
import time
import urllib.parse

import aiohttp
from loguru import logger


class DingTalkNotifier:
    """通过钉钉群机器人 Webhook 发送通知。"""

    def __init__(self, webhook_url: str, secret: str = "") -> None:
        self.webhook_url = webhook_url
        self.secret = secret

    def _sign_url(self) -> str:
        """生成带签名的 Webhook URL。"""
        if not self.secret:
            return self.webhook_url

        timestamp = str(round(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{self.secret}"
        hmac_code = hmac.new(
            self.secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))

        separator = "&" if "?" in self.webhook_url else "?"
        return f"{self.webhook_url}{separator}timestamp={timestamp}&sign={sign}"

    async def send(self, title: str, body: str, level: str = "info") -> bool:
        """发送 Markdown 格式消息到钉钉。"""
        url = self._sign_url()

        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": f"### {title}\n\n{body}",
            },
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    data = await resp.json()
                    if data.get("errcode") == 0:
                        logger.debug("钉钉通知发送成功")
                        return True
                    else:
                        logger.warning("钉钉通知失败: {}", data)
                        return False
        except Exception as e:
            logger.error("钉钉通知异常: {}", e)
            return False
