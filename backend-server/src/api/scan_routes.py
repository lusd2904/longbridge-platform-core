"""
扫描指标相关路由
"""
from flask import Blueprint, request, jsonify
from utils.DbUtil import DbUtil
from core.broker.LongbridgeAPI import LongbridgeAPI
from core.broker.TigerBrokerAPI import TigerBrokerAPI
from core.analysis.HistoricalMarketDataService import HistoricalMarketDataService
from api.auth_routes import login_required
import traceback

scan_bp = Blueprint('scan', __name__)


def calculate_ma(prices, period):
    """计算移动平均线"""
    if len(prices) < period:
        return prices[-1] if prices else 0
    return sum(prices[-period:]) / period


def calculate_rsi(prices, period=14):
    """计算RSI指标"""
    if len(prices) < period + 1:
        return 50
    
    gains = []
    losses = []
    
    for i in range(1, len(prices)):
        change = prices[i] - prices[i-1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))
    
    if len(gains) < period:
        return 50
    
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    
    if avg_loss == 0:
        return 100
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_kdj(prices, highs, lows, n=9, m1=3, m2=3):
    """计算KDJ指标"""
    if len(prices) < n:
        return 50, 50, 50
    
    # 计算RSV
    recent_low = min(lows[-n:])
    recent_high = max(highs[-n:])
    current_close = prices[-1]
    
    if recent_high == recent_low:
        rsv = 50
    else:
        rsv = (current_close - recent_low) / (recent_high - recent_low) * 100
    
    # 简化计算，使用模拟值
    k = rsv
    d = k
    j = 3 * k - 2 * d
    
    return k, d, j


def calculate_bollinger(prices, period=20, std_dev=2):
    """计算布林带"""
    if len(prices) < period:
        middle = sum(prices) / len(prices) if prices else 0
        return middle, middle + 1, middle - 1
    
    middle = sum(prices[-period:]) / period
    variance = sum((p - middle) ** 2 for p in prices[-period:]) / period
    std = variance ** 0.5
    
    upper = middle + std_dev * std
    lower = middle - std_dev * std
    
    return upper, middle, lower


def calculate_macd(prices, fast=12, slow=26, signal=9):
    """计算MACD指标"""
    if len(prices) < slow:
        return 0, 0
    
    # 简化计算EMA
    def ema(data, period):
        multiplier = 2 / (period + 1)
        ema_values = [data[0]]
        for price in data[1:]:
            ema_values.append((price - ema_values[-1]) * multiplier + ema_values[-1])
        return ema_values[-1]
    
    ema_fast = ema(prices, fast)
    ema_slow = ema(prices, slow)
    
    macd_line = ema_fast - ema_slow
    signal_line = macd_line * 0.9  # 简化计算
    
    return macd_line, signal_line


def generate_analysis_text(indicator):
    """生成技术分析摘要"""
    texts = []
    
    # RSI分析
    if indicator['rsi'] < 30:
        texts.append("RSI处于超卖区域，可能存在反弹机会")
    elif indicator['rsi'] > 70:
        texts.append("RSI处于超买区域，注意回调风险")
    else:
        texts.append("RSI处于中性区域")
    
    # MACD分析
    if indicator['macd'] > 0 and indicator['macdSignal'] > 0:
        texts.append("MACD金叉形成，短期趋势向好")
    elif indicator['macd'] < 0 and indicator['macdSignal'] < 0:
        texts.append("MACD死叉形成，短期趋势走弱")
    else:
        texts.append("MACD趋势不明朗")
    
    # 布林带分析
    if indicator['bollingerPercent'] > 80:
        texts.append("价格接近布林带上轨，注意压力位")
    elif indicator['bollingerPercent'] < 20:
        texts.append("价格接近布林带下轨，关注支撑位")
    else:
        texts.append("价格在布林带中轨附近运行")
    
    # 成交量分析
    if indicator['volumeRatio'] > 2:
        texts.append("成交量明显放大，资金活跃度提升")
    elif indicator['volumeRatio'] < 0.5:
        texts.append("成交量萎缩，市场观望情绪浓厚")
    
    return "；".join(texts)


def load_real_history_series(symbol, limit=90):
    history = HistoricalMarketDataService.get_history(symbol, timeframe='daily', limit=max(int(limit or 90), 60))
    items = history.get('items') or []
    if len(items) < 20:
        raise ValueError(f"{HistoricalMarketDataService.normalize_symbol(symbol)} 历史行情不足，无法计算指标")

    prices = [float(item.get('close') or 0) for item in items if float(item.get('close') or 0) > 0]
    highs = [float(item.get('high') or item.get('close') or 0) for item in items if float(item.get('close') or 0) > 0]
    lows = [float(item.get('low') or item.get('close') or 0) for item in items if float(item.get('close') or 0) > 0]
    volumes = [float(item.get('volume') or 0) for item in items if float(item.get('close') or 0) > 0]

    if len(prices) < 20 or len(highs) != len(prices) or len(lows) != len(prices):
        raise ValueError(f"{HistoricalMarketDataService.normalize_symbol(symbol)} 历史行情不完整，无法计算指标")

    return prices, highs, lows, volumes, history


@scan_bp.route('/api/scan/indicators', methods=['POST'])
@login_required
def scan_indicators():
    """扫描持仓股票的技术指标"""
    try:
        data = request.json
        symbols = data.get('symbols', [])
        account_id = data.get('account_id')

        if not symbols:
            return jsonify({"success": False, "error": "股票代码列表不能为空"}), 400

        # 如果没有指定账户，获取默认账户
        if not account_id:
            db = DbUtil()
            row = db.fetch_one(
                """SELECT id, broker_type FROM broker_accounts
                   WHERE is_active = 1 AND is_default = 1
                   ORDER BY id ASC LIMIT 1"""
            )
            if not row:
                row = db.fetch_one(
                    """SELECT id, broker_type FROM broker_accounts
                       WHERE is_active = 1
                       ORDER BY id ASC LIMIT 1"""
                )
            if not row:
                return jsonify({"success": False, "error": "没有可用的交易账户"}), 400
            account_id = row.get('id')

        # 获取账户信息
        db = DbUtil()
        row = db.fetch_one(
            "SELECT broker_type FROM broker_accounts WHERE id = %s AND is_active = 1",
            (account_id,)
        )
        if not row:
            return jsonify({"success": False, "error": "账户不存在或未激活"}), 400

        broker_type = row.get('broker_type')

        # 初始化API
        if broker_type == 'longbridge':
            api = LongbridgeAPI(account_id)
        elif broker_type == 'tiger':
            api = TigerBrokerAPI(account_id)
        else:
            return jsonify({"success": False, "error": "不支持的券商类型"}), 400

        # 连接API
        if not api.connect():
            return jsonify({"success": False, "error": "无法连接到券商API"}), 500

        # 获取行情数据
        quotes = api.get_quote(symbols)

        results = []
        for symbol in symbols:
            quote = quotes.get(symbol)
            if not quote:
                continue

            # 获取价格数据
            current_price = quote.last_price if hasattr(quote, 'last_price') else 0
            prev_close = quote.prev_close if hasattr(quote, 'prev_close') else current_price
            volume = quote.volume if hasattr(quote, 'volume') else 0
            
            # 计算涨跌幅
            price_change = ((current_price - prev_close) / prev_close * 100) if prev_close > 0 else 0
            
            try:
                prices, highs, lows, volumes, history_payload = load_real_history_series(symbol)
            except Exception as history_error:
                results.append({
                    "symbol": symbol,
                    "price": current_price,
                    "priceChange": price_change,
                    "volume": volume,
                    "error": str(history_error),
                    "signal": "unavailable",
                    "signalText": "历史数据不足",
                    "analysisText": str(history_error),
                    "dataSource": "history-missing"
                })
                continue

            if current_price > 0:
                prices[-1] = current_price
            if highs:
                highs[-1] = max(highs[-1], current_price or highs[-1])
            if lows and current_price > 0:
                lows[-1] = min(lows[-1], current_price)
            
            # 计算各项指标
            rsi = calculate_rsi(prices)
            macd, macd_signal = calculate_macd(prices)
            k, d, j = calculate_kdj(prices, highs, lows)
            bollinger_upper, bollinger_middle, bollinger_lower = calculate_bollinger(prices)
            
            # 计算布林带位置百分比
            if bollinger_upper != bollinger_lower:
                bollinger_percent = (current_price - bollinger_lower) / (bollinger_upper - bollinger_lower) * 100
            else:
                bollinger_percent = 50
            
            # 计算MA
            ma5 = calculate_ma(prices, 5)
            ma10 = calculate_ma(prices, 10)
            ma20 = calculate_ma(prices, 20)
            ma60 = calculate_ma(prices, 60)
            
            # 计算趋势强度
            trend_strength = 0
            if current_price > ma5:
                trend_strength += 20
            if current_price > ma10:
                trend_strength += 20
            if current_price > ma20:
                trend_strength += 20
            if current_price > ma60:
                trend_strength += 20
            if macd > 0:
                trend_strength += 20
            
            # 计算量比（真实历史均量）
            baseline_volumes = [value for value in volumes[:-1] if value > 0] or [value for value in volumes if value > 0]
            avg_volume = (sum(baseline_volumes[-20:]) / len(baseline_volumes[-20:])) if baseline_volumes else 0
            volume_ratio = volume / avg_volume if avg_volume > 0 else 1
            
            # 判断布林带位置
            if bollinger_percent > 80:
                bollinger_pos = '上轨附近'
            elif bollinger_percent < 20:
                bollinger_pos = '下轨附近'
            else:
                bollinger_pos = '中轨附近'
            
            # 生成交易信号
            score = 50
            if rsi < 30 and macd > 0:
                signal = 'buy'
                signal_text = '买入信号'
                score = min(100, 70 + (30 - rsi) + trend_strength * 0.3)
            elif rsi > 70 and macd < 0:
                signal = 'sell'
                signal_text = '卖出信号'
                score = max(0, 30 - (rsi - 70) - trend_strength * 0.3)
            else:
                signal = 'hold'
                signal_text = '观望'
                score = 50 + (trend_strength - 50) * 0.3
            
            # 构建指标数据
            indicator = {
                "symbol": symbol,
                "price": current_price,
                "priceChange": price_change,
                "rsi": round(rsi, 2),
                "macd": round(macd, 4),
                "macdSignal": round(macd_signal, 4),
                "kdjK": round(k, 2),
                "kdjD": round(d, 2),
                "kdjJ": round(j, 2),
                "ma5": round(ma5, 2),
                "ma10": round(ma10, 2),
                "ma20": round(ma20, 2),
                "ma60": round(ma60, 2),
                "bollingerUpper": round(bollinger_upper, 2),
                "bollingerMiddle": round(bollinger_middle, 2),
                "bollingerLower": round(bollinger_lower, 2),
                "bollingerPercent": round(bollinger_percent, 2),
                "bollingerPos": bollinger_pos,
                "volume": volume,
                "volumeRatio": round(volume_ratio, 2),
                "trendStrength": round(trend_strength, 2),
                "signal": signal,
                "signalText": signal_text,
                "score": min(100, max(0, int(score))),
                "updateTime": "刚刚",
                "dataSource": "historical-market-data",
                "historySummary": history_payload.get("summary") or {}
            }
            
            # 生成分析文本
            indicator['analysisText'] = generate_analysis_text(indicator)
            
            results.append(indicator)

        return jsonify({
            "success": True,
            "data": results,
            "count": len(results),
            "successCount": len([item for item in results if not item.get("error")]),
            "failureCount": len([item for item in results if item.get("error")])
        })

    except Exception as e:
        print(f"扫描指标失败: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500
