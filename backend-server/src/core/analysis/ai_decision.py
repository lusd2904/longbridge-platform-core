from utils.MonitorLink import MonitorLink
from config.Config import AppConfig

def ai_trade_decision(symbol_data: dict, is_held: bool):
    """
    单体算法决策逻辑 (Layer 2)
    """
    sym = symbol_data.get("symbol")
    rsi = symbol_data.get("rsi", 50.0)
    price = symbol_data.get("price", 0.0)

    # 物理读取 Config.py 中的大写配置
    buy_threshold = getattr(AppConfig, "RSI_OVER_SELL", 30)
    sell_threshold = getattr(AppConfig, "RSI_OVER_BUY", 70)

    # 强行打印扫描过程，确保 4 层扫描可见
    MonitorLink.log(f"📡 [扫描中] {sym} | 当前RSI: {rsi:.1f} | 目标区间: {buy_threshold}-{sell_threshold}")

    decision = "HOLD"
    reason = "指标处于正常区间"

    # 算法判定逻辑
    if rsi < buy_threshold:
        decision = "BUY"
        reason = f"RSI({rsi:.1f}) 触发超卖阈值 {buy_threshold}"
    elif rsi > sell_threshold and is_held:
        decision = "SELL"
        reason = f"RSI({rsi:.1f}) 触发超买阈值 {sell_threshold} 且持有中"

    # 只有产生交易建议时才高亮显示
    if decision != "HOLD":
        color = "#ef4444" if decision == "BUY" else "#10b981"
        MonitorLink.log(f"💡 <span style='color:{color};'>[算法建议]</span> {sym} -> {decision} ({reason})")
    
    return decision