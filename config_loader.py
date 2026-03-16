"""
config_loader.py — HtMeteo 配置加载与校验模块

将 config.yaml 中的原始 YAML 结构解析为类型化的 Python 数据类，
并在加载时执行基础校验，给出友好的错误提示。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml


# ── 数据类定义 ────────────────────────────────────────────────────────────────

@dataclass
class GlobalConfig:
    work_dir: str = "./data"
    log_level: str = "INFO"
    log_file: str = "./logs/htmeteo.log"
    timezone: str = "Asia/Shanghai"


@dataclass
class AccountConfig:
    username: str = ""
    password: str = ""


@dataclass
class DatabaseConfig:
    enabled: bool = False
    type: str = "mysql"
    host: str = "localhost"
    port: int = 3306
    user: str = "root"
    password: str = ""
    name: str = "weather"
    table_prefix: str = "ht_"
    pool_size: int = 5


@dataclass
class ScheduleConfig:
    type: str = "once"           # once | cron | interval
    cron: Optional[str] = None
    interval: Optional[int] = None


@dataclass
class OutputConfig:
    to: str = "local"            # local | database | both
    format: str = "parquet"      # parquet | csv


@dataclass
class QueryConfig:
    time_type: str = "daily"     # daily | monthly | yearly


@dataclass
class TaskGroup:
    name: str
    type: str                    # history | forecast | fetch-all-forecast | api-forecast | api-history
    enabled: bool = True
    locations: List[str] = field(default_factory=list)
    meteo_types: List[str] = field(default_factory=list)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    query: Optional[QueryConfig] = None

    VALID_TYPES = {
        "history",
        "forecast",
        "fetch-all-forecast",
        "api-forecast",
        "api-history",
    }

    def validate(self) -> None:
        if self.type not in self.VALID_TYPES:
            raise ValueError(
                f"任务组 [{self.name}] 的 type='{self.type}' 无效，"
                f"可选值：{', '.join(sorted(self.VALID_TYPES))}"
            )
        if self.schedule.type == "cron" and not self.schedule.cron:
            raise ValueError(f"任务组 [{self.name}] schedule.type=cron 时必须填写 cron 表达式。")
        if self.schedule.type == "interval" and not self.schedule.interval:
            raise ValueError(f"任务组 [{self.name}] schedule.type=interval 时必须填写 interval（秒）。")
        if self.output.to not in ("local", "database", "both"):
            raise ValueError(
                f"任务组 [{self.name}] output.to='{self.output.to}' 无效，"
                "可选值：local | database | both"
            )


# ── 主配置类 ──────────────────────────────────────────────────────────────────

class HtMeteoConfig:
    """
    从 config.yaml 加载并解析完整配置。

    用法::

        cfg = HtMeteoConfig("config.yaml")
        print(cfg.account.username)
        for tg in cfg.enabled_task_groups:
            print(tg.name, tg.type)
    """

    def __init__(self, config_path: str = "config.yaml") -> None:
        self._path = Path(config_path)
        if not self._path.exists():
            raise FileNotFoundError(
                f"找不到配置文件：{self._path.resolve()}\n"
                "请将 config.yaml 放在工作目录，或传入正确的路径。"
            )
        with open(self._path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}

        self.global_config: GlobalConfig = self._parse_global(raw)
        self.account: AccountConfig = self._parse_account(raw)
        self.database: DatabaseConfig = self._parse_database(raw)
        self.task_groups: List[TaskGroup] = self._parse_task_groups(raw)
        self._validate()

    # ── 解析各节 ──────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_global(raw: dict) -> GlobalConfig:
        g = raw.get("global", {}) or {}
        return GlobalConfig(
            work_dir=g.get("work_dir", "./data"),
            log_level=g.get("log_level", "INFO").upper(),
            log_file=g.get("log_file", "./logs/htmeteo.log"),
            timezone=g.get("timezone", "Asia/Shanghai"),
        )

    @staticmethod
    def _parse_account(raw: dict) -> AccountConfig:
        a = raw.get("account", {}) or {}
        return AccountConfig(
            username=str(a.get("username", "")),
            password=str(a.get("password", "")),
        )

    @staticmethod
    def _parse_database(raw: dict) -> DatabaseConfig:
        d = raw.get("database", {}) or {}
        return DatabaseConfig(
            enabled=bool(d.get("enabled", False)),
            type=d.get("type", "mysql"),
            host=d.get("host", "localhost"),
            port=int(d.get("port", 3306)),
            user=d.get("user", "root"),
            password=str(d.get("password", "")),
            name=d.get("name", "weather"),
            table_prefix=d.get("table_prefix", "ht_"),
            pool_size=int(d.get("pool_size", 5)),
        )

    @staticmethod
    def _parse_task_groups(raw: dict) -> List[TaskGroup]:
        groups: List[TaskGroup] = []
        for tg_raw in raw.get("task-groups", []) or []:
            sched_raw = tg_raw.get("schedule", {}) or {}
            schedule = ScheduleConfig(
                type=sched_raw.get("type", "once"),
                cron=sched_raw.get("cron"),
                interval=sched_raw.get("interval"),
            )

            out_raw = tg_raw.get("output", {}) or {}
            output = OutputConfig(
                to=out_raw.get("to", "local"),
                format=out_raw.get("format", "parquet"),
            )

            query_raw = tg_raw.get("query")
            query = (
                QueryConfig(time_type=query_raw.get("time_type", "daily"))
                if query_raw
                else None
            )

            tg = TaskGroup(
                name=tg_raw.get("name", "unnamed"),
                type=tg_raw.get("type", ""),
                enabled=bool(tg_raw.get("enabled", True)),
                locations=list(tg_raw.get("locations", []) or []),
                meteo_types=list(tg_raw.get("meteo_types", []) or []),
                schedule=schedule,
                output=output,
                query=query,
            )
            groups.append(tg)
        return groups

    # ── 校验 ──────────────────────────────────────────────────────────────────

    def _validate(self) -> None:
        errors: List[str] = []

        if not self.account.username:
            errors.append("account.username 不能为空。")
        if not self.account.password:
            errors.append("account.password 不能为空。")

        for tg in self.task_groups:
            try:
                tg.validate()
            except ValueError as exc:
                errors.append(str(exc))

        if errors:
            msg = "\n".join(f"  • {e}" for e in errors)
            raise ValueError(f"config.yaml 存在以下配置错误：\n{msg}")

    # ── 便捷访问 ──────────────────────────────────────────────────────────────

    @property
    def enabled_task_groups(self) -> List[TaskGroup]:
        """返回所有 enabled=true 的任务组。"""
        return [tg for tg in self.task_groups if tg.enabled]

    def get_task_group(self, name: str) -> Optional[TaskGroup]:
        """按名称查找任务组，找不到返回 None。"""
        for tg in self.task_groups:
            if tg.name == name:
                return tg
        return None

    def work_dir_path(self) -> Path:
        """返回全局 work_dir 的 Path 对象。"""
        return Path(self.global_config.work_dir)

    def __repr__(self) -> str:
        enabled = sum(1 for tg in self.task_groups if tg.enabled)
        return (
            f"<HtMeteoConfig "
            f"account={self.account.username!r} "
            f"task_groups={len(self.task_groups)} "
            f"enabled={enabled} "
            f"db={self.database.enabled}>"
        )
