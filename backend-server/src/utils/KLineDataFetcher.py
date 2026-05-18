#!/usr/bin/env python3
"""
K线数据获取工具类
封装日K、周K、月K、年K的获取方法
"""
import sys
import os
from datetime import datetime
import pymysql
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.longbridge import AdjustType, Period, build_quote_context
from utils.DbUtil import DbUtil
import time

class KLineDataFetcher:
    """K线数据获取工具类"""
    
    def __init__(self):
        """初始化Longbridge客户端"""
        self.qc = build_quote_context()
        self.db_conn = None
        self.db_cursor = None
        self.batch_size = 100
    
    def connect_db(self):
        """连接数据库"""
        if self.db_conn is None:
            self.db_conn = pymysql.connect(**DbUtil.URL_CONFIG)
            self.db_cursor = self.db_conn.cursor()
    
    def close_db(self):
        """关闭数据库连接"""
        if self.db_cursor:
            self.db_cursor.close()
            self.db_cursor = None
        if self.db_conn:
            self.db_conn.close()
            self.db_conn = None
    
    def insert_daily_batch(self, data_list):
        """批量插入日K数据"""
        if not data_list:
            return 0
        
        inserted = 0
        
        for data in data_list:
            try:
                insert_sql = """
                INSERT INTO us_stock_daily 
                (trade_date, symbol, open_price, high_price, low_price, close_price, volume, amount)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                open_price = VALUES(open_price),
                high_price = VALUES(high_price),
                low_price = VALUES(low_price),
                close_price = VALUES(close_price),
                volume = VALUES(volume),
                amount = VALUES(amount)
                """
                params = (
                    data['date'],
                    data['symbol'],
                    data['open'],
                    data['high'],
                    data['low'],
                    data['close'],
                    data['volume'],
                    data['amount'],
                )
                DbUtil.execute_sql(insert_sql, params)
                inserted += 1
                    
            except Exception as e:
                print(f"  插入失败: {e}")
        
        return inserted
    
    def fetch_daily_data(self, symbol, start_date=None, end_date=None, count=1000):
        """获取日K数据"""
        try:
            time.sleep(0.1)
            
            if start_date and end_date:
                # 使用日期范围获取
                candles = self.qc.history_candlesticks_by_date(
                    symbol=symbol,
                    period=Period.Day,
                    adjust_type=AdjustType.ForwardAdjust,
                    start=start_date,
                    end=end_date
                )
            else:
                # 使用偏移量获取
                current_time = datetime.now()
                candles = self.qc.history_candlesticks_by_offset(
                    symbol=symbol,
                    period=Period.Day,
                    count=count,
                    adjust_type=AdjustType.ForwardAdjust,
                    forward=False,
                    time=current_time
                )
            
            if not candles:
                return None
            
            data_list = []
            for candle in candles:
                data_list.append({
                    'date': candle.timestamp.strftime('%Y-%m-%d'),
                    'symbol': symbol,
                    'open': float(candle.open),
                    'high': float(candle.high),
                    'low': float(candle.low),
                    'close': float(candle.close),
                    'volume': int(candle.volume),
                    'amount': float(candle.turnover) if hasattr(candle, 'turnover') else 0
                })
            
            return data_list
        except Exception as e:
            print(f"  {symbol} 获取日K失败: {e}")
            return None
    
    def fetch_daily_data_with_retry(self, symbol, start_date=None, end_date=None, count=1000, max_retries=3):
        """获取日K数据（带重试）"""
        retry_count = 0
        delay = 0.2
        
        while retry_count < max_retries:
            try:
                time.sleep(delay)
                
                if start_date and end_date:
                    candles = self.qc.history_candlesticks_by_date(
                        symbol=symbol,
                        period=Period.Day,
                        adjust_type=AdjustType.ForwardAdjust,
                        start=start_date,
                        end=end_date
                    )
                else:
                    current_time = datetime.now()
                    candles = self.qc.history_candlesticks_by_offset(
                        symbol=symbol,
                        period=Period.Day,
                        count=count,
                        adjust_type=AdjustType.ForwardAdjust,
                        forward=False,
                        time=current_time
                    )
                
                if not candles:
                    return None
                
                data_list = []
                for candle in candles:
                    data_list.append({
                        'date': candle.timestamp.strftime('%Y-%m-%d'),
                        'symbol': symbol,
                        'open': float(candle.open),
                        'high': float(candle.high),
                        'low': float(candle.low),
                        'close': float(candle.close),
                        'volume': int(candle.volume),
                        'amount': float(candle.turnover) if hasattr(candle, 'turnover') else 0
                    })
                
                return data_list
                
            except Exception as e:
                error_msg = str(e)
                retry_count += 1
                
                if "301606" in error_msg:
                    delay *= 2
                    print(f"  {symbol} 速率限制，等待 {delay:.1f} 秒后重试 ({retry_count}/{max_retries})")
                    time.sleep(delay)
                elif "301600" in error_msg:
                    return None
                elif retry_count < max_retries:
                    print(f"  {symbol} 错误: {e}，重试 ({retry_count}/{max_retries})")
                    time.sleep(delay)
                else:
                    print(f"  {symbol} 获取失败: {e}")
                    return None
        
        return None
    
    def generate_weekly_data(self):
        """从日K数据生成周K数据"""
        print("\n📊 正在生成周K数据...")
        
        # 清空表
        DbUtil.execute_sql("TRUNCATE TABLE us_stock_weekly")
        
        # 获取所有日K数据
        print("正在读取日K数据...")
        daily_data = DbUtil.query_all("""
            SELECT trade_date, symbol, open_price, close_price, high_price, low_price, volume, amount
            FROM us_stock_daily
            ORDER BY symbol, trade_date
        """)
        
        print(f"读取到 {len(daily_data)} 条日K数据")
        
        # 转换为DataFrame
        df = pd.DataFrame(daily_data, columns=['trade_date', 'symbol', 'open_price', 'close_price', 'high_price', 'low_price', 'volume', 'amount'])
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        
        # 添加周信息
        df['week_start'] = df['trade_date'] - pd.to_timedelta(df['trade_date'].dt.weekday, unit='D')
        
        # 按周聚合
        print("正在聚合周K数据...")
        weekly_df = df.groupby(['week_start', 'symbol']).agg({
            'open_price': 'first',
            'close_price': 'last',
            'high_price': 'max',
            'low_price': 'min',
            'volume': 'sum',
            'amount': 'sum'
        }).reset_index()
        
        print(f"聚合后得到 {len(weekly_df)} 条周K数据")
        
        # 插入数据库
        print("正在插入数据库...")
        inserted = 0
        for _, row in weekly_df.iterrows():
            try:
                insert_sql = """
                INSERT INTO us_stock_weekly 
                (trade_date, symbol, open_price, close_price, high_price, low_price, volume, amount)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """
                params = (
                    row['week_start'].strftime('%Y-%m-%d'),
                    row['symbol'],
                    row['open_price'],
                    row['close_price'],
                    row['high_price'],
                    row['low_price'],
                    row['volume'],
                    row['amount'],
                )
                DbUtil.execute_sql(insert_sql, params)
                inserted += 1
                
                if inserted % 1000 == 0:
                    print(f"已插入 {inserted} 条记录...")
                    
            except Exception as e:
                print(f"插入失败: {e}")
        
        print(f"✅ 周K数据生成成功，共插入 {inserted} 条记录")
        
        # 验证
        count = DbUtil.query_all("SELECT COUNT(*) FROM us_stock_weekly")
        print(f"📈 us_stock_weekly表中共有 {count[0][0]} 条记录")
        
        return inserted
    
    def generate_monthly_data(self):
        """从日K数据生成月K数据"""
        print("\n📊 正在生成月K数据...")
        
        # 清空表
        DbUtil.execute_sql("TRUNCATE TABLE us_stock_monthly")
        
        # 获取所有日K数据
        print("正在读取日K数据...")
        daily_data = DbUtil.query_all("""
            SELECT trade_date, symbol, open_price, close_price, high_price, low_price, volume, amount
            FROM us_stock_daily
            ORDER BY symbol, trade_date
        """)
        
        print(f"读取到 {len(daily_data)} 条日K数据")
        
        # 转换为DataFrame
        df = pd.DataFrame(daily_data, columns=['trade_date', 'symbol', 'open_price', 'close_price', 'high_price', 'low_price', 'volume', 'amount'])
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        
        # 添加月信息
        df['month_start'] = df['trade_date'].dt.to_period('M').dt.to_timestamp()
        
        # 按月聚合
        print("正在聚合月K数据...")
        monthly_df = df.groupby(['month_start', 'symbol']).agg({
            'open_price': 'first',
            'close_price': 'last',
            'high_price': 'max',
            'low_price': 'min',
            'volume': 'sum',
            'amount': 'sum'
        }).reset_index()
        
        print(f"聚合后得到 {len(monthly_df)} 条月K数据")
        
        # 插入数据库
        print("正在插入数据库...")
        inserted = 0
        for _, row in monthly_df.iterrows():
            try:
                insert_sql = """
                INSERT INTO us_stock_monthly 
                (trade_date, symbol, open_price, close_price, high_price, low_price, volume, amount)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """
                params = (
                    row['month_start'].strftime('%Y-%m-%d'),
                    row['symbol'],
                    row['open_price'],
                    row['close_price'],
                    row['high_price'],
                    row['low_price'],
                    row['volume'],
                    row['amount'],
                )
                DbUtil.execute_sql(insert_sql, params)
                inserted += 1
                
                if inserted % 1000 == 0:
                    print(f"已插入 {inserted} 条记录...")
                    
            except Exception as e:
                print(f"插入失败: {e}")
        
        print(f"✅ 月K数据生成成功，共插入 {inserted} 条记录")
        
        # 验证
        count = DbUtil.query_all("SELECT COUNT(*) FROM us_stock_monthly")
        print(f"📈 us_stock_monthly表中共有 {count[0][0]} 条记录")
        
        return inserted
    
    def generate_yearly_data(self):
        """从日K数据生成年K数据"""
        print("\n📊 正在生成年K数据...")
        
        # 清空表
        DbUtil.execute_sql("TRUNCATE TABLE us_stock_yearly")
        
        # 获取所有日K数据
        print("正在读取日K数据...")
        daily_data = DbUtil.query_all("""
            SELECT trade_date, symbol, open_price, close_price, high_price, low_price, volume, amount
            FROM us_stock_daily
            ORDER BY symbol, trade_date
        """)
        
        print(f"读取到 {len(daily_data)} 条日K数据")
        
        # 转换为DataFrame
        df = pd.DataFrame(daily_data, columns=['trade_date', 'symbol', 'open_price', 'close_price', 'high_price', 'low_price', 'volume', 'amount'])
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        
        # 添加年信息
        df['year_start'] = df['trade_date'].dt.to_period('Y').dt.to_timestamp()
        
        # 按年聚合
        print("正在聚合年K数据...")
        yearly_df = df.groupby(['year_start', 'symbol']).agg({
            'open_price': 'first',
            'close_price': 'last',
            'high_price': 'max',
            'low_price': 'min',
            'volume': 'sum',
            'amount': 'sum'
        }).reset_index()
        
        print(f"聚合后得到 {len(yearly_df)} 条年K数据")
        
        # 插入数据库
        print("正在插入数据库...")
        inserted = 0
        for _, row in yearly_df.iterrows():
            try:
                insert_sql = """
                INSERT INTO us_stock_yearly 
                (trade_date, symbol, open_price, close_price, high_price, low_price, volume, amount)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """
                params = (
                    row['year_start'].strftime('%Y-%m-%d'),
                    row['symbol'],
                    row['open_price'],
                    row['close_price'],
                    row['high_price'],
                    row['low_price'],
                    row['volume'],
                    row['amount'],
                )
                DbUtil.execute_sql(insert_sql, params)
                inserted += 1
                
                if inserted % 1000 == 0:
                    print(f"已插入 {inserted} 条记录...")
                    
            except Exception as e:
                print(f"插入失败: {e}")
        
        print(f"✅ 年K数据生成成功，共插入 {inserted} 条记录")
        
        # 验证
        count = DbUtil.query_all("SELECT COUNT(*) FROM us_stock_yearly")
        print(f"📈 us_stock_yearly表中共有 {count[0][0]} 条记录")
        
        return inserted
    
    def generate_all_kline_data(self):
        """生成所有K线数据（周K、月K、年K）"""
        print("🚀 开始生成所有K线数据...")
        
        # 生成周K数据
        weekly_count = self.generate_weekly_data()
        
        # 生成月K数据
        monthly_count = self.generate_monthly_data()
        
        # 生成年K数据
        yearly_count = self.generate_yearly_data()
        
        print(f"\n✅ 所有K线数据生成完成！")
        print(f"📊 周K数据: {weekly_count} 条")
        print(f"📊 月K数据: {monthly_count} 条")
        print(f"📊 年K数据: {yearly_count} 条")
        
        return {
            'weekly': weekly_count,
            'monthly': monthly_count,
            'yearly': yearly_count
        }
    
    def close(self):
        """关闭所有连接"""
        self.close_db()
        if hasattr(self.qc, 'close'):
            self.qc.close()
