import math

class IndicatorUtil:
    @staticmethod
    def calculate_rsi(prices, period=14):
        """物理计算 RSI 指标"""
        if len(prices) <= period: return 50.0
        deltas = [prices[i+1] - prices[i] for i in range(len(prices)-1)]
        gains = [max(d, 0) for d in deltas]
        losses = [max(-d, 0) for d in deltas]
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        for i in range(period, len(deltas)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0: return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    @staticmethod
    def calculate_boll(prices, period=20, k=2):
        """物理计算布林带 (中轨, 上轨, 下轨)"""
        if len(prices) < period:
            return prices[-1], prices[-1], prices[-1]
        recent_prices = prices[-period:]
        ma = sum(recent_prices) / period
        variance = sum([(p - ma) ** 2 for p in recent_prices]) / period
        std_dev = math.sqrt(variance)
        upper = ma + (k * std_dev)
        lower = ma - (k * std_dev)
        return ma, upper, lower

    @staticmethod
    def calculate_macd(prices, fast=12, slow=26, signal=9):
        """物理计算 MACD (DIF, DEA, Histogram)"""
        def get_ema(data, n):
            if not data: return 0
            ema_list = [data[0]]
            mult = 2 / (n + 1)
            for i in range(1, len(data)):
                ema_list.append((data[i] - ema_list[-1]) * mult + ema_list[-1])
            return ema_list

        ema_fast = get_ema(prices, fast)
        ema_slow = get_ema(prices, slow)
        dif = [f - s for f, s in zip(ema_fast, ema_slow)]
        dea = get_ema(dif, signal)
        macd_hist = [(f - s) * 2 for f, s in zip(dif, dea)]
        return dif[-1], dea[-1], macd_hist[-1]