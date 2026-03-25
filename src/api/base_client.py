"""API 客户端协议 — 定义可插拔接口。"""

from __future__ import annotations

from typing import Protocol

from src.api.models import BookingResponse, BookingStatusResponse, SlotInfo
from src.context import BookingTarget


class VenueAPIProtocol(Protocol):
    """
    场地预约 API 协议。

    任何实现了以下方法的类都可以作为 API 客户端使用。
    抓包后如果 API 结构差异较大，可以编写新的客户端类来实现此协议。
    """

    async def query_available_slots(
        self, date: str, venue_id: str | None = None
    ) -> list[SlotInfo]: ...

    async def submit_booking(self, target: BookingTarget) -> BookingResponse: ...

    async def check_booking_status(
        self, booking_id: str
    ) -> BookingStatusResponse: ...
