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

import math

class IndicatorUtilEnhanced:
    @staticmethod
    def calculate_atr(prices, highs, lows, period=14):
        """计算平均真实波幅（ATR）- 衡量波动性"""
        if len(prices) <= period:
            return 0.0
        
        true_ranges = []
        for i in range(1, len(prices)):
            high = highs[i]
            low = lows[i]
            prev_close = prices[i-1]
            
            tr1 = high - low
            tr2 = abs(high - prev_close)
            tr3 = abs(low - prev_close)
            true_ranges.append(max(tr1, tr2, tr3))
        
        atr = sum(true_ranges[:period]) / period
        for i in range(period, len(true_ranges)):
            atr = (atr * (period - 1) + true_ranges[i]) / period
        
        return atr

    @staticmethod
    def calculate_ema(prices, period):
        """计算指数移动平均线（EMA）"""
        if len(prices) < period:
            return prices[-1]
        
        ema = sum(prices[:period]) / period
        multiplier = 2 / (period + 1)
        
        for i in range(period, len(prices)):
            ema = (prices[i] - ema) * multiplier + ema
        
        return ema

    @staticmethod
    def calculate_sma(prices, period):
        """计算简单移动平均线（SMA）"""
        if len(prices) < period:
            return prices[-1]
        return sum(prices[-period:]) / period

    @staticmethod
    def calculate_kdj(prices, highs, lows, period=9, m1=3, m2=3):
        """计算KDJ指标（随机指标）"""
        if len(prices) < period:
            return 50.0, 50.0, 50.0
        
        rsv_list = []
        for i in range(period, len(prices)):
            recent_highs = highs[i-period:i]
            recent_lows = lows[i-period:i]
            
            high_n = max(recent_highs)
            low_n = min(recent_lows)
            close_n = prices[i]
            
            if high_n == low_n:
                rsv = 50.0
            else:
                rsv = (close_n - low_n) / (high_n - low_n) * 100
            
            rsv_list.append(rsv)
        
        # 计算K、D、J
        k = 50.0
        d = 50.0
        
        for rsv in rsv_list:
            k = (2/3) * k + (1/3) * rsv
            d = (2/3) * d + (1/3) * k
        
        j = 3 * k - 2 * d
        
        return k, d, j

    @staticmethod
    def calculate_obv(prices, volumes):
        """计算能量潮（OBV）- 资金流向"""
        if len(prices) != len(volumes) or len(prices) < 2:
            return 0.0
        
        obv = 0.0
        for i in range(1, len(prices)):
            if prices[i] > prices[i-1]:
                obv += volumes[i]
            elif prices[i] < prices[i-1]:
                obv -= volumes[i]
        
        return obv

    @staticmethod
    def calculate_roc(prices, period=12):
        """计算变动率（ROC）- 动量强度"""
        if len(prices) <= period:
            return 0.0
        
        current_price = prices[-1]
        past_price = prices[-period-1]
        
        if past_price == 0:
            return 0.0
        
        roc = (current_price - past_price) / past_price * 100
        return roc

    @staticmethod
    def calculate_cci(prices, highs, lows, period=20):
        """计算顺势指标（CCI）- 价格偏离度"""
        if len(prices) < period:
            return 0.0
        
        typical_prices = [(h + l + c) / 3 for h, l, c in zip(highs, lows, prices)]
        
        # 计算移动平均
        sma_tp = sum(typical_prices[-period:]) / period
        
        # 计算平均偏差
        mean_deviation = sum(abs(tp - sma_tp) for tp in typical_prices[-period:]) / period
        
        if mean_deviation == 0:
            return 0.0
        
        cci = (typical_prices[-1] - sma_tp) / (0.015 * mean_deviation)
        return cci

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
