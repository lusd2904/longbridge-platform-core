"""
股票扫描模块
负责扫描股票池、计算技术指标、识别异常信号等功能
"""
import time
import re
from datetime import datetime
from shared.longbridge import Period, AdjustType
from utils.StockPool import StockPool
from utils.IndicatorUtil import IndicatorUtil
from utils.IndicatorUtilEnhanced import IndicatorUtilEnhanced
from utils.MonitorLink import MonitorLink

class StockScanner:
    @staticmethod
    def scan_stocks(qc, us_pool, price_cache, holds):
        """扫描股票池，计算技术指标"""
        summary_data = []
        
        for s in us_pool:
            try:
                # 严格限流保护，防止 301606 错误
                time.sleep(0.6) 
                
                # 获取 K 线
                current_time = datetime.now()
                candles = qc.history_candlesticks_by_offset(
                    symbol=s, 
                    period=Period.Day, 
                    count=60,
                    adjust_type=AdjustType.ForwardAdjust, 
                    forward=False,                    
                    time=current_time                        
                )
                
                if not candles:
                    continue
                
                # 技术指标初筛
                prices = [float(c.close) for c in candles]
                highs = [float(c.high) for c in candles]
                lows = [float(c.low) for c in candles]
                volumes = [float(c.volume) for c in candles]
                
                # 计算基础指标
                rsi = IndicatorUtil.calculate_rsi(prices)
                boll_mid, boll_upper, boll_lower = IndicatorUtil.calculate_boll(prices)
                diff, dea, macd_h = IndicatorUtil.calculate_macd(prices)
                
                # 计算增强指标
                atr = IndicatorUtilEnhanced.calculate_atr(prices, highs, lows)
                ema_short = IndicatorUtilEnhanced.calculate_ema(prices, 12)
                ema_long = IndicatorUtilEnhanced.calculate_ema(prices, 26)
                k, d, j = IndicatorUtilEnhanced.calculate_kdj(prices, highs, lows)
                obv = IndicatorUtilEnhanced.calculate_obv(prices, volumes)
                roc = IndicatorUtilEnhanced.calculate_roc(prices)
                cci = IndicatorUtilEnhanced.calculate_cci(prices, highs, lows)
                support, resistance = IndicatorUtilEnhanced.calculate_support_resistance(prices)
                market_env = IndicatorUtilEnhanced.analyze_market_environment(prices)
                
                # 分析历史趋势
                trend = StockScanner.analyze_trend(prices)
                trend_tag = ""
                if trend == "BULL":
                    trend_tag = " <span style='color:#10b981;'>[牛市]</span>"
                elif trend == "BEAR":
                    trend_tag = " <span style='color:#ef4444;'>[熊市]</span>"
                else:
                    trend_tag = " <span style='color:#9ca3af;'>[横盘]</span>"
                
                curr_p = price_cache.get(s, prices[-1])
                
                # 判断超买超卖状态
                is_overbought = rsi > 70
                is_oversold = rsi < 30
                is_held = s in holds
                
                # 生成标签
                rsi_color = "#10b981" if rsi < 32 else "#ef4444" if rsi > 68 else "#9ca3af"
                macd_tag = " <span style='color:#10b981;'>[↗️金叉]</span>" if macd_h > 0 else " <span style='color:#ef4444;'>[↘️死叉]</span>"
                bb_tag = StockScanner._get_bb_tag(curr_p, boll_upper, boll_lower)
                ema_tag = StockScanner._get_ema_tag(ema_short, ema_long)
                kdj_tag = StockScanner._get_kdj_tag(k)
                cci_tag = StockScanner._get_cci_tag(cci)
                hold_tag = f" <b style='color:#3b82f6;'>[已持仓]</b>" if is_held else ""
                
                # 打印详细的股票信息
                MonitorLink.log(f"📊 [扫描] {s} | 现价: {curr_p:.2f} | RSI: {rsi:.1f} | MACD: {macd_h:.3f} | KDJ: {k:.1f} | CCI: {cci:.1f} | 超买: {is_overbought} | 超卖: {is_oversold} | 持仓: {is_held}{hold_tag}{trend_tag}")
                MonitorLink.log(f"   [布林带] 中轨: {boll_mid:.2f} | 上轨: {boll_upper:.2f} | 下轨: {boll_lower:.2f}{bb_tag}")
                MonitorLink.log(f"   [趋势] EMA12: {ema_short:.2f} | EMA26: {ema_long:.2f}{ema_tag} | ROC: {roc:.2f}% | ATR: {atr:.2f}")
                MonitorLink.log(f"   [支撑阻力] 支撑: {support:.2f} | 阻力: {resistance:.2f} | 市场环境: {market_env}")
                
                # 记录汇总数据
                summary_data.append(f"{s}(P:{curr_p:.2f},RSI:{rsi:.1f},MACD:{macd_h:.2f},KDJ:{k:.1f},CCI:{cci:.1f},ATR:{atr:.2f},ROC:{roc:.2f},TREND:{trend})")
                
            except Exception as e:
                if "301600" not in str(e):
                    MonitorLink.log(f"⚠️ [扫描异常] {s} | 异常: {str(e)[:100]}")
                continue
        
        return summary_data
    
    @staticmethod
    def _get_bb_tag(curr_p, boll_upper, boll_lower):
        """生成布林带标签"""
        if curr_p >= boll_upper:
            return " <b style='color:#ef4444;'>[触及上轨]</b>"
        elif curr_p <= boll_lower:
            return " <b style='color:#10b981;'>[触及下轨]</b>"
        return ""
    
    @staticmethod
    def _get_ema_tag(ema_short, ema_long):
        """生成EMA趋势标签"""
        if ema_short > ema_long:
            return " <span style='color:#10b981;'>[上升趋势]</span>"
        else:
            return " <span style='color:#ef4444;'>[下降趋势]</span>"
    
    @staticmethod
    def _get_kdj_tag(k):
        """生成KDJ标签"""
        if k > 80:
            return " <span style='color:#ef4444;'>[KDJ超买]</span>"
        elif k < 20:
            return " <span style='color:#10b981;'>[KDJ超卖]</span>"
        return ""
    
    @staticmethod
    def _get_cci_tag(cci):
        """生成CCI标签"""
        if cci > 100:
            return " <span style='color:#ef4444;'>[CCI超买]</span>"
        elif cci < -100:
            return " <span style='color:#10b981;'>[CCI超卖]</span>"
        return ""
    
    @staticmethod
    def extract_stock_data(summary_data, target):
        """从汇总数据中提取目标股票的技术指标"""
        curr_p = 0.0
        rsi = 0.0
        kdj_k = 0.0
        cci = 0.0
        macd_h = 0.0
        atr = 0.0
        roc = 0.0
        trend = ""
        
        for item in summary_data:
            if target in item:
                price_match = re.search(r'P:(\d+\.\d+)', item)
                rsi_match = re.search(r'RSI:(\d+\.\d+)', item)
                kdj_match = re.search(r'KDJ:(\d+\.\d+)', item)
                cci_match = re.search(r'CCI:(\d+\.\d+)', item)
                macd_match = re.search(r'MACD:(\d+\.\d+)', item)
                atr_match = re.search(r'ATR:(\d+\.\d+)', item)
                roc_match = re.search(r'ROC:(\d+\.\d+)', item)
                trend_match = re.search(r'TREND:(\w+)', item)
                
                if price_match:
                    curr_p = float(price_match.group(1))
                if rsi_match:
                    rsi = float(rsi_match.group(1))
                if kdj_match:
                    kdj_k = float(kdj_match.group(1))
                if cci_match:
                    cci = float(cci_match.group(1))
                if macd_match:
                    macd_h = float(macd_match.group(1))
                if atr_match:
                    atr = float(atr_match.group(1))
                if roc_match:
                    roc = float(roc_match.group(1))
                if trend_match:
                    trend = trend_match.group(1)
                break
        
        return {
            "price": curr_p,
            "rsi": rsi,
            "kdj": kdj_k,
            "cci": cci,
            "macd": macd_h,
            "atr": atr,
            "roc": roc,
            "trend": trend
        }
    
    @staticmethod
    def analyze_trend(prices, period=30):
        """
        分析股票的历史趋势
        返回趋势类型：BULL（牛市）、BEAR（熊市）、SIDE（横盘）
        """
        if len(prices) < period:
            return "UNKNOWN"
        
        # 计算长期趋势
        recent_prices = prices[-period:]
        oldest_price = recent_prices[0]
        newest_price = recent_prices[-1]
        
        # 计算价格变化百分比
        price_change = (newest_price - oldest_price) / oldest_price * 100
        
        # 定义趋势阈值
        bull_threshold = 5.0  # 上涨5%以上为牛市
        bear_threshold = -5.0  # 下跌5%以上为熊市
        
        if price_change > bull_threshold:
            return "BULL"
        elif price_change < bear_threshold:
            return "BEAR"
        else:
            return "SIDE"
