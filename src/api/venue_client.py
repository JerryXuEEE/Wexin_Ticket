"""场地预约 API 客户端 — 基于抓包数据完整实现。"""

from __future__ import annotations

import time

import aiohttp
from loguru import logger

from src.api.models import (
    SLOT_STATUS_AVAILABLE,
    BookingResponse,
    BookingStatusResponse,
    SlotInfo,
)
from src.auth.manager import AuthManager
from src.context import BookingTarget


class VenueClient:
    """
    跃动乒羽馆预约 API 客户端。

    所有接口均已通过抓包验证，基于 www.zwcdata.com/ly2/api。
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        api_config: dict,
        auth: AuthManager,
    ) -> None:
        self.session = session
        self.base_url = api_config["base_url"].rstrip("/")
        self.endpoints = api_config["endpoints"]
        self.extra_headers = api_config.get("extra_headers", {})
        self.auth = auth

    def _url(self, endpoint_key: str, suffix: str = "") -> str:
        return f"{self.base_url}{self.endpoints[endpoint_key]}{suffix}"

    async def _headers(self) -> dict[str, str]:
        headers = dict(self.extra_headers)
        headers.update(await self.auth.get_headers())
        return headers

    # ========== 查询场地状态 ==========

    async def query_available_slots(
        self, date: str, venue_id: str = "3", venuetype_id: int = 29
    ) -> list[SlotInfo]:
        """
        查询指定日期的羽毛球场地状态。

        GET /venue/index/getVenueStatus?venueId=3&venuetypeId=29&date=2026-03-25
        """
        url = self._url("venue_status")
        params = {
            "venueId": venue_id,
            "venuetypeId": venuetype_id,
            "date": date,
        }

        async with self.session.get(url, params=params, headers=await self._headers()) as resp:
            if resp.status == 401:
                if await self.auth.on_auth_failure(resp):
                    return await self.query_available_slots(date, venue_id, venuetype_id)
                raise PermissionError("Token 已过期且无法刷新")

            resp.raise_for_status()
            data = await resp.json()
            return self._parse_slots(data)

    # ========== 提交预约 ==========

    async def submit_booking(self, target: BookingTarget) -> BookingResponse:
        """
        提交预约请求。

        POST /venueOrder
        请求体示例（来自抓包）:
        {
          "isCoach": "0",
          "type": 0,
          "venueName": "跃动乒羽馆",
          "startTime": "2026-03-25",
          "times": ["09:30-10:30"],
          "venueId": "3",
          "venuetypeId1": 29,
          "venuetypeId2": 31,
          "venueMoney": 3600,
          "venuetypeName1": "羽毛球",
          "venuetypeName2": "1号场"
        }
        """
        url = self._url("book")
        payload = self._build_booking_payload(target)

        start = time.perf_counter()
        async with self.session.post(url, json=payload, headers=await self._headers()) as resp:
            elapsed_ms = (time.perf_counter() - start) * 1000

            if resp.status == 401:
                if await self.auth.on_auth_failure(resp):
                    return await self.submit_booking(target)
                return BookingResponse(success=False, message="Token 已过期", status_code=401)

            data = await resp.json()
            result = self._parse_booking_response(data, resp.status)

            logger.info(
                "预约 [{}场 {}] → {} ({:.0f}ms)",
                target.court_name,
                target.time_slot,
                "成功" if result.success else f"失败: {result.message}",
                elapsed_ms,
            )
            return result

    # ========== 查询订单状态 ==========

    async def check_booking_status(self, order_id: int | str) -> BookingStatusResponse:
        """
        查询订单详情。

        GET /venueOrder/{orderId}
        """
        url = self._url("booking_detail", f"/{order_id}")

        async with self.session.get(url, headers=await self._headers()) as resp:
            data = await resp.json()
            confirmed = (
                isinstance(data, dict)
                and data.get("code") == 200
                and data.get("data") is not None
            )
            return BookingStatusResponse(
                confirmed=confirmed,
                order_id=int(order_id),
                message=data.get("msg", ""),
                raw_data=data,
            )

    # ========== 获取服务器时间（用于时钟对齐） ==========

    async def get_server_time(self) -> str | None:
        """
        POST /base/day → {"code":200,"msg":"操作成功","data":"2026-03-23 21:19:16"}
        """
        url = self._url("server_time")
        try:
            async with self.session.post(url, json={}, headers=await self._headers()) as resp:
                data = await resp.json()
                return data.get("data")
        except Exception as e:
            logger.warning("获取服务器时间失败: {}", e)
            return None

    # ========== 内部实现 ==========

    def _build_booking_payload(self, target: BookingTarget) -> dict:
        """
        构建预约请求体（与抓包数据完全一致）。

        venueMoney 单位为"分"（元 × 100），价格从 getVenueStatus 响应中获取。
        """
        return {
            "isCoach": "0",
            "type": 0,
            "venueName": target.venue_name,
            "startTime": target.date,
            "times": [target.time_slot],
            "venueId": str(target.venue_id),
            "venuetypeId1": target.venuetype_id,    # 29 = 羽毛球
            "venuetypeId2": target.court_id,         # 31-36 = 1-6号场
            "venueMoney": int(target.price * 100),   # 元 → 分
            "venuetypeName1": target.venuetype_name, # "羽毛球"
            "venuetypeName2": target.court_name,     # "1号场"
        }

    def _parse_slots(self, data: dict) -> list[SlotInfo]:
        """
        解析 getVenueStatus 响应。

        响应结构:
        {
          "data": {
            "date": ["09:30", "10:30", ...],
            "sites": [
              {
                "id": 31, "siteName": "1号场",
                "siteStatus": [
                  {"id": 58345, "setDate": "2026-03-25", "setTime": "09:30-10:30",
                   "price": 0.00, "status": "1", "stime": "09:30", "etime": "10:30", ...}
                ]
              }, ...
            ]
          }
        }
        """
        slots: list[SlotInfo] = []
        inner = data.get("data", {})
        if not isinstance(inner, dict):
            return slots

        for site in inner.get("sites", []):
            site_id = site.get("id")
            site_name = site.get("siteName", "")
            for s in site.get("siteStatus", []):
                slots.append(SlotInfo(
                    slot_id=s.get("id", 0),
                    site_id=site_id,
                    site_name=site_name,
                    set_date=s.get("setDate", ""),
                    set_time=s.get("setTime", ""),
                    stime=s.get("stime", ""),
                    etime=s.get("etime", ""),
                    price=float(s.get("price", 0)),
                    status=str(s.get("status", "")),
                    raw_data=s,
                ))
        return slots

    def _parse_booking_response(self, data: dict, status_code: int) -> BookingResponse:
        """
        解析 POST /venueOrder 响应。

        成功响应: {"code": 200, "msg": "操作成功", "data": [25646]}
        data[0] 为订单 ID。
        """
        if not isinstance(data, dict):
            return BookingResponse(success=False, message="响应格式错误", status_code=status_code, raw_data={})

        code = data.get("code")
        msg = data.get("msg", "")
        order_data = data.get("data")

        success = (code == 200 and isinstance(order_data, list) and len(order_data) > 0)
        order_id = order_data[0] if success else None

        return BookingResponse(
            success=success,
            order_id=order_id,
            message=msg,
            status_code=status_code,
            raw_data=data,
        )
