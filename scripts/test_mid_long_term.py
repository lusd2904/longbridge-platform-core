"""
测试中长线价值策略 (Mid-Long Term Value Strategy Tester)
"""
import sys
import os
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

# 添加 src 到路径
sys.path.append(os.path.join(os.path.dirname(__file__), '../backend-server/src'))

from strategy.strategy_engine import StrategyConfig, StrategyType, BacktestEngine, create_strategy

def generate_mock_data(symbol: str, days: int = 400) -> pd.DataFrame:
    """生成带有牛熊周期的模拟数据"""
    np.random.seed(42 + sum(ord(c) for c in symbol))
    
    dates = [datetime(2023, 1, 1) + timedelta(days=i) for i in range(days)]
    
    # 模拟一个长期向上的趋势，中途有回调
    t = np.linspace(0, 10, days)
    trend = 100 + 5 * t  # 基础上涨
    cycle = 20 * np.sin(t) # 周期性波动
    noise = np.random.normal(0, 2, days)
    
    close = trend + cycle + noise
    
    df = pd.DataFrame({
        'open': close - np.random.normal(0, 1, days),
        'high': close + np.abs(np.random.normal(0, 2, days)),
        'low': close - np.abs(np.random.normal(0, 2, days)),
        'close': close,
        'volume': np.random.randint(1000000, 5000000, days)
    }, index=dates)
    
    return df

def run_test():
    print("🚀 正在初始化中长线价值策略测试...")
    
    # 我们测试三只股票：AAPL（好股），TSLA（波动大），JUNK（基本面差的模拟股）
    symbols = ["AAPL", "TSLA", "JUNK"]
    data_dict = {}
    
    print("📊 正在生成回测数据 (400天)...")
    for sym in symbols:
        data_dict[sym] = generate_mock_data(sym, days=400)
    
    config = StrategyConfig(
        name="Value-Pullback-Portfolio",
        type=StrategyType.MID_LONG_TERM_VALUE,
        symbols=symbols,
        parameters={
            "sma_period": 50, # 测试用缩短，否则400天出不来多少信号
            "rsi_period": 14,
            "atr_period": 14,
            "atr_multiplier": 2.5
        }
    )
    
    strategy = create_strategy(config)
    engine = BacktestEngine()
    
    start_date = datetime(2023, 1, 1)
    end_date = datetime(2023, 1, 1) + timedelta(days=399)
    
    print("\n⏳ 开始运行回测引擎...")
    result = engine.run_backtest(strategy, data_dict, start_date, end_date, initial_capital=100000)
    
    print("\n" + "="*50)
    print("📈 回测结果摘要 (Backtest Results)")
    print("="*50)
    print(f"策略名称: {result.strategy_name}")
    print(f"初始资金: ${result.initial_capital:,.2f}")
    print(f"最终资金: ${result.final_capital:,.2f}")
    print(f"总收益率: {result.total_return:.2%}")
    print(f"最大回撤: {result.max_drawdown:.2%}")
    print(f"交易次数: {result.total_trades}")
    print(f"胜率:     {result.win_rate:.2%}")
    print(f"盈亏比:   {result.profit_factor:.2f}")
    
    print("\n🔍 详细交易记录 (最后5笔):")
    for trade in result.trades[-5:]:
        action = trade['action'].upper()
        sym = trade['symbol']
        price = trade['price']
        qty = trade['quantity']
        date = trade['timestamp'][:10]
        print(f"[{date}] {action} {sym} {qty}股 @ ${price:.2f}")

if __name__ == "__main__":
    run_test()
