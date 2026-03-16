"""
app.py — HtMeteo 可视化控制台

启动方式：
    streamlit run app.py

所有配置均通过网页界面操作，修改后自动写回 config.yaml。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import streamlit as st
import yaml

st.set_page_config(
    page_title="HtMeteo 控制台",
    page_icon="🌤",
    layout="wide",
    initial_sidebar_state="expanded",
)

CONFIG_PATH = "config.yaml"
CONFIG_EXAMPLE_PATH = "config.example.yaml"
PYTHON_EXEC = sys.executable

if not Path(CONFIG_PATH).exists():
    if Path(CONFIG_EXAMPLE_PATH).exists():
        import shutil
        shutil.copy2(CONFIG_EXAMPLE_PATH, CONFIG_PATH)
        st.toast("已从 config.example.yaml 创建 config.yaml，请在【编辑配置】中填写账户和数据库信息。")
    else:
        st.error("找不到 config.yaml 和 config.example.yaml，请先创建配置文件。")
        st.stop()

TYPE_INFO: dict[str, tuple[str, str]] = {
    "history":            ("🗂", "历史数据"),
    "forecast":           ("🌤", "天气预报"),
    "fetch-all-forecast": ("🌍", "全国预报ZIP"),
    "api-forecast":       ("⚡", "API预报直查"),
    "api-history":        ("📡", "API历史直查"),
}

SCHEDULE_LABEL = {"once": "🔂 单次执行", "cron": "⏰ Cron 定时", "interval": "🔄 固定间隔"}
OUTPUT_LABEL = {"local": "💾 本地文件", "database": "🗄 数据库", "both": "💾🗄 本地+数据库"}

# ── 配置读写 ──────────────────────────────────────────────────────────────────

def load_raw() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_raw(data: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def save_and_reload(data: dict) -> None:
    save_raw(data)
    st.rerun()


# ── 子进程执行 ────────────────────────────────────────────────────────────────

def _stream_subprocess(group_name: str, out_box, status_box) -> bool:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.Popen(
        [PYTHON_EXEC, "-u", "task_runner.py",
         "--group", group_name, "--config", CONFIG_PATH],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", env=env, bufsize=1,
    )
    lines: list[str] = []
    for raw_line in proc.stdout:
        lines.append(raw_line.rstrip())
        out_box.code("\n".join(lines[-60:]), language="text")
    proc.wait()
    st.session_state.run_output = lines
    st.session_state.last_run_group = group_name
    st.session_state.last_run_ok = (proc.returncode == 0)
    if proc.returncode == 0:
        status_box.success(f"任务组「{group_name}」执行完毕！")
    else:
        status_box.error(f"任务组「{group_name}」执行出错（退出码 {proc.returncode}）")
    return proc.returncode == 0


# ── Session state ─────────────────────────────────────────────────────────────

for _k, _v in {"run_output": [], "last_run_group": None, "last_run_ok": None}.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ── 读取配置 ──────────────────────────────────────────────────────────────────

raw = load_raw()
task_groups_raw: list[dict] = raw.get("task-groups", []) or []
account_raw: dict = raw.get("account", {}) or {}
db_raw: dict = raw.get("database", {}) or {}
global_raw: dict = raw.get("global", {}) or {}

total_groups = len(task_groups_raw)
enabled_count = sum(1 for t in task_groups_raw if t.get("enabled", True))
total_locs = sum(len(t.get("locations", []) or []) for t in task_groups_raw)

# ════════════════════════════════════════════════════════════════════════════
# 侧边栏
# ════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("## 🌤 HtMeteo")
    st.caption("超级气象信息体 · 可视化控制台")
    st.divider()

    st.markdown("#### 👤 账户")
    uname = account_raw.get("username", "")
    if not uname or "example.com" in uname:
        st.warning("请在【编辑配置】中填写账户信息", icon="⚠")
    else:
        st.success(uname, icon="✅")

    st.markdown("#### 🗄 数据库")
    if db_raw.get("enabled"):
        st.info(f"{db_raw.get('type','mysql')}://{db_raw.get('host')}:{db_raw.get('port')}/{db_raw.get('name')}", icon="🟢")
    else:
        st.caption("未启用")

    st.divider()
    st.markdown("#### ⚙ 全局配置")
    st.caption(f"工作目录：`{global_raw.get('work_dir', './data')}`")
    st.caption(f"时区：`{global_raw.get('timezone', 'Asia/Shanghai')}`")
    st.divider()

    st.markdown("#### 📊 统计")
    c1, c2, c3 = st.columns(3)
    c1.metric("任务组", total_groups)
    c2.metric("启用", enabled_count)
    c3.metric("城市", total_locs)

    st.divider()
    with st.expander("📄 config.yaml 原文"):
        st.code(Path(CONFIG_PATH).read_text(encoding="utf-8"), language="yaml")


# ════════════════════════════════════════════════════════════════════════════
# 主体页面
# ════════════════════════════════════════════════════════════════════════════

st.markdown("# 🌤 HtMeteo 气象数据抓取控制台")

if st.session_state.last_run_group and st.session_state.last_run_ok is not None:
    _msg = f"上次执行：**{st.session_state.last_run_group}**"
    (st.success if st.session_state.last_run_ok else st.error)(
        _msg + ("  —  执行成功" if st.session_state.last_run_ok else "  —  执行出错"),
        icon="✅" if st.session_state.last_run_ok else "❌",
    )

tab_overview, tab_edit, tab_logs = st.tabs(["📊 任务总览", "✏ 编辑配置", "📋 运行日志"])


# ════════════════════════════════════════════════════════════════════════════
# Tab 1 — 任务总览 + 立即运行
# ════════════════════════════════════════════════════════════════════════════

with tab_overview:
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("任务组总数", total_groups)
    m2.metric("已启用", enabled_count)
    m3.metric("已禁用", total_groups - enabled_count)
    m4.metric("配置城市总数", total_locs)
    st.divider()

    if not task_groups_raw:
        st.info("暂无任务组，请前往【编辑配置】新建。", icon="ℹ")
    else:
        for tg_raw in task_groups_raw:
            name = tg_raw.get("name", "unnamed")
            ttype = tg_raw.get("type", "")
            enabled = tg_raw.get("enabled", True)
            locations = tg_raw.get("locations", []) or []
            meteo_types = tg_raw.get("meteo_types", []) or []
            sched = tg_raw.get("schedule", {}) or {}
            out = tg_raw.get("output", {}) or {}
            icon, label = TYPE_INFO.get(ttype, ("❓", ttype))
            dot = "🟢" if enabled else "🔴"

            with st.expander(f"{dot} **{name}**  —  {icon} {label}", expanded=False):
                info_col, btn_col = st.columns([6, 1])
                with info_col:
                    ca, cb, cc = st.columns([2, 3, 2])
                    with ca:
                        st.markdown("**调度方式**")
                        stype = sched.get("type", "once")
                        stxt = SCHEDULE_LABEL.get(stype, stype)
                        if stype == "cron" and sched.get("cron"):
                            stxt += f"\n`{sched['cron']}`"
                        elif stype == "interval" and sched.get("interval"):
                            stxt += f"\n每 {sched['interval']}s"
                        st.info(stxt, icon="⏱")
                        st.markdown("**输出**")
                        st.info(f"{OUTPUT_LABEL.get(out.get('to','local'),'')}\n格式：`{out.get('format','parquet')}`", icon="💾")
                    with cb:
                        st.markdown(f"**城市列表（{len(locations)} 个）**")
                        if locations:
                            for i in range(0, min(len(locations), 20), 4):
                                st.markdown("　".join(f"`{c}`" for c in locations[i:i+4]))
                            if len(locations) > 20:
                                st.caption(f"…… 共 {len(locations)} 个")
                        else:
                            st.caption("未指定（由任务类型决定）")
                    with cc:
                        st.markdown("**气象要素**")
                        if meteo_types:
                            st.metric("要素种数", len(meteo_types))
                        else:
                            st.info("全部要素（默认）", icon="🌡")
                with btn_col:
                    st.markdown("<br><br>", unsafe_allow_html=True)
                    if enabled:
                        run_clicked = st.button("▶ 立即运行", key=f"run_{name}", type="primary", use_container_width=True)
                    else:
                        st.button("已禁用", key=f"run_{name}", disabled=True, use_container_width=True)
                        run_clicked = False
                if run_clicked:
                    st.divider()
                    st.markdown(f"**正在执行：{name}**")
                    ob = st.empty()
                    sb = st.empty()
                    ob.code("等待任务启动……", language="text")
                    with st.spinner("执行中……"):
                        _stream_subprocess(name, ob, sb)


# ════════════════════════════════════════════════════════════════════════════
# Tab 2 — 编辑配置（完整 CRUD）
# ════════════════════════════════════════════════════════════════════════════

with tab_edit:

    # ── 2-A：全局 / 账户 / 数据库 设置 ────────────────────────────────────────
    st.markdown("### ⚙ 全局 / 账户 / 数据库 设置")

    with st.form("form_global", clear_on_submit=False):
        ga, gb, gc = st.columns(3)

        with ga:
            st.markdown("**全局**")
            g_work_dir = st.text_input("工作目录", value=global_raw.get("work_dir", "./data"))
            g_timezone = st.text_input("时区", value=global_raw.get("timezone", "Asia/Shanghai"))
            g_log_file = st.text_input("日志文件", value=global_raw.get("log_file", "./logs/htmeteo.log"))
            g_log_level = st.selectbox("日志等级", ["DEBUG", "INFO", "WARNING", "ERROR"],
                                       index=["DEBUG", "INFO", "WARNING", "ERROR"].index(
                                           global_raw.get("log_level", "INFO")))

        with gb:
            st.markdown("**海天气象账户**")
            a_user = st.text_input("用户名（邮箱）", value=account_raw.get("username", ""))
            a_pass = st.text_input("密码", value=account_raw.get("password", ""), type="password")

        with gc:
            st.markdown("**数据库**")
            d_enabled = st.checkbox("启用数据库写入", value=db_raw.get("enabled", False))
            d_type = st.selectbox("类型", ["mysql", "postgresql", "sqlite"],
                                  index=["mysql", "postgresql", "sqlite"].index(db_raw.get("type", "mysql")))
            d_host = st.text_input("主机", value=db_raw.get("host", "localhost"))
            d_port = st.number_input("端口", value=int(db_raw.get("port", 3306)), min_value=1, max_value=65535)
            d_user = st.text_input("数据库用户", value=db_raw.get("user", "root"))
            d_pass = st.text_input("数据库密码", value=db_raw.get("password", ""), type="password")
            d_name = st.text_input("数据库名", value=db_raw.get("name", "weather"))
            d_prefix = st.text_input("表名前缀", value=db_raw.get("table_prefix", "ht_"),
                                     help="表名 = 前缀 + 后缀，如 weather_ => weather_forecast_hourly")

        save_global = st.form_submit_button("💾 保存全局设置", type="primary")
        if save_global:
            fresh = load_raw()
            fresh["global"] = {"work_dir": g_work_dir, "log_level": g_log_level,
                               "log_file": g_log_file, "timezone": g_timezone}
            fresh["account"] = {"username": a_user, "password": a_pass}
            fresh["database"] = {"enabled": d_enabled, "type": d_type, "host": d_host,
                                 "port": int(d_port), "user": d_user, "password": d_pass,
                                 "name": d_name, "table_prefix": d_prefix,
                                 "pool_size": db_raw.get("pool_size", 5)}
            save_and_reload(fresh)

    st.divider()

    # ── 2-B：管理现有任务组（编辑 / 删除 / 启用禁用）──────────────────────────

    st.markdown("### 📝 管理任务组")

    if not task_groups_raw:
        st.info("暂无任务组，请在下方新建。", icon="ℹ")
    else:
        for idx, tg in enumerate(task_groups_raw):
            g_name = tg.get("name", "unnamed")
            g_type = tg.get("type", "")
            g_enabled = tg.get("enabled", True)
            g_locs = tg.get("locations", []) or []
            g_sched = tg.get("schedule", {}) or {}
            g_out = tg.get("output", {}) or {}
            icon, label = TYPE_INFO.get(g_type, ("❓", g_type))
            dot = "🟢" if g_enabled else "🔴"

            with st.expander(f"{dot} {icon} **{g_name}** — {label}（{len(g_locs)} 个城市）"):

                # ── 删除按钮 + 启用开关 ──────────────────────────────────
                top_a, top_b, top_c = st.columns([1, 1, 5])
                with top_a:
                    if st.button("🗑 删除此任务组", key=f"del_group_{idx}", type="secondary"):
                        fresh = load_raw()
                        groups = fresh.get("task-groups", [])
                        groups[:] = [g for g in groups if g.get("name") != g_name]
                        save_and_reload(fresh)
                with top_b:
                    new_enabled = st.toggle("启用", value=g_enabled, key=f"en_{idx}")
                    if new_enabled != g_enabled:
                        fresh = load_raw()
                        for t in fresh.get("task-groups", []):
                            if t.get("name") == g_name:
                                t["enabled"] = new_enabled
                        save_and_reload(fresh)

                st.divider()

                # ── 编辑表单 ─────────────────────────────────────────────
                with st.form(f"edit_{idx}", clear_on_submit=False):
                    ea, eb = st.columns(2)

                    with ea:
                        e_name = st.text_input("任务组名称", value=g_name, key=f"ename_{idx}")
                        type_keys = list(TYPE_INFO.keys())
                        e_type = st.selectbox(
                            "数据类型", type_keys,
                            index=type_keys.index(g_type) if g_type in type_keys else 0,
                            format_func=lambda k: f"{TYPE_INFO[k][0]} {TYPE_INFO[k][1]}",
                            key=f"etype_{idx}",
                        )
                        e_locs_text = st.text_area(
                            "城市列表（每行一个）",
                            value="\n".join(g_locs),
                            height=150,
                            key=f"elocs_{idx}",
                        )

                    with eb:
                        sched_opts = ["once", "cron", "interval"]
                        cur_stype = g_sched.get("type", "once")
                        e_sched_type = st.selectbox(
                            "执行方式", sched_opts,
                            index=sched_opts.index(cur_stype) if cur_stype in sched_opts else 0,
                            format_func=lambda x: {"once": "🔂 单次执行", "cron": "⏰ Cron 定时", "interval": "🔄 固定间隔"}[x],
                            key=f"estype_{idx}",
                        )
                        e_cron = st.text_input("Cron 表达式", value=g_sched.get("cron", ""),
                                               key=f"ecron_{idx}", disabled=(e_sched_type != "cron"))
                        e_interval = st.number_input("间隔（秒）", value=int(g_sched.get("interval", 3600)),
                                                     min_value=60, step=300, key=f"eiv_{idx}",
                                                     disabled=(e_sched_type != "interval"))

                        out_opts = ["local", "database", "both"]
                        cur_out_to = g_out.get("to", "local")
                        e_out_to = st.selectbox(
                            "输出目标", out_opts,
                            index=out_opts.index(cur_out_to) if cur_out_to in out_opts else 0,
                            format_func=lambda x: OUTPUT_LABEL.get(x, x),
                            key=f"eoutto_{idx}",
                        )
                        fmt_opts = ["parquet", "csv"]
                        cur_fmt = g_out.get("format", "parquet")
                        e_out_fmt = st.selectbox(
                            "文件格式", fmt_opts,
                            index=fmt_opts.index(cur_fmt) if cur_fmt in fmt_opts else 0,
                            key=f"efmt_{idx}",
                        )

                    save_edit = st.form_submit_button("💾 保存修改", type="primary")
                    if save_edit:
                        new_locs = [l.strip() for l in e_locs_text.strip().splitlines() if l.strip()]
                        new_sched: dict = {"type": e_sched_type}
                        if e_sched_type == "cron":
                            new_sched["cron"] = e_cron.strip()
                        elif e_sched_type == "interval":
                            new_sched["interval"] = int(e_interval)

                        fresh = load_raw()
                        for t in fresh.get("task-groups", []):
                            if t.get("name") == g_name:
                                t["name"] = e_name.strip() or g_name
                                t["type"] = e_type
                                t["locations"] = new_locs
                                t["schedule"] = new_sched
                                t["output"] = {"to": e_out_to, "format": e_out_fmt}
                                break
                        save_and_reload(fresh)

    st.divider()

    # ── 2-C：新建任务组 ───────────────────────────────────────────────────────

    st.markdown("### 🆕 新建任务组")

    with st.form("form_new_group", clear_on_submit=True):
        na, nb = st.columns(2)
        with na:
            f_name = st.text_input("任务组名称 *", placeholder="例：长三角历史气象组")
            f_type = st.selectbox("数据类型 *", list(TYPE_INFO.keys()),
                                  format_func=lambda k: f"{TYPE_INFO[k][0]} {TYPE_INFO[k][1]}")
            f_locs = st.text_area("城市列表（每行一个）", placeholder="南京市\n上海市\n杭州市", height=130)
            f_enabled = st.checkbox("创建后立即启用", value=True)
        with nb:
            f_stype = st.selectbox("执行方式 *", ["once", "cron", "interval"],
                                   format_func=lambda x: {"once": "🔂 单次执行", "cron": "⏰ Cron 定时", "interval": "🔄 固定间隔"}[x])
            f_cron = st.text_input("Cron 表达式", placeholder="0 6 * * *", disabled=(f_stype != "cron"))
            f_iv = st.number_input("间隔（秒）", min_value=60, value=3600, step=300, disabled=(f_stype != "interval"))
            f_out_to = st.selectbox("输出目标", ["local", "database", "both"],
                                    format_func=lambda x: OUTPUT_LABEL.get(x, x))
            f_out_fmt = st.selectbox("文件格式", ["parquet", "csv"])

        submitted = st.form_submit_button("✅ 创建任务组", type="primary")
        if submitted:
            errs = []
            if not f_name.strip():
                errs.append("名称不能为空。")
            if f_name.strip() in [t.get("name") for t in task_groups_raw]:
                errs.append(f"「{f_name.strip()}」已存在。")
            if f_stype == "cron" and not f_cron.strip():
                errs.append("Cron 模式须填写表达式。")
            if errs:
                for e in errs:
                    st.error(e)
            else:
                new_sched: dict = {"type": f_stype}
                if f_stype == "cron":
                    new_sched["cron"] = f_cron.strip()
                elif f_stype == "interval":
                    new_sched["interval"] = int(f_iv)

                new_tg = {
                    "name": f_name.strip(),
                    "type": f_type,
                    "enabled": f_enabled,
                    "locations": [l.strip() for l in f_locs.strip().splitlines() if l.strip()],
                    "meteo_types": [],
                    "schedule": new_sched,
                    "output": {"to": f_out_to, "format": f_out_fmt},
                }
                fresh = load_raw()
                if not isinstance(fresh.get("task-groups"), list):
                    fresh["task-groups"] = []
                fresh["task-groups"].append(new_tg)
                save_and_reload(fresh)


# ════════════════════════════════════════════════════════════════════════════
# Tab 3 — 运行日志
# ════════════════════════════════════════════════════════════════════════════

with tab_logs:
    st.markdown("### 🕐 本次会话执行记录")
    if st.session_state.run_output:
        ia, ib, ic = st.columns([3, 2, 1])
        ia.markdown(f"**任务组：** {st.session_state.last_run_group or '未知'}")
        ib.markdown(f"**状态：** {'成功 ✅' if st.session_state.last_run_ok else '失败 ❌'}")
        ic.markdown(f"**行数：** {len(st.session_state.run_output)}")
        st.code("\n".join(st.session_state.run_output), language="text")
        if st.button("清除本次记录", key="clear_log"):
            st.session_state.run_output = []
            st.session_state.last_run_group = None
            st.session_state.last_run_ok = None
            st.rerun()
    else:
        st.info("本次会话尚未执行任何任务。", icon="ℹ")

    st.divider()
    st.markdown("### 📄 持久化日志文件")
    log_path = Path(global_raw.get("log_file", "./logs/htmeteo.log"))
    st.caption(f"路径：`{log_path.resolve()}`")
    if log_path.exists():
        la, lb, _ = st.columns([1, 2, 4])
        with la:
            if st.button("🔄 刷新"):
                st.rerun()
        with lb:
            n_lines = st.selectbox("行数", [50, 100, 200, 500, 1000], index=1, label_visibility="collapsed")
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        st.code("".join(all_lines[-n_lines:]), language="text")
        st.caption(f"共 {len(all_lines)} 行，显示最后 {n_lines} 行")
    else:
        st.info(f"日志文件尚不存在：`{log_path}`", icon="ℹ")
