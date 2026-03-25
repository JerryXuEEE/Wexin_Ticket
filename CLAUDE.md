# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 运行

**启动抢票（真实模式）：**
```
"D:/Softwares/Anaconda3/python.exe" src/main.py
```
程序自动等到 9:30:00.000 触发，发送并发请求，抢到即停。

**Dry-run 测试（不发真实请求）：**
```
"D:/Softwares/Anaconda3/python.exe" src/main.py --dry-run
```

**安装依赖：**
```
pip install -r requirements.txt
```

**关键：** 系统有多个 Python 环境，必须用 Anaconda。直接 `python` 命令会导致 exit code 49（包导入失败）。

**Agent 用户交互要点** 给用户建议在bash里跑的代码保证为一行指令以便于用户直接复制粘贴到CMD里回车后run

## 架构

### 流水线
```
NTP同步 → 精准等待至9:30 → 预热连接池 → 并发抢票（可重试）→ 通知
```

### 核心模块

| 模块 | 作用 |
|------|------|
| `src/scheduler/` | NTP 三服务器同步 + 三阶段精准等待（偏差 <5ms） |
| `src/engine/booking_engine.py` | 多轮并发编排，首个成功即取消其余 |
| `src/engine/retry.py` | 指数退避重试，对 502/503/429/超时 重试，401 刷新 token |
| `src/api/venue_client.py` | API 实现，所有字段已通过 Fiddler 抓包验证 |
| `src/auth/` | Token 管理，优先级：config.yaml → .token_cache 文件 |
| `src/notify/` | 多渠道通知（控制台、企业微信、钉钉、邮件） |

### API 端点（www.zwcdata.com/ly2/api）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/venue/index/getVenueStatus` | 查询场地，status="1" 可抢 |
| POST | `/venueOrder` | 预约，data[0] 为订单 ID |
| GET | `/venueOrder/{id}` | 查询订单状态 |

## 配置关键字段（config/config.yaml）

- `booking.preferred_courts` — 场地列表，id 31-36（对应 1-6 号场）
- `booking.preferred_time_slots` — 时间段，格式 `"09:30-10:30"`
- `auth.token` — Bearer token，从 Fiddler 抓包获取（Bearer 后的字符串）
- `scheduler.trigger_time` — 触发时间，默认 `"09:30:00.000"`

## 场地状态码

| 码 | 含义 |
|----|------|
| "1" | 预约模式可抢 |
| "2" | 已被预约 |
| "4" | 不可用 |

## 关键实现

1. **精准定时**：NTP 校准 + 三阶段等待（粗睡眠→细睡眠→busy-wait 自旋）
2. **并发控制**：`asyncio.Semaphore` 限制并发数，`asyncio.Event` 实现首个成功即取消
3. **智能重试**：指数退避+抖动，不重试业务失败（如"场地已满"）
4. **可插拔 API**：Protocol 抽象，易于扩展或切换实现

## 抓包工具

`capture/` 目录有 Fiddler/mitmproxy 辅助工具。域名 `www.zwcdata.com`，认证 `Authorization: Bearer <token>`。Token 失效后需重新抓包。
