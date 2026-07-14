"""
量化策略引擎
策略定义、回测、优化
"""
import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import json
import pandas_ta_classic as ta

logger = logging.getLogger(__name__)


class SignalType(Enum):
    """信号类型"""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class StrategyType(Enum):
    """策略类型"""
    TREND_FOLLOWING = "trend_following"      # 趋势跟踪
    MEAN_REVERSION = "mean_reversion"        # 均值回归
    MOMENTUM = "momentum"                    # 动量策略
    BREAKOUT = "breakout"                    # 突破策略
    PAIRS_TRADING = "pairs_trading"          # 配令人交易
    MULTI_FACTOR = "multi_factor"            # 多因子策略
    MID_LONG_TERM_VALUE = "mid_long_term_value"  # 中长线价值策略


@dataclass
class Signal:
    """交易信号"""
    type: SignalType
    symbol: str
    timestamp: datetime
    price: float
    confidence: float = 1.0
    metadata: Dict = field(default_factory=dict)


@dataclass
class StrategyConfig:
    """策略配置"""
    name: str
    type: StrategyType
    symbols: List[str]
    parameters: Dict[str, Any] = field(default_factory=dict)
    risk_limits: Dict = field(default_factory=dict)
    enabled: bool = True


@dataclass
class BacktestResult:
    """回测结果"""
    strategy_name: str
    start_date: datetime
    end_date: datetime
    initial_capital: float
    final_capital: float
    total_return: float
    annual_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    equity_curve: List[Dict] = field(default_factory=list)
    trades: List[Dict] = field(default_factory=list)
    monthly_returns: Dict = field(default_factory=dict)


class BaseStrategy:
    """策略基类"""
    
    def __init__(self, config: StrategyConfig):
        self.config = config
        self.signals: List[Signal] = []
        self.positions: Dict[str, Dict] = {}
        self.cash: float = 0
        self.equity: float = 0
    
    def initialize(self, initial_capital: float):
        """初始化策略"""
        self.cash = initial_capital
        self.equity = initial_capital
        self.signals = []
        self.positions = {}
    
    def on_data(self, timestamp: datetime, data: Dict[str, pd.DataFrame]):
        """
        处理数据
        子类需要重写此方法
        """
        raise NotImplementedError
    
    def generate_signal(
        self,
        symbol: str,
        signal_type: SignalType,
        price: float,
        confidence: float = 1.0,
        metadata: Dict = None
    ) -> Signal:
        """生成信号"""
        signal = Signal(
            type=signal_type,
            symbol=symbol,
            timestamp=datetime.now(),
            price=price,
            confidence=confidence,
            metadata=metadata or {}
        )
        self.signals.append(signal)
        return signal
    
    def get_parameters(self) -> Dict:
        """获取策略参数"""
        return self.config.parameters
    
    def set_parameters(self, parameters: Dict):
        """设置策略参数"""
        self.config.parameters.update(parameters)


class MovingAverageCrossStrategy(BaseStrategy):
    """移动平均线交叉策略"""
    
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.fast_period = config.parameters.get("fast_period", 10)
        self.slow_period = config.parameters.get("slow_period", 30)
        self.data_history: Dict[str, pd.DataFrame] = {}
    
    def on_data(self, timestamp: datetime, data: Dict[str, pd.DataFrame]):
        """处理数据并生成信号"""
        for symbol, df in data.items():
            if len(df) < self.slow_period:
                continue
            
            # 计算移动平均线
            fast_ma = df['close'].rolling(window=self.fast_period).mean().iloc[-1]
            slow_ma = df['close'].rolling(window=self.slow_period).mean().iloc[-1]
            
            # 获取前一天的均线
            if len(df) > self.slow_period:
                prev_fast_ma = df['close'].rolling(window=self.fast_period).mean().iloc[-2]
                prev_slow_ma = df['close'].rolling(window=self.slow_period).mean().iloc[-2]
                
                current_price = df['close'].iloc[-1]
                
                # 金叉：快线上穿慢线
                if prev_fast_ma <= prev_slow_ma and fast_ma > slow_ma:
                    self.generate_signal(
                        symbol=symbol,
                        signal_type=SignalType.BUY,
                        price=current_price,
                        confidence=0.8,
                        metadata={
                            "fast_ma": fast_ma,
                            "slow_ma": slow_ma,
                            "signal": "golden_cross"
                        }
                    )
                
                # 死叉：快线下穿慢线
                elif prev_fast_ma >= prev_slow_ma and fast_ma < slow_ma:
                    self.generate_signal(
                        symbol=symbol,
                        signal_type=SignalType.SELL,
                        price=current_price,
                        confidence=0.8,
                        metadata={
                            "fast_ma": fast_ma,
                            "slow_ma": slow_ma,
                            "signal": "death_cross"
                        }
                    )


class RSIStrategy(BaseStrategy):
    """RSI策略"""
    
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.period = config.parameters.get("period", 14)
        self.overbought = config.parameters.get("overbought", 70)
        self.oversold = config.parameters.get("oversold", 30)
    
    def on_data(self, timestamp: datetime, data: Dict[str, pd.DataFrame]):
        """处理数据并生成信号"""
        for symbol, df in data.items():
            if len(df) < self.period:
                continue
            
            # 计算RSI
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=self.period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=self.period).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            
            current_rsi = rsi.iloc[-1]
            current_price = df['close'].iloc[-1]
            
            # 超卖买入
            if current_rsi < self.oversold:
                self.generate_signal(
                    symbol=symbol,
                    signal_type=SignalType.BUY,
                    price=current_price,
                    confidence=(self.oversold - current_rsi) / self.oversold,
                    metadata={"rsi": current_rsi, "condition": "oversold"}
                )
            
            # 超买卖出
            elif current_rsi > self.overbought:
                self.generate_signal(
                    symbol=symbol,
                    signal_type=SignalType.SELL,
                    price=current_price,
                    confidence=(current_rsi - self.overbought) / (100 - self.overbought),
                    metadata={"rsi": current_rsi, "condition": "overbought"}
                )

class MidLongTermValueStrategy(BaseStrategy):
    """中长线价值策略 (好股好价格)"""
    
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.sma_period = config.parameters.get("sma_period", 200)      # 200日牛熊分界线
        self.rsi_period = config.parameters.get("rsi_period", 14)       # RSI 周期
        self.atr_period = config.parameters.get("atr_period", 14)       # ATR 周期
        self.atr_multiplier = config.parameters.get("atr_multiplier", 3.0) # 移动止损乘数
        
        # 记录每只股票的入场价和最高价（用于移动止盈止损）
        self.entry_prices: Dict[str, float] = {}
        self.highest_prices: Dict[str, float] = {}

    def on_data(self, timestamp: datetime, data: Dict[str, pd.DataFrame]):
        """处理数据并生成信号"""
        
        # 1. 模拟调用基本面过滤（假设在每次月度扫描时执行，此处简化直接从我们建的 Fetcher 取）
        from utils.FundamentalDataFetcher import fundamental_fetcher
        universe = list(data.keys())
        good_stocks = fundamental_fetcher.filter_universe(universe, min_roe=0.08, max_pe=40.0)
        
        for symbol, df in data.items():
            if len(df) < self.sma_period:
                continue
                
            # 计算长周期指标 (基于 pandas-ta-classic)
            df.ta.sma(length=self.sma_period, append=True)
            df.ta.rsi(length=self.rsi_period, append=True)
            df.ta.atr(length=self.atr_period, append=True)
            
            sma_col = f"SMA_{self.sma_period}"
            rsi_col = f"RSI_{self.rsi_period}"
            atr_col = f"ATRr_{self.atr_period}"
            
            # 确保指标都算出来了
            if sma_col not in df.columns or rsi_col not in df.columns or atr_col not in df.columns:
                continue
                
            current_price = df['close'].iloc[-1]
            current_sma = df[sma_col].iloc[-1]
            current_rsi = df[rsi_col].iloc[-1]
            current_atr = df[atr_col].iloc[-1]
            
            # 检查是否有持仓
            has_position = False
            # 这里的 self.positions 由 BacktestEngine 更新
            if symbol in self.positions and self.positions[symbol].get("quantity", 0) > 0:
                has_position = True
            
            # ===============================
            # 卖出逻辑 (更好的价格卖出去：移动止损)
            # ===============================
            if has_position:
                if symbol not in self.highest_prices:
                    self.highest_prices[symbol] = current_price
                    
                # 更新自买入以来的最高价
                if current_price > self.highest_prices[symbol]:
                    self.highest_prices[symbol] = current_price
                    
                # 计算动态止损线：最高价 - N倍ATR
                trailing_stop_price = self.highest_prices[symbol] - (self.atr_multiplier * current_atr)
                
                # 如果跌破移动止损线，获利了结或止损
                if current_price < trailing_stop_price:
                    self.generate_signal(
                        symbol=symbol,
                        signal_type=SignalType.SELL,
                        price=current_price,
                        confidence=1.0,
                        metadata={
                            "reason": "trailing_stop",
                            "highest_price": self.highest_prices[symbol],
                            "stop_price": trailing_stop_price
                        }
                    )
                    # 重置记录
                    self.highest_prices.pop(symbol, None)
                continue # 已持仓的暂时不考虑继续加仓逻辑
            
            # ===============================
            # 买入逻辑 (好价格买好股)
            # ===============================
            # 1. 必须是基本面筛选出的“好股”
            if symbol not in good_stocks:
                continue
                
            # 2. “好价格”条件：价格在200日均线之上（处于长期多头趋势），但出现了短线超卖（回档建仓）
            # 或者刚好回踩 200 日均线 (价格在 SMA200 的 1.00 ~ 1.05 之间)
            is_uptrend = current_price > current_sma
            is_pullback = current_rsi < 40  # 中长线可以放宽到 40 就算逢低买入
            is_near_support = current_sma * 1.0 <= current_price <= current_sma * 1.05
            
            if is_uptrend and (is_pullback or is_near_support):
                # 产生强烈的买入信号
                confidence = 0.8
                if is_pullback and is_near_support:
                    confidence = 1.0  # 共振：既超卖又踩到支撑线，极佳买点
                    
                self.generate_signal(
                    symbol=symbol,
                    signal_type=SignalType.BUY,
                    price=current_price,
                    confidence=confidence,
                    metadata={
                        "reason": "value_pullback_support",
                        "sma200": current_sma,
                        "rsi": current_rsi
                    }
                )
                self.highest_prices[symbol] = current_price


class BacktestEngine:
    """回测引擎"""
    
    def __init__(self):
        self.commission_rate = 0.001  # 手续费率 0.1%
        self.slippage = 0.001         # 滑点 0.1%
    
    def run_backtest(
        self,
        strategy: BaseStrategy,
        data: Dict[str, pd.DataFrame],
        start_date: datetime,
        end_date: datetime,
        initial_capital: float = 100000.0
    ) -> BacktestResult:
        """
        运行回测
        
        Args:
            strategy: 策略实例
            data: 历史数据 {symbol: DataFrame}
            start_date: 开始日期
            end_date: 结束日期
            initial_capital: 初始资金
        
        Returns:
            回测结果
        """
        logger.info(f"开始回测: {strategy.config.name}")
        
        # 初始化策略
        strategy.initialize(initial_capital)
        
        # 准备数据
        all_dates = self._get_trading_dates(data, start_date, end_date)
        
        # 回测状态
        positions: Dict[str, Dict] = {}
        cash = initial_capital
        equity_curve = []
        trades = []
        
        # 遍历每个交易日
        for date in all_dates:
            # 获取当日数据
            day_data = self._get_day_data(data, date)
            if not day_data:
                continue
            
            # 策略处理数据
            strategy.on_data(date, day_data)
            
            # 执行信号
            for signal in strategy.signals:
                if signal.timestamp.date() == date.date():
                    trade_result = self._execute_signal(
                        signal, positions, cash, initial_capital
                    )
                    if trade_result:
                        trades.append(trade_result)
                        cash = trade_result["remaining_cash"]
            
            # 计算当日权益
            equity = self._calculate_equity(cash, positions, day_data)
            equity_curve.append({
                "date": date.isoformat(),
                "equity": equity,
                "cash": cash
            })
        
        # 计算回测指标
        result = self._calculate_metrics(
            strategy.config.name,
            start_date,
            end_date,
            initial_capital,
            equity_curve,
            trades
        )
        
        logger.info(f"回测完成: 总收益 {result.total_return:.2%}")
        
        return result
    
    def _get_trading_dates(
        self,
        data: Dict[str, pd.DataFrame],
        start_date: datetime,
        end_date: datetime
    ) -> List[datetime]:
        """获取交易日列表"""
        dates = set()
        for df in data.values():
            mask = (df.index >= start_date) & (df.index <= end_date)
            dates.update(df.index[mask].tolist())
        return sorted(list(dates))
    
    def _get_day_data(
        self,
        data: Dict[str, pd.DataFrame],
        date: datetime
    ) -> Dict[str, pd.DataFrame]:
        """获取某日数据"""
        result = {}
        for symbol, df in data.items():
            day_df = df[df.index <= date]
            if len(day_df) > 0:
                result[symbol] = day_df
        return result
    
    def _execute_signal(
        self,
        signal: Signal,
        positions: Dict,
        cash: float,
        total_capital: float
    ) -> Optional[Dict]:
        """执行交易信号"""
        symbol = signal.symbol
        price = signal.price * (1 + self.slippage)  # 考虑滑点
        
        # 计算交易数量（简化：固定使用10%资金）
        position_size = total_capital * 0.1
        quantity = int(position_size / price)
        
        if quantity <= 0:
            return None
        
        if signal.type == SignalType.BUY:
            cost = quantity * price * (1 + self.commission_rate)
            if cost > cash:
                return None
            
            # 更新持仓
            if symbol not in positions:
                positions[symbol] = {"quantity": 0, "cost_basis": 0}
            
            old_qty = positions[symbol]["quantity"]
            old_cost = positions[symbol]["cost_basis"]
            new_qty = old_qty + quantity
            new_cost = (old_cost * old_qty + cost) / new_qty if new_qty > 0 else 0
            
            positions[symbol]["quantity"] = new_qty
            positions[symbol]["cost_basis"] = new_cost
            
            return {
                "symbol": symbol,
                "action": "buy",
                "quantity": quantity,
                "price": price,
                "cost": cost,
                "timestamp": signal.timestamp.isoformat(),
                "remaining_cash": cash - cost
            }
        
        elif signal.type == SignalType.SELL:
            if symbol not in positions or positions[symbol]["quantity"] < quantity:
                return None
            
            proceeds = quantity * price * (1 - self.commission_rate)
            
            # 更新持仓
            positions[symbol]["quantity"] -= quantity
            if positions[symbol]["quantity"] == 0:
                del positions[symbol]
            
            return {
                "symbol": symbol,
                "action": "sell",
                "quantity": quantity,
                "price": price,
                "proceeds": proceeds,
                "timestamp": signal.timestamp.isoformat(),
                "remaining_cash": cash + proceeds
            }
        
        return None
    
    def _calculate_equity(
        self,
        cash: float,
        positions: Dict,
        data: Dict[str, pd.DataFrame]
    ) -> float:
        """计算总权益"""
        equity = cash
        for symbol, pos in positions.items():
            if symbol in data and len(data[symbol]) > 0:
                current_price = data[symbol]['close'].iloc[-1]
                equity += pos["quantity"] * current_price
        return equity
    
    def _calculate_metrics(
        self,
        strategy_name: str,
        start_date: datetime,
        end_date: datetime,
        initial_capital: float,
        equity_curve: List[Dict],
        trades: List[Dict]
    ) -> BacktestResult:
        """计算回测指标"""
        if not equity_curve:
            return BacktestResult(
                strategy_name=strategy_name,
                start_date=start_date,
                end_date=end_date,
                initial_capital=initial_capital,
                final_capital=initial_capital,
                total_return=0,
                annual_return=0,
                sharpe_ratio=0,
                max_drawdown=0,
                win_rate=0,
                profit_factor=0,
                total_trades=0,
                winning_trades=0,
                losing_trades=0
            )
        
        final_capital = equity_curve[-1]["equity"]
        total_return = (final_capital - initial_capital) / initial_capital
        
        # 计算年化收益
        days = (end_date - start_date).days
        years = days / 365
        annual_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0
        
        # 计算最大回撤
        max_drawdown = self._calculate_max_drawdown(equity_curve)
        
        # 计算夏普比率（简化）
        returns = []
        for i in range(1, len(equity_curve)):
            daily_return = (equity_curve[i]["equity"] - equity_curve[i-1]["equity"]) / equity_curve[i-1]["equity"]
            returns.append(daily_return)
        
        sharpe_ratio = np.mean(returns) / np.std(returns) * np.sqrt(252) if len(returns) > 1 and np.std(returns) > 0 else 0
        
        # 计算胜率
        winning_trades = sum(1 for t in trades if t.get("pnl", 0) > 0)
        total_trades = len(trades)
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        
        # 计算盈亏比
        gross_profit = sum(t.get("pnl", 0) for t in trades if t.get("pnl", 0) > 0)
        gross_loss = abs(sum(t.get("pnl", 0) for t in trades if t.get("pnl", 0) < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        return BacktestResult(
            strategy_name=strategy_name,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            final_capital=final_capital,
            total_return=total_return,
            annual_return=annual_return,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            profit_factor=profit_factor,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=total_trades - winning_trades,
            equity_curve=equity_curve,
            trades=trades
        )
    
    def _calculate_max_drawdown(self, equity_curve: List[Dict]) -> float:
        """计算最大回撤"""
        peak = equity_curve[0]["equity"]
        max_dd = 0
        
        for point in equity_curve:
            equity = point["equity"]
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak
            max_dd = max(max_dd, dd)
        
        return max_dd


# 策略注册表
STRATEGY_REGISTRY = {
    StrategyType.TREND_FOLLOWING: MovingAverageCrossStrategy,
    StrategyType.MEAN_REVERSION: RSIStrategy,
    StrategyType.MID_LONG_TERM_VALUE: MidLongTermValueStrategy,
}


def create_strategy(config: StrategyConfig) -> BaseStrategy:
    """创建策略实例"""
    strategy_class = STRATEGY_REGISTRY.get(config.type)
    if strategy_class:
        return strategy_class(config)
    raise ValueError(f"未知的策略类型: {config.type}")
