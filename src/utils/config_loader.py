"""YAML 配置加载与基础校验。"""

from __future__ import annotations

from pathlib import Path

import yaml
from loguru import logger


_REQUIRED_SECTIONS = ["booking", "scheduler", "engine", "auth", "api", "notify", "logging"]


def load_config(path: str | Path = "config/config.yaml") -> dict:
    """加载并校验 YAML 配置文件。"""
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path.resolve()}")

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if not isinstance(config, dict):
        raise ValueError("配置文件格式错误: 顶层必须是字典")

    missing = [s for s in _REQUIRED_SECTIONS if s not in config]
    if missing:
        raise ValueError(f"配置文件缺少必要的段落: {', '.join(missing)}")

    # 基础类型校验
    engine = config["engine"]
    if engine.get("concurrency", 0) < 1:
        raise ValueError("engine.concurrency 必须 >= 1")
    if engine.get("attempt_rounds", 0) < 1:
        raise ValueError("engine.attempt_rounds 必须 >= 1")

    scheduler = config["scheduler"]
    if not scheduler.get("trigger_time"):
        raise ValueError("scheduler.trigger_time 不能为空")
    if not scheduler.get("ntp_servers"):
        raise ValueError("scheduler.ntp_servers 至少需要一个 NTP 服务器")

    logger.info("配置加载成功: {}", config_path.resolve())
    return config
