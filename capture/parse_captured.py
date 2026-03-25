"""
解析 mitmproxy 抓包数据，生成 config.yaml 可用的配置片段。

使用方法:
    python capture/parse_captured.py [captured_flows.json]
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


def analyze_flows(flows: list[dict]) -> None:
    """分析抓包数据并输出配置建议。"""
    if not flows:
        print("没有捕获到任何流量")
        return

    print(f"\n{'='*60}")
    print(f"共捕获 {len(flows)} 个请求")
    print(f"{'='*60}")

    # 1. 分析域名
    hosts = Counter(f["host"] for f in flows)
    print("\n## 域名统计")
    for host, count in hosts.most_common():
        print(f"  {host}: {count} 次")

    # 2. 提取 base_url
    most_common_host = hosts.most_common(1)[0][0]
    # 判断 scheme
    sample_url = next(f["url"] for f in flows if f["host"] == most_common_host)
    scheme = "https" if sample_url.startswith("https") else "http"
    base_url = f"{scheme}://{most_common_host}"

    print(f"\n## 推荐 base_url")
    print(f"  {base_url}")

    # 3. 分析端点
    print("\n## API 端点")
    for flow in flows:
        path = flow["path"].split("?")[0]
        print(f"  {flow['method']} {path}  (HTTP {flow['response_status']})")

    # 4. 提取认证头
    print("\n## 认证信息")
    auth_headers: dict[str, str] = {}
    for flow in flows:
        headers = flow.get("request_headers", {})
        for key in ["Authorization", "authorization", "Token", "token",
                     "X-Token", "x-token", "Cookie", "cookie",
                     "X-Session", "x-session"]:
            if key in headers:
                auth_headers[key] = headers[key]

    if auth_headers:
        for k, v in auth_headers.items():
            print(f"  {k}: {v[:50]}...")
    else:
        print("  未发现明显的认证头")

    # 5. 提取额外请求头
    print("\n## 常见请求头")
    sample_headers = flows[0].get("request_headers", {})
    important_keys = ["User-Agent", "Referer", "Content-Type", "Accept", "Origin"]
    for key in important_keys:
        for h_key, h_val in sample_headers.items():
            if h_key.lower() == key.lower():
                print(f"  {h_key}: {h_val}")

    # 6. 生成 config 片段
    print(f"\n{'='*60}")
    print("## 建议的 config.yaml 配置片段")
    print(f"{'='*60}")

    # 找出可能的预约接口
    book_endpoints = [
        f for f in flows
        if f["method"] == "POST"
        and any(kw in f["path"].lower() for kw in ["book", "order", "reserve", "submit", "create"])
    ]

    # 找出可能的查询接口
    query_endpoints = [
        f for f in flows
        if f["method"] == "GET"
        and any(kw in f["path"].lower() for kw in ["slot", "list", "query", "available", "schedule", "court"])
    ]

    print("\napi:")
    print(f'  base_url: "{base_url}"')
    print("  endpoints:")

    if query_endpoints:
        path = query_endpoints[0]["path"].split("?")[0]
        print(f'    available_slots: "{path}"')
    else:
        print('    available_slots: "/TODO"  # 需要手动识别查询接口')

    if book_endpoints:
        path = book_endpoints[0]["path"].split("?")[0]
        print(f'    book: "{path}"')
    else:
        print('    book: "/TODO"  # 需要手动识别预约接口')

    print('    booking_status: "/TODO"')

    print("  extra_headers:")
    for key in ["User-Agent", "Referer"]:
        for h_key, h_val in sample_headers.items():
            if h_key.lower() == key.lower():
                print(f'    {h_key}: "{h_val}"')

    # Token 配置
    if auth_headers:
        header_name = list(auth_headers.keys())[0]
        header_value = list(auth_headers.values())[0]

        # 判断前缀
        prefix = ""
        token_value = header_value
        if header_value.startswith("Bearer "):
            prefix = "Bearer "
            token_value = header_value[7:]

        print("\nauth:")
        print(f'  token: "{token_value}"')
        print(f'  token_header: "{header_name}"')
        print(f'  token_prefix: "{prefix}"')

    # 7. 显示请求/响应样本
    print(f"\n{'='*60}")
    print("## 请求/响应样本（用于调整 PLACEHOLDER 方法）")
    print(f"{'='*60}")

    for flow in flows[:5]:
        print(f"\n--- {flow['method']} {flow['path']} ---")
        if flow.get("request_body"):
            print(f"请求体: {json.dumps(flow['request_body'], ensure_ascii=False, indent=2)[:500]}")
        if flow.get("response_body"):
            body = flow["response_body"]
            if isinstance(body, (dict, list)):
                print(f"响应体: {json.dumps(body, ensure_ascii=False, indent=2)[:500]}")
            else:
                print(f"响应体: {str(body)[:500]}")


def main() -> None:
    input_file = sys.argv[1] if len(sys.argv) > 1 else "capture/captured_flows.json"
    path = Path(input_file)

    if not path.exists():
        print(f"文件不存在: {path.resolve()}")
        print("请先运行 mitmproxy 抓包:")
        print("  mitmproxy -s capture/mitmproxy_addon.py")
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        flows = json.load(f)

    analyze_flows(flows)


if __name__ == "__main__":
    main()
