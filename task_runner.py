"""
task_runner.py — HtMeteo 核心任务执行模块

既可被 scheduler.py / app.py 导入调用，也可独立通过 CLI 运行：

    python task_runner.py --group "任务组名" [--config config.yaml]

子进程模式下，所有日志写入 stdout，由调用方（app.py）逐行捕获并实时展示。
"""
from __future__ import annotations

import argparse
import logging
import sys
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from config_loader import HtMeteoConfig, TaskGroup
    from HtMeteo import HtMeteo


# ── 日志 ──────────────────────────────────────────────────────────────────────

def _build_logger() -> logging.Logger:
    """构建行缓冲日志记录器，确保子进程模式下每行立即输出。"""
    logger = logging.getLogger("task_runner")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)-5s] %(message)s",
                              datefmt="%H:%M:%S")
        )
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


logger = _build_logger()


# ── 各类型执行实现 ─────────────────────────────────────────────────────────────

def _run_history(tg: "TaskGroup", meteo: "HtMeteo", config: "HtMeteoConfig | None" = None) -> None:
    """下载缓存逐小时历史数据 + 逐日/月/年统计分析数据。"""
    meteo.set_history_mode("on")
    meteo.set_forecast_mode("off")
    total = len(tg.locations)
    for idx, loc in enumerate(tg.locations, 1):
        logger.info(f"[{idx}/{total}] [历史] 拉取：{loc}")
        meteo.set_location(loc)
    logger.info(f"[历史] 全部完成，共 {total} 个地点。")


def _run_forecast(tg: "TaskGroup", meteo: "HtMeteo", config: "HtMeteoConfig | None" = None) -> None:
    """下载缓存各地点最新天气预报（本地 CSV），可选写库。"""
    meteo.set_forecast_mode("on")
    meteo.set_history_mode("off")
    total = len(tg.locations)
    for idx, loc in enumerate(tg.locations, 1):
        logger.info(f"[{idx}/{total}] [预报] 拉取：{loc}")
        meteo.set_location(loc)
        if config and config.database.enabled and tg.output.to in ("database", "both"):
            try:
                from db_writer import write_dataframe_to_db
                df = meteo.forecast_hourly_series()
                logger.info(f"  [DB] 读取到 DataFrame：{len(df)} 行 × {len(df.columns)} 列")
                if len(df) > 0:
                    logger.info(f"  [DB] 时间范围：{df.index[0]} ~ {df.index[-1]}")
                table_name = f"{config.database.table_prefix}forecast_hourly"
                write_dataframe_to_db(df, table_name, config.database, loc)
            except Exception as e:
                logger.error(f"  [DB] 写入失败 地点={loc}: {e}", exc_info=True)
    logger.info(f"[预报] 全部完成，共 {total} 个地点。")


def _run_fetch_all_forecast(tg: "TaskGroup", meteo: "HtMeteo", config: "HtMeteoConfig | None" = None) -> None:
    """一次性下载全国 3191 城市最新预报 ZIP 包。"""
    meteo.set_forecast_mode("on")
    meteo.set_history_mode("off")
    logger.info("[全国预报] 开始下载 ZIP 包，数据量较大，请耐心等待……")
    meteo.fetch_all_latest_forecast_data()
    logger.info("[全国预报] 下载完毕。")


def _run_api_forecast(tg: "TaskGroup", meteo: "HtMeteo", config: "HtMeteoConfig | None" = None) -> None:
    """通过在线 API 直查逐小时天气预报，不落本地缓存，可选写库。"""
    meteo.set_forecast_mode("off")
    meteo.set_history_mode("off")
    total = len(tg.locations)
    ok_count = 0
    for idx, loc in enumerate(tg.locations, 1):
        logger.info(f"[{idx}/{total}] [API预报] 查询：{loc}")
        meteo.set_location(loc)
        df = meteo.api_forecast_hourly()
        if isinstance(df, pd.DataFrame) and not df.empty:
            logger.info(f"  -> OK  {len(df)} 行 x {len(df.columns)} 列")
            ok_count += 1
            if config and config.database.enabled and tg.output.to in ("database", "both"):
                try:
                    from db_writer import write_dataframe_to_db
                    table_name = f"{config.database.table_prefix}forecast_hourly"
                    write_dataframe_to_db(df, table_name, config.database, loc)
                except Exception as e:
                    logger.error(f"  [DB] 写入失败 地点={loc}: {e}", exc_info=True)
        else:
            logger.warning(f"  -> WARN 返回空数据")
    logger.info(f"[API预报] 全部完成，有效 {ok_count}/{total} 个地点。")


def _run_api_history(tg: "TaskGroup", meteo: "HtMeteo", config: "HtMeteoConfig | None" = None) -> None:
    """通过在线 API 直查统计分析历史天气，不落本地缓存，可选写库。"""
    meteo.set_forecast_mode("off")
    meteo.set_history_mode("off")
    time_type = tg.query.time_type if tg.query else "daily"
    total = len(tg.locations)
    ok_count = 0
    for idx, loc in enumerate(tg.locations, 1):
        logger.info(f"[{idx}/{total}] [API历史/{time_type}] 查询：{loc}")
        meteo.set_location(loc)
        df = meteo.api_history_analysis(time_type)
        if isinstance(df, pd.DataFrame) and not df.empty:
            logger.info(f"  -> OK  {len(df)} 行 x {len(df.columns)} 列")
            ok_count += 1
            if config and config.database.enabled and tg.output.to in ("database", "both"):
                try:
                    from db_writer import write_dataframe_to_db
                    table_name = f"{config.database.table_prefix}history_analysis_{time_type}"
                    write_dataframe_to_db(df, table_name, config.database, loc)
                except Exception as e:
                    logger.error(f"  [DB] 写入失败 地点={loc}: {e}", exc_info=True)
        else:
            logger.warning(f"  -> WARN 返回空数据")
    logger.info(f"[API历史] 全部完成，有效 {ok_count}/{total} 个地点。")


_RUNNERS = {
    "history":            _run_history,
    "forecast":           _run_forecast,
    "fetch-all-forecast": _run_fetch_all_forecast,
    "api-forecast":       _run_api_forecast,
    "api-history":        _run_api_history,
}


# ── 公开接口（供 scheduler.py / app.py 导入）──────────────────────────────────

def run_task_group(tg: "TaskGroup", meteo: "HtMeteo", config: "HtMeteoConfig | None" = None) -> None:
    """
    同步执行单个任务组。

    :param tg: 已解析的 ``TaskGroup`` 数据类实例。
    :param meteo: 已初始化的 ``HtMeteo`` 实例（复用，避免重复登录）。
    :param config: 可选；传入时若任务组 output.to 为 database/both 且 database.enabled，会写入数据库。
    """
    runner = _RUNNERS.get(tg.type)
    if runner is None:
        logger.warning(f"未知任务类型：{tg.type!r}，跳过。")
        return
    runner(tg, meteo, config)


# ── CLI 入口（供 app.py 通过 subprocess 调用）────────────────────────────────

def main() -> None:
    # 强制行缓冲，使调用方能实时捕获每行输出
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except AttributeError:
        pass

    parser = argparse.ArgumentParser(
        description="HtMeteo 任务执行器（可被 app.py 子进程调用）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--config", default="config.yaml", metavar="PATH",
                        help="配置文件路径（默认：config.yaml）")
    parser.add_argument("--group", required=True, metavar="NAME",
                        help="要执行的任务组名称")
    args = parser.parse_args()

    # 延迟导入，避免 app.py 只 import task_runner 时触发不必要的初始化
    from config_loader import HtMeteoConfig
    from HtMeteo import HtMeteo

    cfg = HtMeteoConfig(args.config)
    tg = cfg.get_task_group(args.group)
    if tg is None:
        logger.error(f"找不到任务组：{args.group!r}")
        available = [t.name for t in cfg.task_groups]
        logger.info(f"可用任务组：{available}")
        sys.exit(1)

    meteo = HtMeteo.from_config(cfg)
    logger.info(f"{'=' * 50}")
    logger.info(f"开始执行任务组：{tg.name}  类型：{tg.type}")
    logger.info(f"地点数量：{len(tg.locations)}  调度：{tg.schedule.type}")
    logger.info(f"{'=' * 50}")

    try:
        run_task_group(tg, meteo, config=cfg)
        logger.info(f"{'=' * 50}")
        logger.info(f"任务组执行完毕：{tg.name}")
        logger.info(f"{'=' * 50}")
    except Exception as exc:
        logger.error(f"任务组执行出错：{exc}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
