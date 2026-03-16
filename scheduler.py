"""
scheduler.py — HtMeteo 配置驱动任务调度引擎

工作流程：
  1. 读取 config.yaml，解析所有 task-groups
  2. 对 schedule.type=once 的任务组立即执行
  3. 对 schedule.type=cron/interval 的任务组注册到 APScheduler 持续运行

命令行快速启动::

    python scheduler.py                     # 按配置执行全部已启用任务组
    python scheduler.py --group 四川预报每日更新组   # 只执行指定任务组（立即运行一次）
    python scheduler.py --config my.yaml    # 指定配置文件路径

"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

# APScheduler（需要安装：pip install apscheduler）
try:
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    _HAS_APSCHEDULER = True
except ImportError:
    _HAS_APSCHEDULER = False

from config_loader import HtMeteoConfig, TaskGroup
from db_writer import write_dataframe_to_db
from HtMeteo import HtMeteo


# ── 日志初始化 ─────────────────────────────────────────────────────────────────

def _setup_logging(cfg: HtMeteoConfig) -> logging.Logger:
    log_path = Path(cfg.global_config.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    level = getattr(logging, cfg.global_config.log_level, logging.INFO)
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    handlers: list[logging.Handler] = [
        logging.FileHandler(log_path, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
    logging.basicConfig(level=level, format=fmt, handlers=handlers, force=True)
    return logging.getLogger("HtMeteoScheduler")


# ── 调度器主类 ─────────────────────────────────────────────────────────────────

class HtMeteoScheduler:
    """
    读取 config.yaml 并按任务组配置自动调度数据抓取。

    Clash 风格的任务组设计：每个 task-group 独立声明地点、类型、频率和输出方式，
    调度器统一负责执行与错误恢复，用户只需维护 config.yaml。

    典型用法::

        scheduler = HtMeteoScheduler("config.yaml")
        scheduler.run()          # 启动（一次性任务立即执行，定时任务进入循环）

        # 或单独执行一个任务组：
        scheduler.run_group("四川预报每日更新组")
    """

    def __init__(self, config_path: str = "config.yaml") -> None:
        self.config = HtMeteoConfig(config_path)
        self.logger = _setup_logging(self.config)
        self.logger.info(f"配置加载成功：{self.config}")

        # 用配置初始化 HtMeteo 实例（复用同一实例，避免重复登录）
        self._meteo = HtMeteo.from_config(self.config)

    # ── 公开接口 ───────────────────────────────────────────────────────────────

    def run(self) -> None:
        """
        按配置启动调度：
        - once 任务立即串行执行；
        - cron / interval 任务注册到 APScheduler 后进入阻塞循环。
        """
        once_groups = [
            tg for tg in self.config.enabled_task_groups
            if tg.schedule.type == "once"
        ]
        scheduled_groups = [
            tg for tg in self.config.enabled_task_groups
            if tg.schedule.type in ("cron", "interval")
        ]

        # 立即执行一次性任务
        for tg in once_groups:
            self._safe_run(tg)

        if not scheduled_groups:
            self.logger.info("没有需要持续调度的任务，程序退出。")
            return

        if not _HAS_APSCHEDULER:
            self.logger.error(
                "检测到 cron/interval 任务，但未安装 APScheduler。\n"
                "请执行：pip install apscheduler"
            )
            sys.exit(1)

        scheduler = BlockingScheduler(timezone=self.config.global_config.timezone)
        for tg in scheduled_groups:
            self._register(scheduler, tg)

        self.logger.info(f"调度器启动，共 {len(scheduled_groups)} 个定时任务，按 Ctrl+C 停止。")
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            self.logger.info("调度器已停止。")

    def run_group(self, name: str) -> None:
        """立即执行指定任务组（无视 schedule 配置，强制运行一次）。"""
        tg = self.config.get_task_group(name)
        if tg is None:
            self.logger.error(f"找不到任务组：{name!r}")
            available = [t.name for t in self.config.task_groups]
            self.logger.info(f"可用任务组：{available}")
            return
        self._safe_run(tg)

    # ── 调度注册 ───────────────────────────────────────────────────────────────

    def _register(self, scheduler: "BlockingScheduler", tg: TaskGroup) -> None:
        if tg.schedule.type == "cron":
            trigger = CronTrigger.from_crontab(
                tg.schedule.cron,
                timezone=self.config.global_config.timezone,
            )
            self.logger.info(f"注册 Cron 任务 [{tg.name}]，表达式：{tg.schedule.cron}")
        else:
            trigger = IntervalTrigger(seconds=tg.schedule.interval)
            self.logger.info(f"注册 Interval 任务 [{tg.name}]，间隔：{tg.schedule.interval}s")

        scheduler.add_job(
            self._safe_run,
            trigger,
            args=[tg],
            id=tg.name,
            name=tg.name,
            max_instances=1,          # 同一任务不重叠执行
            misfire_grace_time=300,   # 错过 5 分钟内仍可补跑
        )

    # ── 任务执行（含错误捕获）─────────────────────────────────────────────────

    def _safe_run(self, tg: TaskGroup) -> None:
        self.logger.info(f">> 开始执行任务组：[{tg.name}]（类型：{tg.type}）")
        try:
            _RUNNERS = {
                "history": self._run_history,
                "forecast": self._run_forecast,
                "fetch-all-forecast": self._run_fetch_all_forecast,
                "api-forecast": self._run_api_forecast,
                "api-history": self._run_api_history,
            }
            runner = _RUNNERS.get(tg.type)
            if runner is None:
                self.logger.warning(f"未知任务类型：{tg.type}，跳过。")
                return
            runner(tg)
            self.logger.info(f"[OK] 任务组 [{tg.name}] 执行完毕。")
        except Exception as exc:
            self.logger.error(f"[ERR] 任务组 [{tg.name}] 执行出错：{exc}", exc_info=True)

    # ── 各类型执行逻辑 ────────────────────────────────────────────────────────

    def _run_history(self, tg: TaskGroup) -> None:
        """下载并缓存逐小时历史数据 + 逐日/月/年统计分析数据。"""
        self._meteo.set_history_mode("on")
        self._meteo.set_forecast_mode("off")
        for location in tg.locations:
            self.logger.info(f"  拉取历史数据：{location}")
            self._meteo.set_location(location)

    def _run_forecast(self, tg: TaskGroup) -> None:
        """下载并缓存各地点最新天气预报数据。"""
        self._meteo.set_forecast_mode("on")
        self._meteo.set_history_mode("off")
        for location in tg.locations:
            self.logger.info(f"  拉取预报数据：{location}")
            self._meteo.set_location(location)
            if tg.output.to in ("database", "both") and self.config.database.enabled:
                df = self._meteo.forecast_hourly_series()
                self._write_to_db(df, location, "forecast_hourly", tg)

    def _run_fetch_all_forecast(self, tg: TaskGroup) -> None:
        """一次性拉取全国 3191 个城市最新预报 ZIP 包。"""
        self._meteo.set_forecast_mode("on")
        self._meteo.set_history_mode("off")
        self.logger.info("  开始拉取全国预报数据（ZIP）……")
        self._meteo.fetch_all_latest_forecast_data()

    def _run_api_forecast(self, tg: TaskGroup) -> None:
        """通过在线 API 直查逐小时天气预报，不落本地缓存。"""
        self._meteo.set_forecast_mode("off")
        self._meteo.set_history_mode("off")
        for location in tg.locations:
            self.logger.info(f"  API 查询预报：{location}")
            self._meteo.set_location(location)
            df: pd.DataFrame = self._meteo.api_forecast_hourly()
            if not isinstance(df, pd.DataFrame) or df.empty:
                self.logger.warning(f"  {location} API 返回空数据，跳过。")
                continue
            if tg.output.to in ("local", "both"):
                self._save_local(df, location, "api_forecast_hourly", tg)
            if tg.output.to in ("database", "both") and self.config.database.enabled:
                self._write_to_db(df, location, "forecast_hourly", tg)

    def _run_api_history(self, tg: TaskGroup) -> None:
        """通过在线 API 直查统计分析历史天气数据，不落本地缓存。"""
        self._meteo.set_forecast_mode("off")
        self._meteo.set_history_mode("off")
        time_type = tg.query.time_type if tg.query else "daily"
        for location in tg.locations:
            self.logger.info(f"  API 查询历史（{time_type}）：{location}")
            self._meteo.set_location(location)
            df: pd.DataFrame = self._meteo.api_history_analysis(time_type)
            if not isinstance(df, pd.DataFrame) or df.empty:
                self.logger.warning(f"  {location} API 返回空数据，跳过。")
                continue
            if tg.output.to in ("local", "both"):
                self._save_local(df, location, f"api_history_{time_type}", tg)
            if tg.output.to in ("database", "both") and self.config.database.enabled:
                self._write_to_db(df, location, f"history_analysis_{time_type}", tg)

    # ── 输出辅助 ──────────────────────────────────────────────────────────────

    def _save_local(self, df: pd.DataFrame, location: str,
                    label: str, tg: TaskGroup) -> None:
        """将 DataFrame 保存到本地文件（csv 或 parquet）。"""
        out_dir = Path(self.config.global_config.work_dir) / "api_output" / label
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
        if tg.output.format == "parquet":
            out_path = out_dir / f"{location}_{ts}.parquet"
            df.to_parquet(out_path, engine="pyarrow", compression="snappy")
        else:
            out_path = out_dir / f"{location}_{ts}.csv"
            df.to_csv(out_path, encoding="utf-8-sig")
        self.logger.info(f"  已保存本地文件：{out_path}")

    def _write_to_db(self, df: pd.DataFrame, location: str,
                     table_suffix: str, tg: TaskGroup) -> None:
        """将 DataFrame 写入 config 中配置的数据库（表不存在则自动建表后追加）。"""
        db = self.config.database
        # 表名 = 前缀 + 后缀，例如 ht_ + forecast_hourly => ht_forecast_hourly
        table_name = f"{db.table_prefix}{table_suffix}"
        self.logger.info(
            f"  [DB] 准备写入 {db.type}://{db.host}:{db.port}/{db.name}.{table_name} "
            f"地点={location} 行数={len(df)}"
        )
        try:
            write_dataframe_to_db(df, table_name, db, location)
        except Exception as e:
            self.logger.error(
                f"  [DB] 写入失败 地点={location} 表={table_name}: {e}",
                exc_info=True,
            )
            raise


# ── 命令行入口 ─────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="HtMeteo 配置驱动任务调度器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python scheduler.py                              # 按配置执行全部已启用任务
  python scheduler.py --group 四川预报每日更新组   # 立即执行指定任务组
  python scheduler.py --config my_config.yaml     # 使用指定配置文件
  python scheduler.py --list                      # 列出所有任务组
        """,
    )
    parser.add_argument(
        "--config", default="config.yaml", metavar="PATH",
        help="配置文件路径（默认：config.yaml）",
    )
    parser.add_argument(
        "--group", default=None, metavar="NAME",
        help="只执行指定名称的任务组（立即运行一次）",
    )
    parser.add_argument(
        "--list", action="store_true",
        help="列出配置文件中所有任务组并退出",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    if args.list:
        cfg = HtMeteoConfig(args.config)
        print(f"\n配置文件：{args.config}\n")
        print(f"{'#':<3} {'名称':<24} {'类型':<20} {'启用':<6} {'调度'}")
        print("-" * 72)
        for i, tg in enumerate(cfg.task_groups, 1):
            sched = tg.schedule.type
            if tg.schedule.cron:
                sched += f"({tg.schedule.cron})"
            elif tg.schedule.interval:
                sched += f"({tg.schedule.interval}s)"
            enabled_mark = "Y" if tg.enabled else "N"
            print(f"{i:<3} {tg.name:<24} {tg.type:<20} {enabled_mark:<6} {sched}")
        print()
        return

    scheduler = HtMeteoScheduler(args.config)

    if args.group:
        scheduler.run_group(args.group)
    else:
        scheduler.run()


if __name__ == "__main__":
    main()
