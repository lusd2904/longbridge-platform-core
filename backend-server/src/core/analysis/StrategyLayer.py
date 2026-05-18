from utils.IndicatorUtil import IndicatorUtil
from config.Config import AppConfig

class StrategyLayer:
    @staticmethod
    def rsi_scan(symbol, candles, is_held):
        """Layer 2: 算法初步筛选"""
        prices = [float(c.close) for c in candles]
        rsi = IndicatorUtil.calculate_rsi(prices)
        curr_p = prices[-1]
        
        buy_line = getattr(AppConfig, "RSI_OVER_SELL", 30)
        sell_line = getattr(AppConfig, "RSI_OVER_BUY", 70)

        if rsi < buy_line:
            return {"side": "BUY", "rsi": rsi, "price": curr_p}
        elif rsi > sell_line and is_held:
            return {"side": "SELL", "rsi": rsi, "price": curr_p}
        elif is_held:
            return {"side": "HOLD_MONITOR", "rsi": rsi, "price": curr_p}
        return None