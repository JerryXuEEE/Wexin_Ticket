"""共享数据上下文。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BookingTarget:
    """单个抢票目标，字段与 POST /venueOrder 请求体一一对应。"""

    date: str              # "2026-03-25"
    time_slot: str         # "09:30-10:30"
    court_id: int          # 场地 ID: 31-36（1-6号场）
    court_name: str        # "1号场"
    venue_id: str = "3"
    venue_name: str = "跃动乒羽馆"
    venuetype_id: int = 29          # 羽毛球=29
    venuetype_name: str = "羽毛球"
    price: float = 0.0              # 元，查询到 status=1 时更新
    priority: int = 0               # 越小优先级越高


@dataclass
class BookingResult:
    """单次抢票尝试的结果。"""

    success: bool
    target: BookingTarget
    response_data: dict | None = None
    error: str | None = None
    attempt_number: int = 0
    latency_ms: float = 0.0
    order_id: int | None = None


@dataclass
class BookingContext:
    """全局上下文，贯穿整条流水线。"""

    config: dict
    targets: list[BookingTarget] = field(default_factory=list)
    auth_token: str = ""
    results: list[BookingResult] = field(default_factory=list)
    ntp_offset_ms: float = 0.0
    dry_run: bool = False
