"""
app.py — HtMeteo 可视化控制台

启动方式：
    streamlit run app.py

功能：
  - 侧边栏：账户状态、数据库状态、全局配置概览
  - Tab 1 [任务总览]：所有任务组卡片，含"立即运行"按钮和实时日志流
  - Tab 2 [编辑配置]：添加城市、新建任务组、启用/禁用开关
  - Tab 3 [运行日志]：本次会话执行记录 + 持久化日志文件查看器
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import streamlit as st
import yaml

# ── 必须是第一个 Streamlit 调用 ───────────────────────────────────────────────
st.set_page_config(
    page_title="HtMeteo 控制台",
    page_icon="🌤",
    layout="wide",
    initial_sidebar_state="expanded",
)

CONFIG_PATH = "config.yaml"
PYTHON_EXEC = sys.executable

# ── 常量：任务类型元数据 ──────────────────────────────────────────────────────
TYPE_INFO: dict[str, tuple[str, str, str]] = {
    # key: (icon, 中文标签, badge颜色)
    "history":            ("🗂", "历史数据",    "blue"),
    "forecast":           ("🌤", "天气预报",    "orange"),
    "fetch-all-forecast": ("🌍", "全国预报ZIP", "green"),
    "api-forecast":       ("⚡", "API预报直查", "violet"),
    "api-history":        ("📡", "API历史直查", "red"),
}

SCHEDULE_LABEL = {
    "once":     "🔂 单次执行",
    "cron":     "⏰ Cron 定时",
    "interval": "🔄 固定间隔",
}

OUTPUT_LABEL = {
    "local":    "💾 本地文件",
    "database": "🗄 数据库",
    "both":     "💾🗄 本地 + 数据库",
}


# ── 配置读写 ──────────────────────────────────────────────────────────────────

@st.cache_data(ttl=2)
def _cached_load_raw(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_raw() -> dict:
    return _cached_load_raw(CONFIG_PATH)


def save_raw(data: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    _cached_load_raw.clear()


def reload() -> None:
    """清除缓存并触发页面刷新。"""
    _cached_load_raw.clear()
    st.rerun()


# ── 任务执行（子进程 + 实时流式输出）─────────────────────────────────────────

def _stream_subprocess(group_name: str, out_box, status_box) -> bool:
    """
    通过 task_runner.py 子进程执行任务组，将 stdout 实时流入 out_box。
    返回 True 表示成功退出（returncode == 0）。
    """
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    proc = subprocess.Popen(
        [PYTHON_EXEC, "-u", "task_runner.py",
         "--group", group_name, "--config", CONFIG_PATH],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        bufsize=1,
    )

    lines: list[str] = []
    for raw_line in proc.stdout:
        lines.append(raw_line.rstrip())
        # 实时更新输出框（显示最新 60 行）
        out_box.code("\n".join(lines[-60:]), language="text")

    proc.wait()

    # 持久化到 session_state 供"运行日志"Tab 查看
    st.session_state.run_output = lines
    st.session_state.last_run_group = group_name
    st.session_state.last_run_ok = (proc.returncode == 0)

    if proc.returncode == 0:
        status_box.success(f"任务组「{group_name}」执行完毕！")
    else:
        status_box.error(
            f"任务组「{group_name}」执行出错（退出码 {proc.returncode}），请查看上方日志。"
        )
    return proc.returncode == 0


# ── Session state 初始化 ──────────────────────────────────────────────────────

defaults = {
    "run_output": [],
    "last_run_group": None,
    "last_run_ok": None,
}
for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val


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

    # 账户状态
    st.markdown("#### 👤 账户")
    username = account_raw.get("username", "")
    is_placeholder = (
        not username
        or "example.com" in username
        or username == "your_email@example.com"
    )
    if is_placeholder:
        st.warning("请在 config.yaml 中填写真实账户信息。", icon="⚠")
    else:
        st.success(username, icon="✅")

    # 数据库状态
    st.markdown("#### 🗄 数据库")
    db_enabled = db_raw.get("enabled", False)
    if db_enabled:
        db_str = (
            f"{db_raw.get('type','mysql')}://"
            f"{db_raw.get('host','localhost')}:{db_raw.get('port',3306)}"
            f"/{db_raw.get('name','weather')}"
        )
        st.info(db_str, icon="🟢")
    else:
        st.caption("未启用（可在 config.yaml 中开启）")

    st.divider()

    # 全局配置摘要
    st.markdown("#### ⚙ 全局配置")
    st.caption(f"工作目录：`{global_raw.get('work_dir', './data')}`")
    st.caption(f"时　　区：`{global_raw.get('timezone', 'Asia/Shanghai')}`")
    st.caption(f"日志文件：`{global_raw.get('log_file', './logs/htmeteo.log')}`")

    st.divider()

    # 快速统计
    st.markdown("#### 📊 任务统计")
    c1, c2, c3 = st.columns(3)
    c1.metric("总数", total_groups)
    c2.metric("启用", enabled_count)
    c3.metric("城市", total_locs)

    st.divider()

    # 原始 YAML 预览
    with st.expander("📄 查看 config.yaml 原文"):
        raw_text = Path(CONFIG_PATH).read_text(encoding="utf-8")
        st.code(raw_text, language="yaml")


# ════════════════════════════════════════════════════════════════════════════
# 主体页面
# ════════════════════════════════════════════════════════════════════════════

st.markdown("# 🌤 HtMeteo 气象数据抓取控制台")

# 上次运行结果横幅
if st.session_state.last_run_group and st.session_state.last_run_ok is not None:
    _msg = f"上次执行：**{st.session_state.last_run_group}**"
    if st.session_state.last_run_ok:
        st.success(_msg + "  —  执行成功", icon="✅")
    else:
        st.error(_msg + "  —  执行出错，请检查运行日志", icon="❌")

tab_overview, tab_edit, tab_logs = st.tabs(
    ["📊 任务总览", "✏ 编辑配置", "📋 运行日志"]
)


# ════════════════════════════════════════════════════════════════════════════
# Tab 1 — 任务总览
# ════════════════════════════════════════════════════════════════════════════

with tab_overview:
    # 指标行
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("任务组总数", total_groups)
    m2.metric("已启用", enabled_count)
    m3.metric("已禁用", total_groups - enabled_count)
    m4.metric("配置城市总数", total_locs)

    st.divider()

    if not task_groups_raw:
        st.info("暂无任务组。请前往【编辑配置】标签页新建第一个任务组。", icon="ℹ")
    else:
        for tg_raw in task_groups_raw:
            name: str = tg_raw.get("name", "unnamed")
            ttype: str = tg_raw.get("type", "")
            enabled: bool = tg_raw.get("enabled", True)
            locations: list = tg_raw.get("locations", []) or []
            meteo_types: list = tg_raw.get("meteo_types", []) or []
            sched: dict = tg_raw.get("schedule", {}) or {}
            out: dict = tg_raw.get("output", {}) or {}

            icon, label, _ = TYPE_INFO.get(ttype, ("❓", ttype, "gray"))
            status_dot = "🟢" if enabled else "🔴"

            with st.expander(
                f"{status_dot} **{name}**  —  {icon} {label}",
                expanded=False,
            ):
                # ── 上半：信息区 ─────────────────────────────────────────────
                info_col, btn_col = st.columns([6, 1])

                with info_col:
                    col_sched, col_locs, col_types = st.columns([2, 3, 2])

                    with col_sched:
                        st.markdown("**调度方式**")
                        stype = sched.get("type", "once")
                        sched_text = SCHEDULE_LABEL.get(stype, stype)
                        if stype == "cron" and sched.get("cron"):
                            sched_text += f"\n`{sched['cron']}`"
                        elif stype == "interval" and sched.get("interval"):
                            iv = sched["interval"]
                            sched_text += f"\n每 {iv}s（{iv // 60} min）"
                        st.info(sched_text, icon="⏱")

                        st.markdown("**输出配置**")
                        out_label = OUTPUT_LABEL.get(out.get("to", "local"), out.get("to", ""))
                        out_fmt = out.get("format", "parquet")
                        st.info(f"{out_label}\n格式：`{out_fmt}`", icon="💾")

                    with col_locs:
                        st.markdown(f"**城市列表（{len(locations)} 个）**")
                        if locations:
                            # 每行最多 4 个城市，最多显示 5 行（20 个）
                            preview = locations[:20]
                            rows = [preview[i:i+4] for i in range(0, len(preview), 4)]
                            for row in rows:
                                st.markdown("　".join(f"`{c}`" for c in row))
                            if len(locations) > 20:
                                st.caption(f"…… 等共 **{len(locations)}** 个地点")
                        else:
                            st.caption("未指定城市（由任务类型决定范围）")

                    with col_types:
                        st.markdown("**气象要素**")
                        if meteo_types:
                            st.metric("要素种数", len(meteo_types))
                            with st.expander("展开查看"):
                                for mt in meteo_types:
                                    st.code(mt, language=None)
                        else:
                            st.info("全部要素（默认）", icon="🌡")

                with btn_col:
                    st.markdown("<br><br>", unsafe_allow_html=True)
                    if enabled:
                        run_clicked = st.button(
                            "▶ 立即运行",
                            key=f"run_{name}",
                            type="primary",
                            use_container_width=True,
                        )
                    else:
                        st.button(
                            "已禁用",
                            key=f"run_{name}",
                            disabled=True,
                            use_container_width=True,
                        )
                        run_clicked = False

                # ── 下半：运行输出（仅在点击后渲染）───────────────────────────
                if run_clicked:
                    st.divider()
                    st.markdown(f"**正在执行任务组：{name}**")
                    out_box = st.empty()
                    status_box = st.empty()
                    out_box.code("等待任务启动……", language="text")
                    with st.spinner("执行中，请勿关闭页面……"):
                        _stream_subprocess(name, out_box, status_box)


# ════════════════════════════════════════════════════════════════════════════
# Tab 2 — 编辑配置
# ════════════════════════════════════════════════════════════════════════════

with tab_edit:

    # ── Section A: 向已有任务组添加城市 ──────────────────────────────────────
    st.markdown("### ➕ 添加城市到现有任务组")

    if not task_groups_raw:
        st.warning("暂无任务组，请先在下方创建一个。")
    else:
        group_names = [t.get("name", "") for t in task_groups_raw]

        add_g_col, add_c_col, add_btn_col = st.columns([3, 3, 1])
        with add_g_col:
            sel_group = st.selectbox(
                "目标任务组",
                group_names,
                help="选择要追加城市的任务组",
            )
        with add_c_col:
            new_city = st.text_input(
                "城市名称",
                placeholder="例：西安市  顺德区  大理白族自治州",
                help="名称需与海天气象平台行政区划名一致",
            )
        with add_btn_col:
            st.markdown("<br>", unsafe_allow_html=True)
            do_add = st.button("添加 ➕", type="primary", use_container_width=True)

        if do_add:
            city = new_city.strip()
            if not city:
                st.error("城市名称不能为空。")
            else:
                fresh = load_raw()
                added = False
                for tg in fresh.get("task-groups", []):
                    if tg.get("name") == sel_group:
                        if not isinstance(tg.get("locations"), list):
                            tg["locations"] = []
                        if city in tg["locations"]:
                            st.warning(f"「{city}」已存在于「{sel_group}」中，无需重复添加。")
                        else:
                            tg["locations"].append(city)
                            save_raw(fresh)
                            st.success(f"已将「{city}」添加到「{sel_group}」")
                            added = True
                        break
                if added:
                    reload()

        # 当前选中任务组的城市网格预览
        for tg in task_groups_raw:
            if tg.get("name") == sel_group:
                cur_locs: list = tg.get("locations", []) or []
                if cur_locs:
                    with st.expander(
                        f"「{sel_group}」当前城市列表（{len(cur_locs)} 个）",
                        expanded=False,
                    ):
                        n_cols = 6
                        cols = st.columns(n_cols)
                        for i, loc in enumerate(cur_locs):
                            with cols[i % n_cols]:
                                # 每个城市旁放一个删除按钮
                                inner_a, inner_b = st.columns([4, 1])
                                inner_a.markdown(f"`{loc}`")
                                if inner_b.button("✕", key=f"del_{sel_group}_{loc}", help=f"从列表中移除 {loc}"):
                                    fresh = load_raw()
                                    for t in fresh.get("task-groups", []):
                                        if t.get("name") == sel_group and loc in (t.get("locations") or []):
                                            t["locations"].remove(loc)
                                    save_raw(fresh)
                                    reload()
                break

    st.divider()

    # ── Section B: 新建任务组 ─────────────────────────────────────────────────
    st.markdown("### 🆕 新建任务组")

    with st.form("form_new_group", clear_on_submit=True):
        fa, fb = st.columns(2)

        with fa:
            f_name = st.text_input(
                "任务组名称 *",
                placeholder="例：长三角历史气象组",
            )
            f_type = st.selectbox(
                "数据类型 *",
                options=list(TYPE_INFO.keys()),
                format_func=lambda k: f"{TYPE_INFO[k][0]} {TYPE_INFO[k][1]}",
            )
            f_locations = st.text_area(
                "城市列表（每行一个城市名）",
                placeholder="南京市\n上海市\n杭州市\n苏州市",
                height=130,
            )
            f_enabled = st.checkbox("创建后立即启用", value=True)

        with fb:
            f_sched_type = st.selectbox(
                "执行方式 *",
                ["once", "cron", "interval"],
                format_func=lambda x: {
                    "once":     "🔂 单次执行（启动时运行一次）",
                    "cron":     "⏰ Cron 定时（需填表达式）",
                    "interval": "🔄 固定间隔（需填秒数）",
                }[x],
            )
            f_cron = st.text_input(
                "Cron 表达式",
                placeholder="分 时 日 月 周  ·  示例：0 6 * * *",
                disabled=(f_sched_type != "cron"),
            )
            f_interval = st.number_input(
                "间隔（秒）",
                min_value=60, value=3600, step=300,
                disabled=(f_sched_type != "interval"),
            )
            f_output_to = st.selectbox(
                "输出目标",
                ["local", "database", "both"],
                format_func=lambda x: OUTPUT_LABEL.get(x, x),
            )
            f_output_fmt = st.selectbox(
                "文件格式",
                ["parquet", "csv"],
                format_func=lambda x: {
                    "parquet": "Parquet（高效压缩，推荐历史数据）",
                    "csv":     "CSV（可直接用 Excel 打开）",
                }[x],
            )

        submitted = st.form_submit_button("✅ 创建任务组", type="primary")
        if submitted:
            errs: list[str] = []
            if not f_name.strip():
                errs.append("任务组名称不能为空。")
            if f_name.strip() in [t.get("name") for t in task_groups_raw]:
                errs.append(f"任务组「{f_name.strip()}」已存在，请使用其他名称。")
            if f_sched_type == "cron" and not f_cron.strip():
                errs.append("选择 Cron 模式时必须填写 Cron 表达式（如 0 6 * * *）。")

            if errs:
                for e in errs:
                    st.error(e)
            else:
                locs = [l.strip() for l in f_locations.strip().splitlines() if l.strip()]
                new_tg: dict = {
                    "name":        f_name.strip(),
                    "type":        f_type,
                    "enabled":     f_enabled,
                    "locations":   locs,
                    "meteo_types": [],
                    "schedule":    {"type": f_sched_type},
                    "output":      {"to": f_output_to, "format": f_output_fmt},
                }
                if f_sched_type == "cron":
                    new_tg["schedule"]["cron"] = f_cron.strip()
                elif f_sched_type == "interval":
                    new_tg["schedule"]["interval"] = int(f_interval)

                fresh = load_raw()
                if not isinstance(fresh.get("task-groups"), list):
                    fresh["task-groups"] = []
                fresh["task-groups"].append(new_tg)
                save_raw(fresh)
                st.success(f"任务组「{f_name.strip()}」已创建！")
                reload()

    st.divider()

    # ── Section C: 批量启用 / 禁用 ───────────────────────────────────────────
    st.markdown("### 🔧 启用 / 禁用任务组")

    if not task_groups_raw:
        st.caption("暂无任务组。")
    else:
        toggle_cols = st.columns(min(total_groups, 3))
        for i, tg in enumerate(task_groups_raw):
            g_name = tg.get("name", "")
            g_enabled = tg.get("enabled", True)
            with toggle_cols[i % 3]:
                new_state = st.toggle(
                    g_name,
                    value=g_enabled,
                    key=f"toggle_{g_name}",
                )
                if new_state != g_enabled:
                    fresh = load_raw()
                    for t in fresh.get("task-groups", []):
                        if t.get("name") == g_name:
                            t["enabled"] = new_state
                    save_raw(fresh)
                    reload()


# ════════════════════════════════════════════════════════════════════════════
# Tab 3 — 运行日志
# ════════════════════════════════════════════════════════════════════════════

with tab_logs:

    # ── 本次会话的执行输出 ─────────────────────────────────────────────────
    st.markdown("### 🕐 本次会话执行记录")

    if st.session_state.run_output:
        group_label = st.session_state.last_run_group or "未知"
        ok_label = "成功 ✅" if st.session_state.last_run_ok else "失败 ❌"
        line_count = len(st.session_state.run_output)

        info_a, info_b, info_c = st.columns([3, 2, 1])
        info_a.markdown(f"**任务组：** {group_label}")
        info_b.markdown(f"**状态：** {ok_label}")
        info_c.markdown(f"**行数：** {line_count}")

        st.code("\n".join(st.session_state.run_output), language="text")

        if st.button("清除本次记录", key="clear_session_log"):
            st.session_state.run_output = []
            st.session_state.last_run_group = None
            st.session_state.last_run_ok = None
            st.rerun()
    else:
        st.info("本次会话尚未执行任何任务。在【任务总览】中点击「立即运行」后，日志将在此显示。", icon="ℹ")

    st.divider()

    # ── 持久化日志文件 ─────────────────────────────────────────────────────
    st.markdown("### 📄 持久化日志文件")

    log_file = global_raw.get("log_file", "./logs/htmeteo.log")
    log_path = Path(log_file)
    st.caption(f"文件路径：`{log_path.resolve()}`")

    if log_path.exists():
        ctrl_a, ctrl_b, ctrl_c = st.columns([1, 2, 4])
        with ctrl_a:
            if st.button("🔄 刷新日志"):
                st.rerun()
        with ctrl_b:
            n_lines = st.selectbox(
                "显示行数",
                [50, 100, 200, 500, 1000],
                index=1,
                label_visibility="collapsed",
            )

        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()

        recent_text = "".join(all_lines[-n_lines:])
        st.code(recent_text, language="text")
        st.caption(
            f"日志共 **{len(all_lines)}** 行，当前显示最后 **{n_lines}** 行。"
        )
    else:
        st.info(
            f"日志文件尚不存在：`{log_path}`\n\n"
            "首次通过调度器（scheduler.py）运行任务后将自动创建。",
            icon="ℹ",
        )
