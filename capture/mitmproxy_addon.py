"""
mitmproxy 插件 — 自动过滤并记录微信小程序 API 流量。

使用方法:
    mitmproxy -s capture/mitmproxy_addon.py
    或
    mitmdump -s capture/mitmproxy_addon.py

可配置项（通过环境变量）:
    CAPTURE_KEYWORDS  — 域名关键字，逗号分隔（默认: 跃动,yuedon,booking）
    CAPTURE_OUTPUT    — 输出文件路径（默认: capture/captured_flows.json）
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from mitmproxy import http


# 配置
DOMAIN_KEYWORDS = os.environ.get("CAPTURE_KEYWORDS", "zwcdata,跃动,yuedon,booking,venue,reserve").split(",")
OUTPUT_FILE = os.environ.get("CAPTURE_OUTPUT", "capture/captured_flows.json")


class WeixinCaptureAddon:
    """自动捕获匹配的 HTTP 流量并保存为 JSON。"""

    def __init__(self) -> None:
        self.flows: list[dict] = []
        self.output_path = Path(OUTPUT_FILE)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"[抓包插件] 域名关键字: {DOMAIN_KEYWORDS}")
        print(f"[抓包插件] 输出文件: {self.output_path.resolve()}")

    def _match_domain(self, host: str) -> bool:
        """检查 host 是否匹配任一关键字。"""
        host_lower = host.lower()
        return any(kw.strip().lower() in host_lower for kw in DOMAIN_KEYWORDS)

    def response(self, flow: http.HTTPFlow) -> None:
        """拦截响应，记录匹配的流量。"""
        if not flow.response:
            return

        host = flow.request.pretty_host
        if not self._match_domain(host):
            return

        # 提取请求信息
        request_body = None
        try:
            content_type = flow.request.headers.get("content-type", "")
            if "json" in content_type:
                request_body = json.loads(flow.request.get_text())
            elif "form" in content_type:
                request_body = dict(flow.request.urlencoded_form)
            else:
                text = flow.request.get_text()
                if text:
                    try:
                        request_body = json.loads(text)
                    except json.JSONDecodeError:
                        request_body = text
        except Exception:
            request_body = flow.request.get_text()

        # 提取响应信息
        response_body = None
        try:
            response_body = json.loads(flow.response.get_text())
        except (json.JSONDecodeError, ValueError):
            response_body = flow.response.get_text()[:500]

        record = {
            "timestamp": datetime.now().isoformat(),
            "method": flow.request.method,
            "url": flow.request.pretty_url,
            "host": host,
            "path": flow.request.path,
            "request_headers": dict(flow.request.headers),
            "request_body": request_body,
            "response_status": flow.response.status_code,
            "response_headers": dict(flow.response.headers),
            "response_body": response_body,
        }

        self.flows.append(record)
        self._save()

        # 控制台高亮输出
        status = flow.response.status_code
        print(f"\n{'='*60}")
        print(f"[抓包] {flow.request.method} {flow.request.pretty_url}")
        print(f"[状态] {status}")
        print(f"[请求头]")
        for k, v in flow.request.headers.items():
            # 高亮认证相关头
            if k.lower() in ("authorization", "token", "cookie", "x-token", "x-session"):
                print(f"  *** {k}: {v}")
            else:
                print(f"  {k}: {v}")
        if request_body:
            print(f"[请求体] {json.dumps(request_body, ensure_ascii=False, indent=2)[:300]}")
        if response_body:
            body_str = json.dumps(response_body, ensure_ascii=False, indent=2) if isinstance(response_body, (dict, list)) else str(response_body)
            print(f"[响应体] {body_str[:500]}")
        print(f"{'='*60}")

    def _save(self) -> None:
        """将捕获的流量保存到 JSON 文件。"""
        with open(self.output_path, "w", encoding="utf-8") as f:
            json.dump(self.flows, f, ensure_ascii=False, indent=2)


addons = [WeixinCaptureAddon()]
