# HtMeteo — 配置驱动的气象数据自动化抓取系统

  

基于 [海天气象](https://cornicelli.net/) 数据平台的 Python 气象数据采集系统。通过一个 `config.yaml` 配置文件管理所有抓取任务，提供 Streamlit 可视化控制台和命令行两种使用方式。

  

## 功能概览

  

- **配置驱动**：所有任务在 `config.yaml` 中以任务组形式管理，类似 Clash 的分组思路

- **可视化控制台**：Streamlit 网页界面，可在线编辑配置、选取城市、执行任务、查看日志

- **省份/城市二级选取**：从行政区划表中按省选择城市，支持整省一键添加

- **多种数据类型**：历史气象（逐小时/日/月/年）、天气预报、全国预报批量下载、API 直查

- **灵活调度**：单次执行、Cron 定时、固定间隔三种调度方式

- **数据库写入**：支持将数据写入 Doris / MySQL，UNIQUE KEY 自动覆盖更新

- **容错机制**：单个城市失败不影响整体任务，自动跳过平台无数据的地点

  

## 项目结构

  

```

HtMeteo/

├── app.py                  # Streamlit 可视化控制台（主入口）

├── HtMeteo.py              # 气象数据核心库（账户认证、数据拉取、查询统计）

├── config_loader.py        # config.yaml 解析与校验

├── task_runner.py           # 任务执行模块（支持 CLI 和子进程调用）

├── scheduler.py             # 定时调度引擎（Cron / Interval）

├── db_writer.py             # 数据库写入模块（Doris / MySQL）

├── config.example.yaml      # 配置文件模板（不含敏感信息，纳入 Git）

├── config.yaml              # 实际配置文件（含密码，不纳入 Git）

├── requirements.txt         # Python 依赖

├── main.py                  # HtMeteo 原始示例代码

├── docs/

│   ├── doris_forecast_hourly.sql   # Doris 建表语句

│   └── t_dim_area.csv              # 省份/城市行政区划映射表

├── scripts/

│   └── weather_to_sqlite.py        # 早期数据入库脚本（参考）

├── data/                    # 运行时生成的数据目录（不纳入 Git）

│   ├── history/             # 逐小时历史气象数据（parquet）

│   ├── history_analysis/    # 日/月/年统计分析数据（parquet）

│   ├── forecast/            # 天气预报数据（csv）

│   └── temp/                # 下载缓存（csv/zip）

└── logs/                    # 运行日志（不纳入 Git）

```

  

## 快速开始

  

### 1. 环境准备

  

```bash

# 克隆项目

git clone <repo-url>

cd HtMeteo

  

# 创建虚拟环境并安装依赖

python -m venv venv

# Windows

.\venv\Scripts\activate

# Linux/Mac

source venv/bin/activate

  

pip install -r requirements.txt

```

  

### 2. 创建配置文件

  

```bash

cp config.example.yaml config.yaml

```

  

编辑 `config.yaml`，填写海天气象账户和数据库信息（也可在网页界面中操作）。

  

### 3. 启动可视化控制台

  

```bash

streamlit run app.py

```

  

打开浏览器访问 `http://localhost:8501`，在【编辑配置】标签页中：

  

1. 填写海天气象账户和数据库连接信息

2. 新建任务组，通过省份/城市二级选取器选择目标城市

3. 设置数据类型、调度方式、输出目标

4. 在【任务总览】中点击「立即运行」

  

### 4. 命令行使用（可选）

  

```bash

# 列出所有任务组

python scheduler.py --list

  

# 执行指定任务组

python task_runner.py --group "四川预报每日更新组"

  

# 启动定时调度器（Cron / Interval 任务进入循环）

python scheduler.py

```

  

## 配置文件说明

  

`config.yaml` 分为四个部分：

  

### global — 全局设置

  

```yaml

global:

  work_dir: ./data              # 数据存储根目录

  log_level: INFO               # 日志等级

  log_file: ./logs/htmeteo.log  # 日志文件路径

  timezone: Asia/Shanghai       # 调度时区

```

  

### account — 海天气象账户

  

```yaml

account:

  username: "your_email"

  password: "your_password"

```

  

### database — 数据库配置

  

```yaml

database:

  enabled: true           # 是否启用数据库写入

  type: mysql              # mysql | postgresql | sqlite

  host: localhost

  port: 9030               # Doris 默认端口

  user: admin

  password: "db_password"

  name: weather

  table_prefix: "weather_" # 表名 = 前缀 + 后缀（如 weather_forecast_hourly）

```

  

### task-groups — 任务组

  

每个任务组是一个独立的抓取策略：

  

```yaml

task-groups:

  - name: 四川预报每日更新组

    type: forecast            # history | forecast | fetch-all-forecast | api-forecast | api-history

    enabled: true

    locations:

      - 成都市

      - 绵阳市

    meteo_types: []           # 留空表示全部气象要素

    schedule:

      type: cron              # once | cron | interval

      cron: "0 6 * * *"       # 每天 06:00 执行

    output:

      to: both                # local | database | both

      format: csv             # csv | parquet

```

  

**任务类型说明：**

  

| type | 说明 | 数据来源 |
|------|------|----------|
| `history` | 下载 2000-2025 逐小时历史数据 + 日/月/年统计 | 平台下载 → 本地缓存 |
| `forecast` | 下载未来 10 天逐小时天气预报 | 平台下载 → 本地缓存 |
| `fetch-all-forecast` | 一次性下载全国 3191 个城市预报 ZIP | 平台打包下载 |
| `api-forecast` | API 直查天气预报（不落本地文件） | 在线 API |
| `api-history` | API 直查历史统计（不落本地文件） | 在线 API |

  

## 数据库建表（Doris）

  

如需将预报数据写入 Doris，先执行建表 SQL：

  

```bash

# 在 Doris 客户端中执行

source docs/doris_forecast_hourly.sql

```

  

该表使用 `UNIQUE KEY(date, location)`，相同时次 + 地点的数据会自动覆盖更新，适合每日定时刷新预报数据。

  

## 支持的气象要素

  

### 天气预报（32 种）

  

气温、体感温度、露点、湿度、气压、降水（雨/雪）、云量（高/中/低）、风速/风向（10m/100m）、阵风、辐射（短波/直射/散射）、土壤温湿度、径流、CAPE、可降水量等。

  

### 历史数据（40 种）

  

在预报要素基础上增加蒸散量、蒸气压亏缺、边界层高度、深层土壤温湿度、整层水汽等，且区分最大值/最小值/平均值/累积值。

  

完整要素列表见 [海天气象数据开发文档](https://cornicelli.net/meteo/doc#data_info)。

  

## 数据来源

  

- **历史数据**：ERA5 再分析资料（欧洲中期天气预报中心）

- **预报数据**：ECMWF 数值预报

- **数据平台**：[海天气象](https://cornicelli.net/)

  

## 依赖说明

  

| 包 | 用途 |
|---|---|
| pandas, numpy, pyarrow | 数据处理与存储 |
| requests, beautifulsoup4 | 平台登录与数据拉取 |
| PyYAML | 配置文件解析 |
| streamlit | 可视化控制台 |
| APScheduler | 定时任务调度 |
| SQLAlchemy, pymysql | 数据库写入 |