import sys
import os
import datetime
import pandas as pd
from tqdm import tqdm
import pymysql

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from HtMeteo import HtMeteo

class WeatherToSqlite:
    def __init__(self):
        self.meteo = HtMeteo()
        self.meteo.set_forecast_mode('on')
        self.locations = []  # 四川省内所有区县
        self.db_config = {
            'host': 'localhost',
            'port': 9030,
            'user': 'root',
            'password': '',
            'database': 'weather'
        }
    
    def load_locations(self):
        """加载四川省内所有区县"""
        # 这里需要根据用户提供的区域表文件来加载
        # 暂时使用示例数据
        self.locations = [
            '成都市', '自贡市', '攀枝花市', '泸州市', '德阳市',
            '绵阳市', '广元市', '遂宁市', '内江市', '乐山市',
            '南充市', '眉山市', '宜宾市', '广安市', '达州市',
            '雅安市', '巴中市', '资阳市', '阿坝藏族羌族自治州',
            '甘孜藏族自治州', '凉山彝族自治州'
        ]
    
    def get_forecast_data(self, location):
        """获取指定地点的逐小时预报数据"""
        self.meteo.set_location(location)
        df = self.meteo.api_forecast_hourly()
        if isinstance(df, pd.DataFrame) and not df.empty:
            df['location'] = location
            return df
        return None
    
    def create_table(self):
        """创建 hourly_forecast 表"""
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS hourly_forecast (
            location VARCHAR(100),
            datetime DATETIME,
            temperature_2m FLOAT,
            precipitation FLOAT,
            shortwave_radiation_instant FLOAT,
            wind_speed_10m FLOAT,
            relative_humidity_2m FLOAT,
            PRIMARY KEY (location, datetime)
        ) ENGINE=OLAP
        DUPLICATE KEY(location, datetime)
        PARTITION BY RANGE(datetime)
        (PARTITION p2024 VALUES [('2024-01-01 00:00:00'), ('2025-01-01 00:00:00')),
         PARTITION p2025 VALUES [('2025-01-01 00:00:00'), ('2026-01-01 00:00:00')),
         PARTITION p2026 VALUES [('2026-01-01 00:00:00'), ('2027-01-01 00:00:00')))
        DISTRIBUTED BY HASH(location)
        PROPERTIES (
            "replication_num" = "3"
        )
        """
        
        try:
            conn = pymysql.connect(
                host=self.db_config['host'],
                port=self.db_config['port'],
                user=self.db_config['user'],
                password=self.db_config['password'],
                database=self.db_config['database']
            )
            cursor = conn.cursor()
            cursor.execute(create_table_sql)
            conn.commit()
            print("表创建成功!")
        except Exception as e:
            print(f"创建表时出错: {e}")
        finally:
            if 'conn' in locals():
                conn.close()
    
    def insert_or_update_data(self, df):
        """插入或更新数据"""
        if df is None or df.empty:
            return
        
        # 准备数据
        df.reset_index(inplace=True)
        df.rename(columns={'date': 'datetime'}, inplace=True)
        
        # 选择需要的列
        required_columns = ['location', 'datetime', 'temperature_2m', 'precipitation', 
                          'shortwave_radiation_instant', 'wind_speed_10m', 'relative_humidity_2m']
        df = df[required_columns]
        
        # 构建插入或更新语句
        insert_sql = """
        INSERT INTO hourly_forecast (location, datetime, temperature_2m, precipitation, 
                                   shortwave_radiation_instant, wind_speed_10m, relative_humidity_2m)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            temperature_2m = VALUES(temperature_2m),
            precipitation = VALUES(precipitation),
            shortwave_radiation_instant = VALUES(shortwave_radiation_instant),
            wind_speed_10m = VALUES(wind_speed_10m),
            relative_humidity_2m = VALUES(relative_humidity_2m)
        """
        
        try:
            conn = pymysql.connect(
                host=self.db_config['host'],
                port=self.db_config['port'],
                user=self.db_config['user'],
                password=self.db_config['password'],
                database=self.db_config['database']
            )
            cursor = conn.cursor()
            
            # 批量插入数据
            data = []
            for _, row in df.iterrows():
                data.append((
                    row['location'],
                    row['datetime'],
                    row['temperature_2m'],
                    row['precipitation'],
                    row['shortwave_radiation_instant'],
                    row['wind_speed_10m'],
                    row['relative_humidity_2m']
                ))
            
            cursor.executemany(insert_sql, data)
            conn.commit()
            print(f"成功处理 {len(df)} 条数据")
        except Exception as e:
            print(f"插入数据时出错: {e}")
            conn.rollback()
        finally:
            if 'conn' in locals():
                conn.close()
    
    def run(self):
        """运行主流程"""
        print("开始运行天气数据采集脚本...")
        
        # 加载地点
        self.load_locations()
        print(f"共加载 {len(self.locations)} 个地点")
        
        # 创建表
        self.create_table()
        
        # 遍历地点获取数据
        for location in tqdm(self.locations, desc="处理地点"):
            print(f"\n处理地点: {location}")
            df = self.get_forecast_data(location)
            if df is not None:
                self.insert_or_update_data(df)
            else:
                print(f"无法获取 {location} 的数据")
        
        print("\n脚本运行完成!")

if __name__ == "__main__":
    weather_to_sqlite = WeatherToSqlite()
    weather_to_sqlite.run()
