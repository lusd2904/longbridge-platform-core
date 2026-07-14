import pandas as pd
import pandas_ta_classic as ta

class IndicatorUtil:
    @staticmethod
    def calculate_rsi(prices, period=14):
        """物理计算 RSI 指标 (已切换至 pandas-ta)"""
        if len(prices) <= period: return 50.0
        s = pd.Series(prices)
        rsi = ta.rsi(s, length=period)
        if rsi is None or rsi.dropna().empty: return 50.0
        return float(rsi.iloc[-1])

    @staticmethod
    def calculate_boll(prices, period=20, k=2):
        """物理计算布林带 (已切换至 pandas-ta)"""
        if len(prices) < period:
            return prices[-1], prices[-1], prices[-1]
        s = pd.Series(prices)
        bb = ta.bbands(s, length=period, std=k)
        if bb is None or bb.dropna().empty:
            return prices[-1], prices[-1], prices[-1]
        last_row = bb.iloc[-1]
        # pandas_ta columns: BBL, BBM, BBU
        return float(last_row.iloc[1]), float(last_row.iloc[2]), float(last_row.iloc[0])

    @staticmethod
    def calculate_macd(prices, fast=12, slow=26, signal=9):
        """物理计算 MACD (已切换至 pandas-ta)"""
        if len(prices) < slow:
            return 0.0, 0.0, 0.0
        s = pd.Series(prices)
        m = ta.macd(s, fast=fast, slow=slow, signal=signal)
        if m is None or m.dropna().empty:
            return 0.0, 0.0, 0.0
        last_row = m.iloc[-1]
        dif = float(last_row.iloc[0])
        dea = float(last_row.iloc[2])
        macd_hist = (dif - dea) * 2
        return dif, dea, macd_hist