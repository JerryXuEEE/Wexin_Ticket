"""SMTP 邮件通知。"""

from __future__ import annotations

from email.mime.text import MIMEText

import aiosmtplib
from loguru import logger


class EmailNotifier:
    """通过 SMTP 发送邮件通知。"""

    def __init__(self, email_config: dict) -> None:
        self.host = email_config["smtp_host"]
        self.port = email_config.get("smtp_port", 465)
        self.use_ssl = email_config.get("use_ssl", True)
        self.username = email_config["username"]
        self.password = email_config["password"]
        self.to_addrs: list[str] = email_config.get("to_addrs", [])

    async def send(self, title: str, body: str, level: str = "info") -> bool:
        """发送纯文本邮件。"""
        if not self.to_addrs:
            logger.warning("邮件通知未配置收件人")
            return False

        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = f"[抢票通知] {title}"
        msg["From"] = self.username
        msg["To"] = ", ".join(self.to_addrs)

        try:
            if self.use_ssl:
                smtp = aiosmtplib.SMTP(
                    hostname=self.host, port=self.port, use_tls=True
                )
            else:
                smtp = aiosmtplib.SMTP(hostname=self.host, port=self.port)

            async with smtp:
                await smtp.login(self.username, self.password)
                await smtp.sendmail(self.username, self.to_addrs, msg.as_string())

            logger.debug("邮件通知发送成功 → {}", self.to_addrs)
            return True
        except Exception as e:
            logger.error("邮件通知失败: {}", e)
            return False
