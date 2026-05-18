"""
InfluxDB时序数据库客户端
用于存储和查询行情数据
"""
import os
from typing import List, Dict, Optional
from datetime import datetime
import logging

from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.domain.write_precision import WritePrecision

from config.settings import settings

logger = logging.getLogger(__name__)


class InfluxDBManager:
    """InfluxDB管理器"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._client = None
            cls._instance._write_api = None
            cls._instance._query_api = None
        return cls._instance
    
    def __init__(self):
        if self._client is None:
            self._init_client()
    
    def _init_client(self):
        """初始化客户端"""
        try:
            self._client = InfluxDBClient(
                url=settings.INFLUXDB_URL,
                token=settings.INFLUXDB_TOKEN,
                org=settings.INFLUXDB_ORG
            )
            self._write_api = self._client.write_api(write_options=SYNCHRONOUS)
            self._query_api = self._client.query_api()
            logger.info("InfluxDB客户端初始化成功")
        except Exception as e:
            logger.error(f"InfluxDB客户端初始化失败: {e}")
            raise
    
    @property
    def client(self) -> InfluxDBClient:
        """获取客户端"""
        if self._client is None:
            self._init_client()
        return self._client
    
    @property
    def write_api(self):
        """获取写入API"""
        if self._write_api is None:
            self._init_client()
        return self._write_api
    
    @property
    def query_api(self):
        """获取查询API"""
        if self._query_api is None:
            self._init_client()
        return self._query_api
    
    def write_quote(self, symbol: str, price: float, volume: int,
                   open_price: float = None, high: float = None,
                   low: float = None, timestamp: datetime = None):
        """
        写入行情数据
        """
        try:
            point = Point("stock_quote") \
                .tag("symbol", symbol) \
                .field("price", float(price)) \
                .field("volume", int(volume))
            
            if open_price:
                point = point.field("open", float(open_price))
            if high:
                point = point.field("high", float(high))
            if low:
                point = point.field("low", float(low))
            
            if timestamp:
                point = point.time(timestamp)
            
            self.write_api.write(
                bucket=settings.INFLUXDB_BUCKET,
                record=point
            )
            
            logger.debug(f"行情数据写入成功: {symbol}")
            
        except Exception as e:
            logger.error(f"行情数据写入失败: {e}")
            raise
    
    def query_quotes(self, symbol: str, start: datetime, end: datetime = None,
                    interval: str = "1m") -> List[Dict]:
        """
        查询行情数据
        :param symbol: 股票代码
        :param start: 开始时间
        :param end: 结束时间
        :param interval: 时间间隔 (1m, 5m, 1h, 1d)
        """
        try:
            end = end or datetime.utcnow()
            
            query = f'''
            from(bucket: "{settings.INFLUXDB_BUCKET}")
                |> range(start: {start.isoformat()}Z, stop: {end.isoformat()}Z)
                |> filter(fn: (r) => r._measurement == "stock_quote")
                |> filter(fn: (r) => r.symbol == "{symbol}")
                |> aggregateWindow(every: {interval}, fn: mean, createEmpty: false)
                |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
            '''
            
            tables = self.query_api.query(query)
            
            results = []
            for table in tables:
                for record in table.records:
                    results.append({
                        "time": record.get_time().isoformat(),
                        "symbol": record.values.get("symbol"),
                        "price": record.values.get("price"),
                        "volume": record.values.get("volume"),
                        "open": record.values.get("open"),
                        "high": record.values.get("high"),
                        "low": record.values.get("low")
                    })
            
            return results
            
        except Exception as e:
            logger.error(f"行情数据查询失败: {e}")
            return []
    
    def write_indicator(self, symbol: str, indicator_name: str,
                       value: float, timestamp: datetime = None):
        """
        写入技术指标
        """
        try:
            point = Point("technical_indicator") \
                .tag("symbol", symbol) \
                .tag("indicator", indicator_name) \
                .field("value", float(value))
            
            if timestamp:
                point = point.time(timestamp)
            
            self.write_api.write(
                bucket=settings.INFLUXDB_BUCKET,
                record=point
            )
            
            logger.debug(f"指标数据写入成功: {symbol} - {indicator_name}")
            
        except Exception as e:
            logger.error(f"指标数据写入失败: {e}")
            raise
    
    def query_indicators(self, symbol: str, indicator: str,
                        start: datetime, end: datetime = None) -> List[Dict]:
        """查询技术指标"""
        try:
            end = end or datetime.utcnow()
            
            query = f'''
            from(bucket: "{settings.INFLUXDB_BUCKET}")
                |> range(start: {start.isoformat()}Z, stop: {end.isoformat()}Z)
                |> filter(fn: (r) => r._measurement == "technical_indicator")
                |> filter(fn: (r) => r.symbol == "{symbol}")
                |> filter(fn: (r) => r.indicator == "{indicator}")
            '''
            
            tables = self.query_api.query(query)
            
            results = []
            for table in tables:
                for record in table.records:
                    results.append({
                        "time": record.get_time().isoformat(),
                        "value": record.get_value()
                    })
            
            return results
            
        except Exception as e:
            logger.error(f"指标数据查询失败: {e}")
            return []
    
    def write_trade(self, order_id: str, symbol: str, side: str,
                   quantity: float, price: float, timestamp: datetime = None):
        """
        写入交易记录
        """
        try:
            point = Point("trade") \
                .tag("symbol", symbol) \
                .tag("side", side) \
                .tag("order_id", order_id) \
                .field("quantity", float(quantity)) \
                .field("price", float(price))
            
            if timestamp:
                point = point.time(timestamp)
            
            self.write_api.write(
                bucket=settings.INFLUXDB_BUCKET,
                record=point
            )
            
            logger.debug(f"交易记录写入成功: {order_id}")
            
        except Exception as e:
            logger.error(f"交易记录写入失败: {e}")
            raise
    
    def get_latest_quote(self, symbol: str) -> Optional[Dict]:
        """获取最新行情"""
        try:
            query = f'''
            from(bucket: "{settings.INFLUXDB_BUCKET}")
                |> range(start: -1h)
                |> filter(fn: (r) => r._measurement == "stock_quote")
                |> filter(fn: (r) => r.symbol == "{symbol}")
                |> last()
                |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
            '''
            
            tables = self.query_api.query(query)
            
            for table in tables:
                for record in table.records:
                    return {
                        "time": record.get_time().isoformat(),
                        "symbol": record.values.get("symbol"),
                        "price": record.values.get("price"),
                        "volume": record.values.get("volume")
                    }
            
            return None
            
        except Exception as e:
            logger.error(f"获取最新行情失败: {e}")
            return None
    
    def close(self):
        """关闭连接"""
        if self._client:
            self._client.close()
            logger.info("InfluxDB连接已关闭")


# 全局实例
influx_db = InfluxDBManager()
