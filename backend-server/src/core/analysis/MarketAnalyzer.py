"""
大盘分析模块
负责获取大盘趋势（标普500、纳斯达克）等功能
"""
from datetime import datetime
from shared.longbridge import Period, AdjustType
from utils.IndicatorUtilEnhanced import IndicatorUtilEnhanced
from utils.MonitorLink import MonitorLink

class MarketAnalyzer:
    @staticmethod
    def get_market_trend(qc):
        """获取大盘趋势（标普500和纳斯达克）"""
        try:
            # 获取标普500趋势
            sp500_trend = MarketAnalyzer._get_index_trend(qc, ".SPX", "标普500")
            
            # 获取纳斯达克趋势
            nasdaq_trend = MarketAnalyzer._get_index_trend(qc, ".NDX", "纳斯达克")
            
            return sp500_trend, nasdaq_trend
        except Exception as e:
            MonitorLink.log(f"⚠️ [大盘] 获取大盘趋势失败: {str(e)[:50]}")
            return None, None
    
    @staticmethod
    def _get_index_trend(qc, symbol, name):
        """获取单个指数的趋势"""
        try:
            candles = qc.history_candlesticks_by_offset(
                symbol=symbol, 
                period=Period.Day, 
                count=60,
                adjust_type=AdjustType.ForwardAdjust, 
                forward=False,                    
                time=datetime.now()                        
            )
            
            if not candles:
                return None
            
            prices = [float(c.close) for c in candles]
            ema_short = IndicatorUtilEnhanced.calculate_ema(prices, 12)
            ema_long = IndicatorUtilEnhanced.calculate_ema(prices, 26)
            trend = "📈 上升" if ema_short > ema_long else "📉 下降"
            
            MonitorLink.log(f"🌍 [大盘] {name}: {prices[-1]:.2f} | 趋势: {trend}")
            
            return {
                "name": name,
                "price": prices[-1],
                "ema_short": ema_short,
                "ema_long": ema_long,
                "trend": trend
            }
        except Exception as e:
            MonitorLink.log(f"⚠️ [大盘] 获取{name}趋势失败: {str(e)[:50]}")
            return None
