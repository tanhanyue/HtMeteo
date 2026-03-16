-- =============================================================================
-- Doris 建表语句：逐小时天气预报表
-- 使用 UNIQUE KEY(date, location)，相同时次+地点的数据会自动覆盖更新
-- =============================================================================
-- 使用前：
--   1) 先删旧表：DROP TABLE IF EXISTS power_spot_weather.weather_forecast_hourly;
--   2) 再执行本 SQL 建表
--   3) 表名需与 config.yaml 中 database.table_prefix + "forecast_hourly" 一致
-- =============================================================================

DROP TABLE IF EXISTS power_spot_weather.weather_forecast_hourly;

CREATE TABLE power_spot_weather.weather_forecast_hourly (
    `date`              DATETIME     NOT NULL COMMENT '预报时次（含小时）',
    `location`          VARCHAR(64)  NOT NULL COMMENT '地点名称',
    `temperature_2m`    DOUBLE       COMMENT '2米气温(℃)',
    `relative_humidity_2m`   DOUBLE  COMMENT '2米相对湿度(%)',
    `dew_point_2m`      DOUBLE       COMMENT '2米露点温度(℃)',
    `apparent_temperature`   DOUBLE  COMMENT '体感温度(℃)',
    `precipitation`     DOUBLE       COMMENT '降水量(mm)',
    `rain`              DOUBLE       COMMENT '降雨(mm)',
    `snowfall`          DOUBLE       COMMENT '降雪(mm)',
    `weather_code`      INT          COMMENT '天气现象代码(WMO)',
    `pressure_msl`      DOUBLE       COMMENT '海平面气压(hPa)',
    `surface_pressure`  DOUBLE       COMMENT '地面气压(hPa)',
    `cloud_cover`       DOUBLE       COMMENT '总云量(%)',
    `cloud_cover_low`   DOUBLE       COMMENT '低云量(%)',
    `cloud_cover_mid`   DOUBLE       COMMENT '中云量(%)',
    `cloud_cover_high`  DOUBLE       COMMENT '高云量(%)',
    `vapour_pressure_deficit` DOUBLE  COMMENT '蒸气压亏缺(kPa)',
    `wind_speed_10m`    DOUBLE       COMMENT '10米风速(m/s)',
    `wind_speed_100m`   DOUBLE       COMMENT '100米风速(m/s)',
    `wind_direction_10m`  DOUBLE     COMMENT '10米风向(°)',
    `wind_direction_100m` DOUBLE     COMMENT '100米风向(°)',
    `wind_gusts_10m`    DOUBLE       COMMENT '10米阵风(m/s)',
    `surface_temperature` DOUBLE     COMMENT '地表温度(℃)',
    `soil_temperature_0_to_7cm`   DOUBLE COMMENT '0-7cm土壤温度(℃)',
    `soil_moisture_0_to_7cm`      DOUBLE COMMENT '0-7cm土壤湿度(m³/m³)',
    `soil_moisture_7_to_28cm`     DOUBLE COMMENT '7-28cm土壤湿度(m³/m³)',
    `runoff`            DOUBLE       COMMENT '径流(mm)',
    `cape`              DOUBLE       COMMENT '对流有效位能(J/kg)',
    `total_column_integrated_water_vapour` DOUBLE COMMENT '整层可降水量(kg/m²)',
    `shortwave_radiation_instant` DOUBLE COMMENT '短波辐射瞬时(W/m²)',
    `direct_radiation_instant`    DOUBLE COMMENT '直接辐射瞬时(W/m²)',
    `diffuse_radiation_instant`   DOUBLE COMMENT '散射辐射瞬时(W/m²)',
    `direct_normal_irradiance_instant` DOUBLE COMMENT '法向直射辐射瞬时(W/m²)',
    `global_tilted_irradiance_instant` DOUBLE COMMENT '斜面总辐射瞬时(W/m²)'
)
UNIQUE KEY(`date`, `location`)
COMMENT 'HtMeteo 逐小时天气预报数据（同 date+location 自动覆盖更新）'
PARTITION BY RANGE(`date`) (
    PARTITION p2026_01 VALUES LESS THAN ("2026-02-01"),
    PARTITION p2026_02 VALUES LESS THAN ("2026-03-01"),
    PARTITION p2026_03 VALUES LESS THAN ("2026-04-01"),
    PARTITION p2026_04 VALUES LESS THAN ("2026-05-01"),
    PARTITION p2026_05 VALUES LESS THAN ("2026-06-01"),
    PARTITION p2026_06 VALUES LESS THAN ("2026-07-01"),
    PARTITION p2026_07 VALUES LESS THAN ("2026-08-01"),
    PARTITION p2026_08 VALUES LESS THAN ("2026-09-01"),
    PARTITION p2026_09 VALUES LESS THAN ("2026-10-01"),
    PARTITION p2026_10 VALUES LESS THAN ("2026-11-01"),
    PARTITION p2026_11 VALUES LESS THAN ("2026-12-01"),
    PARTITION p2026_12 VALUES LESS THAN ("2027-01-01"),
    PARTITION p_future  VALUES LESS THAN ("2030-01-01")
)
DISTRIBUTED BY HASH(`location`) BUCKETS 10
PROPERTIES (
    "replication_num" = "3"
);
