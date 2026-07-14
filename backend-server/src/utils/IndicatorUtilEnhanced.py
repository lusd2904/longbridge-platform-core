"""
量化+AI分析优化建议

当前分析维度：
1. RSI（相对强弱指标）- 超买超卖
2. 布林带（Bollinger Bands）- 价格波动范围
3. MACD（指数平滑异同移动平均线）- 趋势判断

建议增加的多维度分析：

1. 成交量分析
   - 成交量放大确认价格变动
   - OBV（能量潮）- 资金流向
   - Volume MA（成交量均线）- 成交量趋势

2. 波动率分析
   - ATR（平均真实波幅）- 波动性衡量
   - 波动率突破策略

3. 趋势分析
   - EMA（指数移动平均线）- 短期、中期、长期趋势
   - SMA（简单移动平均线）- 趋势支撑阻力
   - 趋势强度判断

4. 动量指标
   - KDJ（随机指标）- 超买超卖确认
   - ROC（变动率）- 动量强度
   - CCI（顺势指标）- 价格偏离度

5. 支撑阻力位
   - 基于价格历史数据计算
   - 关键价位识别

6. 市场环境判断
   - 牛市/熊市/震荡市
   - 市场情绪指数

7. 风险评估
   - 仓位管理
   - 止损止盈策略
   - 风险收益比

8. AI分析优化
   - 增加更多技术指标到AI提示词
   - 优化AI海选逻辑
   - 增加市场环境判断
   - 多模型综合决策
"""

import pandas as pd
import pandas_ta_classic as ta

class IndicatorUtilEnhanced:
    @staticmethod
    def calculate_atr(prices, highs, lows, period=14):
        """计算平均真实波幅（ATR）- 衡量波动性 (已切换至 pandas-ta)"""
        if len(prices) <= period: return 0.0
        h, l, c = pd.Series(highs), pd.Series(lows), pd.Series(prices)
        atr = ta.atr(high=h, low=l, close=c, length=period)
        if atr is None or atr.dropna().empty: return 0.0
        return float(atr.iloc[-1])

    @staticmethod
    def calculate_ema(prices, period):
        """计算指数移动平均线（EMA） (已切换至 pandas-ta)"""
        if len(prices) < period: return prices[-1]
        s = pd.Series(prices)
        ema = ta.ema(s, length=period)
        if ema is None or ema.dropna().empty: return prices[-1]
        return float(ema.iloc[-1])

    @staticmethod
    def calculate_sma(prices, period):
        """计算简单移动平均线（SMA） (已切换至 pandas-ta)"""
        if len(prices) < period: return prices[-1]
        s = pd.Series(prices)
        sma = ta.sma(s, length=period)
        if sma is None or sma.dropna().empty: return prices[-1]
        return float(sma.iloc[-1])

    @staticmethod
    def calculate_kdj(prices, highs, lows, period=9, m1=3, m2=3):
        """计算KDJ指标（随机指标） (已切换至 pandas-ta)"""
        if len(prices) < period: return 50.0, 50.0, 50.0
        h, l, c = pd.Series(highs), pd.Series(lows), pd.Series(prices)
        kdj = ta.kdj(high=h, low=l, close=c, length=period, signal=m1)
        if kdj is None or kdj.dropna().empty: return 50.0, 50.0, 50.0
        last_row = kdj.iloc[-1]
        # pandas_ta columns: K, D, J
        return float(last_row.iloc[0]), float(last_row.iloc[1]), float(last_row.iloc[2])

    @staticmethod
    def calculate_obv(prices, volumes):
        """计算能量潮（OBV）- 资金流向 (已切换至 pandas-ta)"""
        if len(prices) != len(volumes) or len(prices) < 2: return 0.0
        c, v = pd.Series(prices), pd.Series(volumes)
        obv = ta.obv(close=c, volume=v)
        if obv is None or obv.dropna().empty: return 0.0
        return float(obv.iloc[-1])

    @staticmethod
    def calculate_roc(prices, period=12):
        """计算变动率（ROC）- 动量强度 (已切换至 pandas-ta)"""
        if len(prices) <= period: return 0.0
        s = pd.Series(prices)
        roc = ta.roc(s, length=period)
        if roc is None or roc.dropna().empty: return 0.0
        return float(roc.iloc[-1])

    @staticmethod
    def calculate_cci(prices, highs, lows, period=20):
        """计算顺势指标（CCI）- 价格偏离度 (已切换至 pandas-ta)"""
        if len(prices) < period: return 0.0
        h, l, c = pd.Series(highs), pd.Series(lows), pd.Series(prices)
        cci = ta.cci(high=h, low=l, close=c, length=period)
        if cci is None or cci.dropna().empty: return 0.0
        return float(cci.iloc[-1])

    @staticmethod
    def calculate_support_resistance(prices, period=20):
        """计算支撑位和阻力位"""
        if len(prices) < period:
            return prices[-1], prices[-1]
        
        recent_prices = prices[-period:]
        
        # 简单支撑阻力位计算
        support = min(recent_prices)
        resistance = max(recent_prices)
        
        # 更精确的支撑阻力位（基于价格聚集区）
        price_counts = {}
        for p in recent_prices:
            rounded_p = round(p, 2)
            price_counts[rounded_p] = price_counts.get(rounded_p, 0) + 1
        
        # 找出价格聚集最多的区域
        if price_counts:
            sorted_prices = sorted(price_counts.items(), key=lambda x: x[1], reverse=True)
            if len(sorted_prices) >= 2:
                resistance = sorted_prices[0][0]
                support = sorted_prices[-1][0]
        
        return support, resistance

    @staticmethod
    def analyze_market_environment(prices, period=50):
        """分析市场环境（牛市/熊市/震荡市）"""
        if len(prices) < period:
            return "未知"
        
        recent_prices = prices[-period:]
        short_ma = sum(recent_prices[-20:]) / 20
        long_ma = sum(recent_prices) / period
        
        # 计算价格波动率
        volatility = (max(recent_prices) - min(recent_prices)) / sum(recent_prices) * period
        
        # 判断市场环境
        if short_ma > long_ma * 1.02:
            if volatility < 0.1:
                return "牛市-稳定"
            else:
                return "牛市-波动"
        elif short_ma < long_ma * 0.98:
            if volatility < 0.1:
                return "熊市-稳定"
            else:
                return "熊市-波动"
        else:
            if volatility < 0.05:
                return "震荡市-平稳"
            else:
                return "震荡市-剧烈"

    @staticmethod
    def calculate_risk_reward_ratio(entry_price, stop_loss, take_profit):
        """计算风险收益比"""
        if stop_loss == 0:
            return 0.0
        
        risk = abs(entry_price - stop_loss)
        reward = abs(take_profit - entry_price)
        
        if risk == 0:
            return 0.0
        
        return reward / risk

    @staticmethod
    def calculate_position_size(account_balance, risk_per_trade, entry_price, stop_loss):
        """计算合理的仓位大小"""
        if stop_loss == 0 or entry_price == 0:
            return 0
        
        risk_amount = account_balance * risk_per_trade
        risk_per_share = abs(entry_price - stop_loss)
        
        if risk_per_share == 0:
            return 0
        
        position_size = risk_amount / risk_per_share
        return int(position_size)
