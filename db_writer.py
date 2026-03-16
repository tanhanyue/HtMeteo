"""
db_writer.py — 将气象 DataFrame 写入 config 中配置的数据库

支持 MySQL（含兼容 MySQL 协议的其他库，如 Doris）。
Doris 需先在库中执行 docs/doris_forecast_hourly.sql 建表后再写入。
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from config_loader import DatabaseConfig

logger = logging.getLogger(__name__)

# 建表说明文档路径，用于错误提示
DORIS_DDL_HINT = "请先在 Doris 中执行项目 docs/doris_forecast_hourly.sql 建表，并确认 config.yaml 中 database 的库名、表名前缀正确。"


def _build_mysql_url(db: "DatabaseConfig") -> str:
    """构建 MySQL 连接 URL，对密码中的特殊字符进行编码。"""
    from urllib.parse import quote_plus
    user = quote_plus(db.user)
    password = quote_plus(db.password)
    return (
        f"mysql+pymysql://{user}:{password}"
        f"@{db.host}:{db.port}/{db.name}"
    )


def _wrap_connection_error(e: Exception, db: "DatabaseConfig") -> str:
    """将连接类异常转为中文提示。"""
    msg = str(e).strip()
    return (
        "无法连接数据库，请检查：\n"
        f"  1) config.yaml 中 database.host={db.host}、port={db.port}、name={db.name} 是否正确；\n"
        "  2) 用户名、密码是否正确；\n"
        "  3) 本机网络是否能访问数据库（防火墙、白名单等）。\n"
        f"原始错误：{msg}"
    )


def _wrap_table_not_found_error(e: Exception, table_name: str) -> str:
    """表不存在时给出建表提示。"""
    return (
        f"表 {table_name} 不存在，无法写入。\n"
        f"{DORIS_DDL_HINT}\n"
        f"原始错误：{e}"
    )


def write_dataframe_to_db(
    df: pd.DataFrame,
    table_name: str,
    db: "DatabaseConfig",
    location: str,
) -> int:
    """
    将 DataFrame 写入数据库指定表。

    - 表必须已存在（Doris 需先用 docs/doris_forecast_hourly.sql 建表）。
    - 会为每行增加 location 列；若 DataFrame 索引为时间，会 reset_index 成 date 列。
    - 连接失败或表不存在时会抛出带中文说明的异常。
    """
    from sqlalchemy import create_engine
    from sqlalchemy.exc import OperationalError, ProgrammingError

    if df is None or df.empty:
        logger.warning("[DB] DataFrame 为空，跳过写入。")
        return 0

    # 副本，避免修改原 DataFrame
    out = df.copy()
    # 将索引转为列（常见为 date）
    if out.index.name is not None or not out.index.equals(pd.RangeIndex(len(out))):
        out = out.reset_index()
    out["location"] = location

    # 兼容 datetime 带时区：转为 naive 再写库
    for col in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[col]):
            ser = out[col]
            if hasattr(ser.dtype, "tz") and ser.dtype.tz is not None:
                out[col] = pd.to_datetime(ser, utc=True).dt.tz_localize(None)

    url = _build_mysql_url(db)
    try:
        engine = create_engine(url, pool_size=db.pool_size, pool_pre_ping=True)
    except Exception as e:
        raise RuntimeError(_wrap_connection_error(e, db)) from e

    try:
        n = len(out)
        out.to_sql(
            table_name,
            engine,
            if_exists="append",
            index=False,
            method="multi",
            chunksize=1000,
        )
        logger.info(f"  [DB] 写入完成：{n} 行 → {table_name} 地点={location}")
        return n
    except OperationalError as e:
        err_msg = str(e).lower()
        # 连接失败（无法连上、超时、拒绝等）
        if "can't connect" in err_msg or "connection" in err_msg or "refused" in err_msg or "timeout" in err_msg or "2003" in err_msg:
            raise RuntimeError(_wrap_connection_error(e, db)) from e
        # 表不存在（Doris/MySQL 等）
        if "doesn't exist" in err_msg or "not exist" in err_msg or "1146" in err_msg or "unknown table" in err_msg:
            raise RuntimeError(_wrap_table_not_found_error(e, table_name)) from e
        raise
    except ProgrammingError as e:
        err_msg = str(e).lower()
        if "doesn't exist" in err_msg or "not exist" in err_msg or "1146" in err_msg or "unknown table" in err_msg:
            raise RuntimeError(_wrap_table_not_found_error(e, table_name)) from e
        raise
