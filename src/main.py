"""抢票框架入口。"""

from __future__ import annotations

import asyncio
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from loguru import logger

# 确保项目根目录在 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.context import BookingContext, BookingTarget
from src.utils.config_loader import load_config
from src.utils.logging_setup import setup_logging


def build_targets(config: dict) -> list[BookingTarget]:
    """根据配置生成抢票目标列表（按优先级排序：时段优先，场地次之）。"""
    booking = config["booking"]
    offset_days = booking.get("target_date_offset", 2)
    target_date = (datetime.now() + timedelta(days=offset_days)).strftime("%Y-%m-%d")

    courts = booking.get("preferred_courts", [])   # [{"id": 31, "name": "1号场"}, ...]
    slots = booking.get("preferred_time_slots", [])

    venue_id = str(booking.get("venue_id", "3"))
    venue_name = booking.get("venue_name", "跃动乒羽馆")
    venuetype_id = int(booking.get("venuetype_id", 29))

    targets: list[BookingTarget] = []
    priority = 0
    for slot in slots:
        for court in courts:
            court_id = court["id"] if isinstance(court, dict) else court
            court_name = court.get("name", f"{court_id}号场") if isinstance(court, dict) else str(court)
            targets.append(
                BookingTarget(
                    date=target_date,
                    time_slot=slot,
                    court_id=court_id,
                    court_name=court_name,
                    venue_id=venue_id,
                    venue_name=venue_name,
                    venuetype_id=venuetype_id,
                    priority=priority,
                )
            )
            priority += 1

    logger.info("生成 {} 个抢票目标, 日期={}", len(targets), target_date)
    for t in targets:
        logger.debug("  [P{}] {} {} {} (场地ID={})", t.priority, t.date, t.court_name, t.time_slot, t.court_id)

    return targets


async def main() -> None:
    """主流程。"""
    # 1. 加载配置
    config = load_config()
    setup_logging(config["logging"])

    logger.info("=" * 60)
    logger.info("微信小程序抢票框架启动")
    logger.info("=" * 60)

    # 2. 构建目标
    targets = build_targets(config)

    # 3. 初始化上下文
    context = BookingContext(
        config=config,
        targets=targets,
        dry_run="--dry-run" in sys.argv,
    )

    if context.dry_run:
        logger.warning("DRY-RUN 模式: 不会发送真实请求")

    # 4. 初始化认证
    from src.auth.manager import AuthManager
    from src.auth.token_store import TokenStore

    token_store = TokenStore(config["auth"].get("token_file", ".token_cache"))
    auth = AuthManager(config["auth"], token_store)

    if not auth.is_token_valid():
        logger.error("Token 无效或未配置，请先在 config.yaml 中填入 token")
        if not context.dry_run:
            sys.exit(1)

    context.auth_token = auth.get_token()

    # 5. NTP 同步（作为后备时间源）
    from src.scheduler.ntp_sync import NTPSynchronizer

    ntp = NTPSynchronizer(config["scheduler"]["ntp_servers"])
    ntp_offset = await ntp.sync()
    ntp_available = ntp_offset != 0.0
    context.ntp_offset_ms = ntp_offset * 1000
    if ntp_available:
        logger.info("NTP 时间偏移: {:.3f}ms（后备）", context.ntp_offset_ms)
    else:
        logger.warning("NTP 同步失败，等待服务器时间矫正")

    # 6. 创建 aiohttp 会话
    import aiohttp

    from src.api.venue_client import VenueClient
    from src.engine.booking_engine import BookingEngine
    from src.engine.pool_warmer import PoolWarmer
    from src.engine.retry import RetryPolicy
    from src.notify.base import build_notifier_chain
    from src.scheduler.precision_timer import PrecisionTimer

    engine_cfg = config["engine"]
    connector = aiohttp.TCPConnector(
        limit=engine_cfg["concurrency"] * 2,
        limit_per_host=engine_cfg["concurrency"] * 2,
        ttl_dns_cache=300,
        enable_cleanup_closed=True,
    )
    timeout = aiohttp.ClientTimeout(total=engine_cfg["request_timeout_s"])

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        # 构建组件
        api_client = VenueClient(session, config["api"], auth)
        warm_headers = dict(config["api"].get("extra_headers", {}))
        warm_headers.update(await auth.get_headers())
        warmer = PoolWarmer(session, config["api"]["base_url"], warm_headers)

        # 6.1 时间矫正：优先用服务器时间，失败则回退 NTP
        t_before = time.time()
        server_time_str = await api_client.get_server_time()
        rtt_s = time.time() - t_before
        if server_time_str:
            try:
                server_dt = datetime.strptime(server_time_str, "%Y-%m-%d %H:%M:%S")
                server_ts = server_dt.timestamp() + 0.5  # 补偿秒级截断
                local_ts_at_server = ntp.get_precise_time() - rtt_s / 2  # 补偿网络 RTT
                deviation_s = local_ts_at_server - server_ts
                ntp.offset -= deviation_s
                context.ntp_offset_ms = ntp.offset * 1000
                logger.info(
                    "✓ 服务器时间矫正: 服务器={}, RTT={:.0f}ms, 偏差={:.3f}s, offset={:.3f}ms",
                    server_time_str, rtt_s * 1000, deviation_s, context.ntp_offset_ms,
                )
            except ValueError:
                logger.warning("服务器时间格式解析失败: {}", server_time_str)
        else:
            if ntp_available:
                logger.info("服务器时间不可用，使用 NTP 矫正 (offset={:.3f}ms)", context.ntp_offset_ms)
            else:
                logger.error("⚠ 服务器时间和 NTP 均不可用，使用本地时钟（精度无保障）")

        retry_cfg = engine_cfg["retry"]
        retry_policy = RetryPolicy(
            max_retries=retry_cfg["max_retries"],
            backoff_base_ms=retry_cfg["backoff_base_ms"],
            backoff_max_ms=retry_cfg["backoff_max_ms"],
            retryable_status_codes=set(retry_cfg["retryable_status_codes"]),
        )

        notifier = build_notifier_chain(config["notify"])
        engine = BookingEngine(api_client, auth, retry_policy, notifier, engine_cfg)

        # 7. 精准定时调度
        timer = PrecisionTimer(ntp, config["scheduler"])

        async def on_pre_connect() -> None:
            logger.info("预热连接池...")
            await warmer.warm()

        async def on_trigger() -> None:
            logger.info(">>> 触发！开始抢票 <<<")
            results = await engine.run(context)
            context.results = results

        await timer.schedule_booking(
            trigger_callback=on_trigger,
            pre_connect_callback=on_pre_connect,
        )

    # 8. 结果汇总
    successes = [r for r in context.results if r.success]
    failures = [r for r in context.results if not r.success]

    logger.info("=" * 60)
    if successes:
        logger.success("抢票成功！共 {} 个场地", len(successes))
        for r in successes:
            logger.success(
                "  场地={} 时段={} 耗时={:.0f}ms",
                r.target.court_id,
                r.target.time_slot,
                r.latency_ms,
            )
    else:
        logger.error("所有尝试均失败 ({} 次)", len(failures))

    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
