"""API 数据模型 — 基于 zwcdata.com 抓包数据。"""

from __future__ import annotations

from dataclasses import dataclass, field


# 场地 status 含义（来自 getVenueStatus 响应）
SLOT_STATUS_AVAILABLE = "1"    # 可预约（放票后的状态）
SLOT_STATUS_FREE = "0"         # 当日可约（非预约模式）
SLOT_STATUS_BOOKED = "2"       # 已被预约
SLOT_STATUS_CLOSED = "4"       # 不可用/已过期


@dataclass
class SlotInfo:
    """单个场地时段的状态信息（来自 getVenueStatus.data.sites[].siteStatus[]）。"""

    slot_id: int               # siteStatus.id，唯一标识此时段
    site_id: int               # sites.id，场地 ID（31-36）
    site_name: str             # sites.siteName，如"1号场"
    set_date: str              # "2026-03-25"
    set_time: str              # "09:30-10:30"
    stime: str                 # "09:30"
    etime: str                 # "10:30"
    price: float               # 单位：元
    status: str                # "0"/"1"/"2"/"4"
    raw_data: dict = field(default_factory=dict)

    @property
    def available(self) -> bool:
        """是否可预约（status=1 为放票后可抢状态）。"""
        return self.status in (SLOT_STATUS_AVAILABLE, SLOT_STATUS_FREE)


@dataclass
class BookingResponse:
    """POST /venueOrder 响应。"""

    success: bool
    order_id: int | None = None    # data[0]，即订单 ID
    message: str = ""
    status_code: int = 0
    raw_data: dict = field(default_factory=dict)


@dataclass
class BookingStatusResponse:
    """GET /venueOrder/{id} 响应。"""

    confirmed: bool
    order_id: int | None = None
    message: str = ""
    raw_data: dict = field(default_factory=dict)
