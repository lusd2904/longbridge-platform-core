"""
AI分析相关路由
"""
from flask import Blueprint, request, jsonify
from utils.DbUtil import DbUtil
from core.broker.LongbridgeAPI import LongbridgeAPI
from core.broker.TigerBrokerAPI import TigerBrokerAPI
from api.auth_routes import login_required
from utils.IndicatorUtil import IndicatorUtil
from utils.IndicatorUtilEnhanced import IndicatorUtilEnhanced
from core.analysis.AiConsultant import AiConsultant
from core.analysis.DailySymbolTrendScanService import DailySymbolTrendScanService
from core.analysis.IndicatorSnapshotService import IndicatorSnapshotService
from core.analysis.RecommendationService import RecommendationService
from core.analysis.QuantTradingService import QuantTradingService
from core.analysis.ai_analyst import AIAnalyst
from core.analysis.HistoricalMarketDataService import HistoricalMarketDataService
from utils.MonitorLink import MonitorLink
from utils.logger import Logger
from utils.cache import cache, AICache, StockCache
from utils.rate_limiter import rate_limit
from core.account.DataPersistence import get_persistence_manager, AIAnalysisHistory
import traceback
import time
import os
from datetime import datetime
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor

ai_bp = Blueprint('ai', __name__)


def _env_int(name, default, minimum=1):
    raw = os.getenv(name, str(default))
    try:
        value = int(raw or default)
    except (TypeError, ValueError):
        value = default
    return max(minimum, value)


SYNC_BATCH_ANALYZE_LIMIT = _env_int("REF_ANALYSIS_SYNC_POSITIONS_LIMIT", 12)

BENCHMARKS = {
    'US': [
        {"symbol": "SPY.US", "name": "标普500", "role": "index", "sentiment_weight": 1.0},
        {"symbol": "QQQ.US", "name": "纳指100", "role": "index", "sentiment_weight": 1.1},
        {"symbol": "DIA.US", "name": "道琼斯", "role": "index", "sentiment_weight": 0.9},
        {"symbol": "IWM.US", "name": "罗素2000", "role": "index", "sentiment_weight": 1.0},
        {"symbol": "UVIX.US", "name": "UVIX波动率", "role": "volatility", "sentiment_weight": -1.1},
        {"symbol": "GLD.US", "name": "黄金", "role": "defensive", "sentiment_weight": -0.6},
        {"symbol": "USO.US", "name": "原油", "role": "commodity", "sentiment_weight": 0.35}
    ],
    'HK': [
        {"symbol": "2800.HK", "name": "恒生ETF", "role": "index", "sentiment_weight": 1.0},
        {"symbol": "2822.HK", "name": "中国企业ETF", "role": "index", "sentiment_weight": 1.0},
        {"symbol": "3033.HK", "name": "恒生科技ETF", "role": "index", "sentiment_weight": 1.1}
    ],
    'CN': [
        {"symbol": "510300.SH", "name": "沪深300ETF", "role": "index", "sentiment_weight": 1.0},
        {"symbol": "510050.SH", "name": "上证50ETF", "role": "index", "sentiment_weight": 0.9},
        {"symbol": "159915.SZ", "name": "创业板ETF", "role": "index", "sentiment_weight": 1.1}
    ]
}


class APICache:
    """兼容旧接口的 API 缓存包装。"""

    @staticmethod
    def cache_ai_analysis(symbol, model="combined"):
        return AICache.get_analysis(symbol, model)

    @staticmethod
    def set_ai_analysis(symbol, model, result, expire=1800):
        return AICache.cache_analysis(symbol, result, model, expire)

    @staticmethod
    def cache_indicators(symbol):
        return StockCache.get_indicators(symbol)

    @staticmethod
    def set_indicators(symbol, indicators, expire=300):
        return StockCache.cache_indicators(symbol, indicators, expire)

    @staticmethod
    def set_stock_quote(symbol, data, expire=60):
        return cache.set(f"stock:quote:{symbol}", data, expire)


def _detect_market(symbol):
    upper_symbol = (symbol or '').upper()
    if upper_symbol.endswith('.HK'):
        return 'HK'
    if upper_symbol.endswith('.SH') or upper_symbol.endswith('.SZ'):
        return 'CN'
    return 'US'


def _format_symbol(symbol):
    market = _detect_market(symbol)
    normalized = (symbol or '').upper()
    if '.' in normalized:
        return normalized
    return f"{normalized}.{market}"


def _resolve_quote_accounts(account_id=None, user_id=None):
    db = DbUtil()

    if account_id:
        if user_id is not None:
            row = db.fetch_one(
                """SELECT id, broker_type
                   FROM broker_accounts
                   WHERE id = %s AND user_id = %s AND is_active = 1
                   LIMIT 1""",
                (account_id, user_id)
            )
        else:
            row = db.fetch_one(
                """SELECT id, broker_type
                   FROM broker_accounts
                   WHERE id = %s AND is_active = 1
                   LIMIT 1""",
                (account_id,)
            )
        if row:
            return [row]

    if user_id is not None:
        rows = db.query_all(
            """SELECT id, broker_type
               FROM broker_accounts
               WHERE user_id = %s AND is_active = 1
               ORDER BY is_default DESC, id ASC""",
            (user_id,)
        )
        if rows:
            return [{"id": row[0], "broker_type": row[1]} for row in rows]

    rows = db.query_all(
        """SELECT id, broker_type
           FROM broker_accounts
           WHERE is_active = 1
           ORDER BY is_default DESC, id ASC"""
    )
    return [{"id": row[0], "broker_type": row[1]} for row in (rows or [])]


def _normalize_quote_dict(symbol, quote):
    last_price = float(quote.get('last_price', 0) or 0)
    prev_close = float(quote.get('prev_close', 0) or 0)
    change_percent = quote.get('change_percent')
    if change_percent is None:
        change_percent = ((last_price - prev_close) / prev_close * 100) if prev_close else 0

    return {
        "symbol": symbol,
        "last_price": last_price,
        "prev_close": prev_close,
        "volume": int(quote.get('volume', 0) or 0),
        "change_percent": float(change_percent or 0)
    }


def _get_quotes_from_broker(symbols, account_id=None, user_id=None):
    """优先使用指定账户所属券商获取行情，失败时自动回退到其他激活账户。"""
    formatted_symbols = [_format_symbol(symbol) for symbol in symbols if symbol]
    if not formatted_symbols:
        return {}

    for account in _resolve_quote_accounts(account_id, user_id=user_id):
        broker_type = (account.get('broker_type') or '').lower()
        broker_account_id = account.get('id')
        broker_api = None

        try:
            if broker_type == 'longbridge':
                broker_api = LongbridgeAPI(account_id=broker_account_id)
            elif broker_type == 'tiger':
                broker_api = TigerBrokerAPI(account_id=broker_account_id)
            else:
                continue

            if not broker_api.connect():
                continue

            raw_quotes = broker_api.get_quote(formatted_symbols) or {}
            normalized_quotes = {}

            for symbol in formatted_symbols:
                quote = raw_quotes.get(symbol)
                if not quote:
                    continue

                if hasattr(quote, 'last_price'):
                    normalized_quotes[symbol] = {
                        "symbol": symbol,
                        "last_price": float(getattr(quote, 'last_price', 0) or 0),
                        "prev_close": float(getattr(quote, 'prev_close', 0) or 0),
                        "volume": int(getattr(quote, 'volume', 0) or 0),
                        "change_percent": float(getattr(quote, 'change_percent', 0) or 0)
                    }
                else:
                    normalized_quotes[symbol] = _normalize_quote_dict(symbol, quote)

            if normalized_quotes:
                return normalized_quotes
        except Exception as exc:
            Logger.log_error("ai_quote", exc, f"获取行情失败: {formatted_symbols}")
        finally:
            if broker_api:
                try:
                    broker_api.disconnect()
                except Exception:
                    pass

    return {}


def _get_quote_from_broker(symbol, account_id=None, user_id=None):
    quote = _get_quotes_from_broker([symbol], account_id, user_id=user_id).get(_format_symbol(symbol))
    if not quote:
        MonitorLink.log(f"❌ 所有API都无法获取行情: {_format_symbol(symbol)}")
        return 0, 0, 0.0, 0.0

    MonitorLink.log(
        f"✅ 获取实时行情: {quote['symbol']} = {quote['last_price']} ({quote['change_percent']:+.2f}%)"
    )
    return (
        quote['last_price'],
        quote['volume'],
        quote['change_percent'],
        quote['prev_close']
    )


def _build_market_snapshot(account_id=None, focus_symbol=None, user_id=None):
    market = _detect_market(focus_symbol or 'US')
    benchmark_config = BENCHMARKS.get(market) or BENCHMARKS['US']

    quotes = _get_quotes_from_broker([item['symbol'] for item in benchmark_config], account_id, user_id=user_id)
    if not quotes and market != 'US':
        market = 'US'
        benchmark_config = BENCHMARKS['US']
        quotes = _get_quotes_from_broker([item['symbol'] for item in benchmark_config], account_id, user_id=user_id)

    benchmarks = []
    sentiment_changes = []
    benchmark_map = {}

    for item in benchmark_config:
        symbol = item['symbol']
        quote = quotes.get(symbol)
        if not quote:
            continue

        change_percent = float(quote.get('change_percent', 0) or 0)
        sentiment_change = change_percent * float(item.get('sentiment_weight', 1.0) or 1.0)
        sentiment_changes.append(sentiment_change)

        benchmark_data = {
            "symbol": symbol,
            "name": item.get('name', symbol),
            "role": item.get('role', 'index'),
            "price": float(quote.get('last_price', 0) or 0),
            "changePercent": change_percent,
            "sentimentAdjustedChange": sentiment_change,
            "tone": "up" if sentiment_change > 0 else "down" if sentiment_change < 0 else "flat"
        }
        benchmarks.append(benchmark_data)
        benchmark_map[symbol] = benchmark_data

    if not benchmarks:
        return {
            "market": market,
            "regime": "balanced",
            "risk_temperature": "中性",
            "summary": "未获取到实时大盘快照",
            "benchmarks": [],
            "updated_at": time.time()
        }

    positive = len([item for item in sentiment_changes if item > 0])
    negative = len([item for item in sentiment_changes if item < 0])
    average_change = sum(sentiment_changes) / len(sentiment_changes)
    majority_threshold = max(2, (len(sentiment_changes) // 2) + 1)

    macro_drivers = []
    uvix = benchmark_map.get('UVIX.US')
    gold = benchmark_map.get('GLD.US')
    oil = benchmark_map.get('USO.US')

    if uvix:
        if uvix['changePercent'] >= 3:
            macro_drivers.append("UVIX急升，短线波动显著放大")
        elif uvix['changePercent'] <= -3:
            macro_drivers.append("UVIX回落，市场恐慌有所缓解")

    if gold:
        if gold['changePercent'] >= 1:
            macro_drivers.append("黄金走强，避险需求升温")
        elif gold['changePercent'] <= -1:
            macro_drivers.append("黄金回落，避险买盘减弱")

    if oil:
        if oil['changePercent'] >= 1:
            macro_drivers.append("原油上行，通胀与能源链条需留意")
        elif oil['changePercent'] <= -1:
            macro_drivers.append("原油回落，周期板块情绪偏温和")

    if average_change >= 0.45 and positive >= majority_threshold:
        regime = "risk_on"
        risk_temperature = "偏强"
        summary = "指数共振偏强，市场风险偏好回升"
    elif average_change <= -0.45 and negative >= majority_threshold:
        regime = "risk_off"
        risk_temperature = "偏弱"
        summary = "指数整体承压，市场进入防守模式"
    else:
        regime = "balanced"
        risk_temperature = "震荡"
        summary = "指数分化，市场处于震荡筛选阶段"

    if macro_drivers:
        summary = f"{summary}；{'；'.join(macro_drivers[:2])}"

    return {
        "market": market,
        "regime": regime,
        "risk_temperature": risk_temperature,
        "summary": summary,
        "benchmarks": benchmarks,
        "updated_at": time.time()
    }


def _normalize_position_batch_payload(raw_positions, sync_limit=SYNC_BATCH_ANALYZE_LIMIT):
    positions = raw_positions if isinstance(raw_positions, list) else []
    safe_limit = max(1, int(sync_limit or 1))
    total = len(positions)
    accepted = positions[:safe_limit]
    dropped = max(total - len(accepted), 0)
    return accepted, {
        "requested": total,
        "accepted": len(accepted),
        "deferred": dropped,
        "syncLimit": safe_limit,
        "partial": dropped > 0,
    }


def _build_deferred_batch_placeholders(raw_positions, sync_limit=SYNC_BATCH_ANALYZE_LIMIT):
    positions = raw_positions if isinstance(raw_positions, list) else []
    placeholders = []
    for item in positions:
        if not isinstance(item, dict):
            continue
        raw_symbol = str(item.get("symbol") or "").strip()
        if not raw_symbol:
            continue
        symbol = HistoricalMarketDataService.normalize_symbol(raw_symbol)
        placeholders.append(
            {
                "symbol": symbol,
                "name": item.get("name") or item.get("symbol_name") or symbol,
                "queued": True,
                "deferred": True,
                "reason": f"批量分析超过同步上限 {sync_limit}，已快速接受并延后处理",
                "finalSignal": "warning",
                "finalDecision": "排队中",
                "scanLayers": [],
                "source": "manual_scan",
                "analysisMode": "manual_deferred_scan",
            }
        )
    return placeholders


def _build_real_indicator_context(symbol, current_price, volume, user_id=1):
    normalized_symbol = HistoricalMarketDataService.normalize_symbol(symbol)
    overview = IndicatorSnapshotService.get_symbol_overview(normalized_symbol, user_id=user_id)
    daily_snapshot = (overview.get('snapshots') or {}).get('daily') or {}

    if not daily_snapshot:
        raise ValueError(f"{normalized_symbol} 暂无可用技术快照")

    effective_price = float(current_price or daily_snapshot.get('closePrice') or 0)
    indicator_payload = {
        "rsi": float(daily_snapshot.get('rsi') or 0),
        "macd": float(daily_snapshot.get('macdDiff') or 0),
        "kdj": float(daily_snapshot.get('jValue') or 0),
        "boll": {
            "upper": float(daily_snapshot.get('bollUpper') or 0),
            "mid": float(daily_snapshot.get('bollMid') or 0),
            "lower": float(daily_snapshot.get('bollLower') or 0)
        },
        "ema": {
            "short": float(daily_snapshot.get('emaShort') or 0),
            "long": float(daily_snapshot.get('emaLong') or 0)
        },
        "atr": float(daily_snapshot.get('atr') or 0),
        "roc": float(daily_snapshot.get('roc') or 0),
        "cci": float(daily_snapshot.get('cci') or 0),
        "obv": float(daily_snapshot.get('obv') or 0),
        "support": float(daily_snapshot.get('supportPrice') or 0),
        "resistance": float(daily_snapshot.get('resistancePrice') or 0),
        "trendLabel": daily_snapshot.get('trendLabel') or '',
        "momentumScore": float(daily_snapshot.get('momentumScore') or 0),
        "snapshotDate": daily_snapshot.get('tradeDate'),
        "fundamentals": overview.get('fundamentals') or {}
    }

    ai_payload = {
        "price": effective_price,
        "rsi": indicator_payload["rsi"],
        "macd": indicator_payload["macd"],
        "kdj": indicator_payload["kdj"],
        "boll_upper": indicator_payload["boll"]["upper"],
        "boll_mid": indicator_payload["boll"]["mid"],
        "boll_lower": indicator_payload["boll"]["lower"],
        "ema_short": indicator_payload["ema"]["short"],
        "ema_long": indicator_payload["ema"]["long"],
        "atr": indicator_payload["atr"],
        "roc": indicator_payload["roc"],
        "cci": indicator_payload["cci"],
        "obv": indicator_payload["obv"],
        "support": indicator_payload["support"],
        "resistance": indicator_payload["resistance"],
        "snapshot_date": indicator_payload["snapshotDate"],
        "trend_label": indicator_payload["trendLabel"],
        "momentum_score": indicator_payload["momentumScore"],
        "volume": int(volume or 0)
    }
    return ai_payload, indicator_payload


def _extract_position_quote_fallback(position):
    def coerce_float(*values, default=0.0):
        for value in values:
            if value in (None, ""):
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return default

    current_price = coerce_float(
        position.get('current_price'),
        position.get('currentPrice'),
        position.get('market_price'),
        position.get('marketPrice'),
        position.get('latest_price'),
        position.get('latestPrice'),
        position.get('last_price'),
        position.get('lastPrice'),
        position.get('price'),
    )
    quantity = coerce_float(
        position.get('quantity'),
        position.get('qty'),
        position.get('availableQuantity'),
        position.get('available_quantity'),
    )
    market_value = coerce_float(
        position.get('market_value'),
        position.get('marketValue'),
        position.get('market_val'),
        position.get('marketVal'),
    )
    if current_price <= 0 and quantity > 0 and market_value > 0:
        current_price = market_value / quantity

    volume = int(coerce_float(position.get('volume'), position.get('turnoverVolume')))
    change_percent = coerce_float(position.get('change_percent'), position.get('changePercent'))
    prev_close = coerce_float(position.get('prev_close'), position.get('prevClose'))

    if prev_close <= 0 and current_price > 0 and change_percent:
        denominator = 1 + (change_percent / 100)
        if denominator:
            prev_close = current_price / denominator

    if prev_close <= 0:
        prev_close = current_price

    return current_price, volume, change_percent, prev_close


def _build_trend_scan_analysis_result(scan):
    trend_direction = str(scan.get("trendDirection") or "sideways").strip().lower()
    signal_map = {
        "up": "success",
        "down": "danger",
        "sideways": "warning"
    }
    decision_map = {
        "up": "偏多",
        "down": "偏空",
        "sideways": "观望"
    }
    risk_label_map = {
        "low": "低风险",
        "medium": "中风险",
        "high": "高风险"
    }

    raw_indicators = scan.get("indicators") or {}
    latest_price = float(
        raw_indicators.get("latestClose")
        or raw_indicators.get("closePrice")
        or raw_indicators.get("close")
        or 0
    )
    change_percent = float(
        raw_indicators.get("dayChangePercent")
        or raw_indicators.get("changePercent")
        or 0
    )
    prev_close = latest_price
    denominator = 1 + (change_percent / 100)
    if latest_price > 0 and denominator:
        prev_close = latest_price / denominator

    indicators = {
        **raw_indicators,
        "closePrice": latest_price,
        "close": latest_price,
        "changePercent": change_percent,
        "rsi": float(raw_indicators.get("rsi") or raw_indicators.get("rsi14") or 0),
        "trendLabel": raw_indicators.get("trendLabel") or raw_indicators.get("trendHint") or "",
        "snapshotDate": raw_indicators.get("snapshotDate") or scan.get("dataTradeDate"),
        "momentumScore": float(raw_indicators.get("momentumScore") or scan.get("technicalScore") or 0)
    }

    final_signal = signal_map.get(trend_direction, "warning")
    final_decision = decision_map.get(trend_direction, "观望")
    risk_level = str(scan.get("riskLevel") or "medium").strip().lower()
    data_trade_date = scan.get("dataTradeDate")
    headline = scan.get("headline") or ""
    summary = scan.get("summary") or ""
    provider_route = (scan.get("meta") or {}).get("providerRoute")

    highlights = [
        f"方向 {final_decision}",
        risk_label_map.get(risk_level, "中风险"),
        f"技术分 {float(scan.get('technicalScore') or 0):.1f}"
    ]
    if data_trade_date:
        highlights.append(f"数据截至 {data_trade_date}")

    return {
        "symbol": scan.get("symbol"),
        "market": scan.get("market"),
        "price": latest_price,
        "prevClose": round(prev_close, 4) if prev_close else latest_price,
        "changePercent": change_percent,
        "volume": int(indicators.get("volume") or 0),
        "confidence": max(0, min(float(scan.get("trendStrength") or 0), 100)),
        "technicalScore": float(scan.get("technicalScore") or 0),
        "marketScore": 0,
        "finalSignal": final_signal,
        "finalDecision": final_decision,
        "reason": headline or summary or "已加载历史趋势扫描结果",
        "analysisTime": scan.get("generatedAt") or scan.get("analysisDate"),
        "indicators": indicators,
        "modelPlan": {
            "trendBatch": {
                "id": scan.get("modelId"),
                "alias": scan.get("modelAlias"),
                "latency": "batch",
                "quality": "最高质量",
                "reasoningEffort": "high",
                "providerRoute": provider_route
            }
        },
        "scanLayers": [
            {
                "id": "trend",
                "name": "历史趋势扫描",
                "summary": summary or headline,
                "fullText": scan.get("analysisText") or summary or headline,
                "signal": final_signal,
                "decision": final_decision,
                "modelId": scan.get("modelId"),
                "modelAlias": scan.get("modelAlias"),
                "modelLatency": "batch",
                "modelQuality": "最高质量",
                "reasoningEffort": "high",
                "highlights": highlights
            }
        ],
        "trendDirection": trend_direction,
        "trendStrength": float(scan.get("trendStrength") or 0),
        "riskLevel": risk_level,
        "source": "trend_scan",
        "analysisMode": "scheduled_trend"
    }


@ai_bp.route('/api/ai/models', methods=['GET'])
@login_required
def get_ai_models():
    try:
        user_id = getattr(request, 'user_id', 1)
        return jsonify({
            "success": True,
            "data": AIAnalyst.get_model_catalog(user_id=user_id),
            "defaultPlan": AIAnalyst.get_task_model_plan(user_id=user_id),
            "providerPlan": AIAnalyst.get_task_provider_plan(user_id=user_id),
            "provider": AIAnalyst._provider(user_id=user_id)
        })
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@ai_bp.route('/api/ai/test-connection', methods=['POST'])
@login_required
def test_ai_connection():
    try:
        payload = request.get_json(silent=True) or {}
        configs = payload.get('configs') or {}
        result = AIAnalyst.probe_connection(config_map=configs, user_id=getattr(request, 'user_id', 1))
        status_code = 200 if result.get('success') else 400
        return jsonify({
            "success": bool(result.get('success')),
            "data": result
        }), status_code
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@ai_bp.route('/api/ai/trend-scans', methods=['GET'])
@login_required
def get_latest_trend_scans():
    try:
        raw_symbols = request.args.getlist('symbols')
        if len(raw_symbols) == 1 and ',' in str(raw_symbols[0]):
            raw_symbols = [item.strip() for item in str(raw_symbols[0]).split(',') if item.strip()]
        if not raw_symbols:
            merged = str(request.args.get('symbols', '') or request.args.get('symbol', '')).strip()
            raw_symbols = [item.strip() for item in merged.split(',') if item.strip()]

        market = str(request.args.get('market', '') or '').strip().upper()
        limit = max(1, min(int(request.args.get('limit', 24) or 24), 80))
        items = DailySymbolTrendScanService.get_latest_batch(
            symbols=raw_symbols or None,
            market=market or None,
            limit=limit
        )
        return jsonify({
            "success": True,
            "data": [_build_trend_scan_analysis_result(item) for item in items]
        })
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@ai_bp.route('/api/recommendations', methods=['GET'])
@login_required
def get_recommendations():
    try:
        profile = request.args.get('profile', 'growth')
        refresh = str(request.args.get('refresh', '')).lower() in {'1', 'true', 'yes'}
        user_id = getattr(request, 'user_id', 1)

        if refresh:
            result = RecommendationService.refresh(profile=profile, user_id=user_id, force=True)
        else:
            result = RecommendationService.get_latest(profile=profile, user_id=user_id)
            if not result:
                result = RecommendationService.refresh(profile=profile, user_id=user_id, force=True)

        return jsonify({
            "success": True,
            "data": result
        })
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@ai_bp.route('/api/recommendations/refresh', methods=['POST'])
@login_required
@rate_limit(key_func=lambda: f"recommend-refresh:{getattr(request, 'user_id', 'anonymous')}", limit=6, window=60)
def refresh_recommendations():
    try:
        payload = request.get_json(silent=True) or {}
        profile = payload.get('profile', request.args.get('profile', 'growth'))
        user_id = getattr(request, 'user_id', 1)
        result = RecommendationService.refresh(profile=profile, user_id=user_id, force=True)
        return jsonify({
            "success": True,
            "message": "智能推荐已刷新",
            "data": result
        })
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@ai_bp.route('/api/quant/status', methods=['GET'])
@login_required
def get_quant_status():
    try:
        result = QuantTradingService.get_status(user_id=getattr(request, 'user_id', 1))
        return jsonify({
            "success": True,
            "data": result
        })
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@ai_bp.route('/api/quant/run', methods=['POST'])
@login_required
@rate_limit(key_func=lambda: f"quant-run:{getattr(request, 'user_id', 'anonymous')}", limit=3, window=300)
def run_quant_cycle():
    try:
        payload = request.get_json(silent=True) or {}
        account_id = payload.get('account_id')
        execute = payload.get('execute')
        execute_flag = None if execute is None else str(execute).strip().lower() in {'1', 'true', 'yes', 'on'}
        result = QuantTradingService.run_watchlist_strategy_cycle(
            user_id=getattr(request, 'user_id', 1),
            account_id=int(account_id) if account_id else None,
            source='manual',
            execute=execute_flag
        )
        return jsonify({
            "success": True,
            "message": "自选池量化策略扫描已完成",
            "data": result
        })
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@ai_bp.route('/api/ai/analyze_positions', methods=['POST'])
@login_required
@rate_limit(key_func=lambda: f"ai-analyze:{getattr(request, 'user_id', 'anonymous')}", limit=6, window=60)
def analyze_positions():
    """AI分析持仓情况 - 对每只股票进行真实AI分析"""
    start_time = time.time()
    logger = Logger.get_logger('api')
    
    try:
        data = request.get_json(silent=True) or {}
        positions = data.get('positions', [])
        account_id = data.get('account_id')
        user_id = getattr(request, 'user_id', 1)
        model_plan = AIAnalyst.get_task_model_plan(user_id=user_id)

        if not positions:
            return jsonify({"success": False, "error": "持仓数据不能为空"}), 400

        MonitorLink.log(f"🧠 [AI分析持仓] 开始分析 {len(positions)} 只股票")
        logger.info(f"开始分析 {len(positions)} 只股票")
        
        # 如果没有指定账户，获取默认账户
        if not account_id:
            db = DbUtil()
            row = db.fetch_one(
                """SELECT id, broker_type FROM broker_accounts
                   WHERE user_id = %s AND is_active = 1 AND is_default = 1
                   ORDER BY id ASC LIMIT 1""",
                (user_id,)
            )
            if not row:
                row = db.fetch_one(
                    """SELECT id, broker_type FROM broker_accounts
                       WHERE user_id = %s AND is_active = 1
                       ORDER BY id ASC LIMIT 1""",
                    (user_id,)
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
        
        results = []
        market_snapshot_cache = {}
        response_market_summary = None
        for position in positions:
            symbol = position.get('symbol')
            if not symbol:
                continue
            
            current_price = 0
            volume = 0
            change_percent = 0
            prev_close = 0
            indicator_payload = {}
            market_snapshot = response_market_summary or {}
            indicator_meta = {"source": "", "warning": ""}

            try:
                MonitorLink.log(f"📈 分析股票: {symbol}")
                
                # 检查缓存
                cached_result = APICache.cache_ai_analysis(symbol, "combined")
                if cached_result and cached_result.get('scanLayers'):
                    current_price, volume, change_percent, prev_close = _get_quote_from_broker(symbol, account_id, user_id=user_id)
                    market_key = _detect_market(symbol)
                    market_snapshot = market_snapshot_cache.get(market_key)
                    if not market_snapshot:
                        market_snapshot = _build_market_snapshot(account_id, symbol, user_id=user_id)
                        market_snapshot_cache[market_key] = market_snapshot

                    refreshed_cached_result = dict(cached_result)
                    if current_price > 0:
                        refreshed_cached_result.update({
                            "price": current_price,
                            "volume": volume,
                            "changePercent": change_percent,
                            "prevClose": prev_close,
                            "analysisTime": time.time(),
                            "timestamp": time.time()
                        })
                    refreshed_cached_result["marketSummary"] = market_snapshot
                    refreshed_cached_result["modelPlan"] = model_plan

                    MonitorLink.log(f"🔥 使用缓存结果: {symbol}")
                    results.append(refreshed_cached_result)
                    response_market_summary = market_snapshot or response_market_summary
                    continue
                
                # 1. 获取实时行情
                current_price, volume, change_percent, prev_close = _get_quote_from_broker(symbol, account_id, user_id=user_id)
                if current_price <= 0:
                    fallback_price, fallback_volume, fallback_change, fallback_prev_close = _extract_position_quote_fallback(position)
                    if fallback_price > 0:
                        current_price = fallback_price
                        volume = volume or fallback_volume
                        change_percent = change_percent or fallback_change
                        prev_close = prev_close or fallback_prev_close
                        MonitorLink.log(f"⚠️ 实时行情不可用，回退到请求内行情: {symbol} = {current_price}")
                if current_price <= 0:
                    # 没有获取到行情数据，返回错误信息
                    MonitorLink.log(f"❌ 无行情数据: {symbol}")
                    # 构建错误结果
                    error_result = {
                        "symbol": symbol,
                        "name": position.get('name') or position.get('symbol_name') or symbol,
                        "error": "无行情数据",
                        "reason": "当前未能从券商获取到实时行情，请稍后重试或检查代码格式。",
                        "modelPlan": model_plan,
                        "scanLayers": [],
                        "finalSignal": "danger",
                        "finalDecision": "无行情"
                    }
                    results.append(error_result)
                    continue
                
                # 将获取到的行情保存到数据库
                try:
                    db = DbUtil()
                    db.execute(
                        """INSERT INTO stock_quote (symbol, price, volume, updated_at) 
                           VALUES (%s, %s, %s, NOW())
                           ON DUPLICATE KEY UPDATE
                           price = VALUES(price),
                           volume = VALUES(volume),
                           updated_at = NOW()""",
                        (symbol, current_price, volume)
                    )
                    MonitorLink.log(f"💾 行情数据已保存到数据库: {symbol}")
                except Exception as db_error:
                    Logger.log_error("ai_analyze", db_error, f"保存行情数据失败: {symbol}")
                
                # 2. 基于真实历史行情生成技术快照
                real_ai_payload, indicator_payload = _build_real_indicator_context(
                    symbol, current_price, volume, user_id=user_id
                )
                indicator_meta = {"source": "snapshot", "warning": ""}

                # 3. 构建AI分析数据
                market_key = _detect_market(symbol)
                market_snapshot = market_snapshot_cache.get(market_key)
                if not market_snapshot:
                    market_snapshot = _build_market_snapshot(account_id, symbol, user_id=user_id)
                    market_snapshot_cache[market_key] = market_snapshot

                response_market_summary = market_snapshot

                ai_data = {
                    **real_ai_payload,
                    'price': float(current_price or real_ai_payload.get('price') or 0),
                    'market_context': market_snapshot,
                    'account_id': account_id,
                    'user_id': user_id,
                    'indicator_source': indicator_meta.get('source')
                }
                
                # 4. 调用AI分析
                rsi = float(real_ai_payload.get('rsi') or 0)
                algo_side = 'BUY' if rsi < 30 else 'SELL' if rsi > 70 else 'HOLD'
                verdict, reason, gemma_analysis, llama_analysis, deepseek_analysis = AiConsultant.get_final_decision_with_details(
                    symbol, algo_side, ai_data
                )
                
                # 5. 构建分析结果
                signal_map = {
                    'BUY': 'success',
                    'SELL': 'danger',
                    'HOLD': 'warning'
                }
                decision_map = {
                    'BUY': '买入',
                    'SELL': '卖出',
                    'HOLD': '观望'
                }
                final_signal = signal_map.get(verdict, 'warning')
                final_decision = decision_map.get(verdict, '观望')

                scan_layers = [
                    {
                        "id": "pulse",
                        "name": gemma_analysis.get('role', '市场脉冲层'),
                        "summary": gemma_analysis.get('summary', ''),
                        "fullText": gemma_analysis.get('full_text', ''),
                        "signal": signal_map.get(gemma_analysis.get('signal', verdict), final_signal),
                        "decision": decision_map.get(gemma_analysis.get('signal', verdict), final_decision),
                        "modelId": model_plan.get('pulse', {}).get('id'),
                        "modelAlias": model_plan.get('pulse', {}).get('alias'),
                        "modelLatency": model_plan.get('pulse', {}).get('latency'),
                        "modelQuality": model_plan.get('pulse', {}).get('quality'),
                        "reasoningEffort": model_plan.get('pulse', {}).get('reasoningEffort'),
                        "highlights": [
                            gemma_analysis.get('trend', ''),
                            gemma_analysis.get('market_link', ''),
                            gemma_analysis.get('window', '')
                        ]
                    },
                    {
                        "id": "risk",
                        "name": llama_analysis.get('role', '风险筛查层'),
                        "summary": llama_analysis.get('summary', ''),
                        "fullText": llama_analysis.get('full_text', ''),
                        "signal": signal_map.get(llama_analysis.get('signal', verdict), final_signal),
                        "decision": decision_map.get(llama_analysis.get('signal', verdict), final_decision),
                        "modelId": model_plan.get('risk', {}).get('id'),
                        "modelAlias": model_plan.get('risk', {}).get('alias'),
                        "modelLatency": model_plan.get('risk', {}).get('latency'),
                        "modelQuality": model_plan.get('risk', {}).get('quality'),
                        "reasoningEffort": model_plan.get('risk', {}).get('reasoningEffort'),
                        "highlights": [
                            llama_analysis.get('sentiment', ''),
                            llama_analysis.get('risk', ''),
                            llama_analysis.get('position_advice', '')
                        ]
                    },
                    {
                        "id": "final",
                        "name": deepseek_analysis.get('role', '决策终审层'),
                        "summary": deepseek_analysis.get('summary', ''),
                        "fullText": deepseek_analysis.get('full_text', ''),
                        "signal": final_signal,
                        "decision": final_decision,
                        "modelId": model_plan.get('final', {}).get('id'),
                        "modelAlias": model_plan.get('final', {}).get('alias'),
                        "modelLatency": model_plan.get('final', {}).get('latency'),
                        "modelQuality": model_plan.get('final', {}).get('quality'),
                        "reasoningEffort": model_plan.get('final', {}).get('reasoningEffort'),
                        "highlights": [
                            deepseek_analysis.get('strategy', ''),
                            deepseek_analysis.get('market_scan', ''),
                            f"置信度 {deepseek_analysis.get('confidence', 0)}%"
                        ]
                    }
                ]

                analysis_result = {
                    "symbol": symbol,
                    "name": position.get('name') or position.get('symbol_name') or symbol,
                    "price": current_price,
                    "prevClose": prev_close,
                    "changePercent": change_percent,
                    "volume": volume,
                    "indicators": indicator_payload,
                    "marketSummary": market_snapshot,
                    "modelPlan": model_plan,
                    "scanLayers": scan_layers,
                    "gemma": gemma_analysis.get('summary', ''),
                    "gemmaFullText": gemma_analysis.get('full_text', ''),
                    "gemmaTrend": gemma_analysis.get('trend', ''),
                    "gemmaIndicators": gemma_analysis.get('indicators', ''),
                    "gemmaLevels": gemma_analysis.get('levels', ''),
                    "gemmaSignal": signal_map.get(gemma_analysis.get('signal', verdict), final_signal),
                    "gemmaDecision": decision_map.get(gemma_analysis.get('signal', verdict), final_decision),
                    "llama": llama_analysis.get('summary', ''),
                    "llamaFullText": llama_analysis.get('full_text', ''),
                    "llamaSentiment": llama_analysis.get('sentiment', ''),
                    "llamaFlow": llama_analysis.get('flow', ''),
                    "llamaRisk": llama_analysis.get('risk', ''),
                    "llamaMarket": llama_analysis.get('market_env', ''),
                    "llamaSignal": signal_map.get(llama_analysis.get('signal', verdict), final_signal),
                    "llamaDecision": decision_map.get(llama_analysis.get('signal', verdict), final_decision),
                    "deepseek": deepseek_analysis.get('summary', ''),
                    "deepseekFullText": deepseek_analysis.get('full_text', ''),
                    "deepseekTrend": deepseek_analysis.get('trend', ''),
                    "deepseekIndicators": deepseek_analysis.get('indicators', ''),
                    "deepseekMarketScan": deepseek_analysis.get('market_scan', ''),
                    "deepseekStrategy": deepseek_analysis.get('strategy', ''),
                    "deepseekTarget": deepseek_analysis.get('target', ''),
                    "deepseekStopLoss": deepseek_analysis.get('stop_loss', ''),
                    "deepseekFundamental": deepseek_analysis.get('fundamental_score', 0),
                    "deepseekTechnical": deepseek_analysis.get('technical_score', 0),
                    "deepseekCapital": deepseek_analysis.get('capital_score', 0),
                    "deepseekMarketScore": deepseek_analysis.get('market_score', 0),
                    "deepseekConfidence": deepseek_analysis.get('confidence', 0),
                    "deepseekSignal": final_signal,
                    "deepseekDecision": final_decision,
                    "finalSignal": final_signal,
                    "finalDecision": final_decision,
                    "reason": f"{reason}；{indicator_meta['warning']}" if indicator_meta.get('warning') else reason,
                    "indicatorSource": indicator_meta.get('source') or 'snapshot',
                    "analysisTime": time.time(),
                    "timestamp": time.time()
                }
                
                # 保存AI分析历史到数据库
                try:
                    persistence = get_persistence_manager()
                    ai_history = AIAnalysisHistory(
                        user_id=user_id,
                        symbol=symbol,
                        market=_detect_market(symbol),
                        price=current_price,
                        gemma_decision=analysis_result.get('gemmaDecision', gemma_analysis.get('signal', '')),
                        gemma_confidence=80.0,  # 假设的置信度
                        gemma_analysis=gemma_analysis.get('full_text', ''),
                        llama_decision=analysis_result.get('llamaDecision', llama_analysis.get('signal', '')),
                        llama_confidence=80.0,  # 假设的置信度
                        llama_analysis=llama_analysis.get('full_text', ''),
                        deepseek_decision=analysis_result.get('deepseekDecision', deepseek_analysis.get('signal', '')),
                        deepseek_confidence=deepseek_analysis.get('confidence', 75.0),
                        deepseek_analysis=deepseek_analysis.get('full_text', ''),
                        final_decision=analysis_result['finalDecision'],
                        final_confidence=deepseek_analysis.get('confidence', 75.0),
                        indicators=analysis_result['indicators'],
                        analysis_time=datetime.now()
                    )
                    persistence.save_ai_analysis(ai_history)
                    MonitorLink.log(f"💾 分析历史已保存: {symbol}")
                except Exception as db_error:
                    Logger.log_error("ai_analyze", db_error, f"保存分析历史失败: {symbol}")
                
                # 缓存结果
                APICache.set_ai_analysis(symbol, "combined", analysis_result, 1800)  # 30分钟缓存
                
                results.append(analysis_result)
                MonitorLink.log(f"✅ 分析完成: {symbol} -> {analysis_result['finalDecision']}")
                
            except Exception as e:
                MonitorLink.log(f"❌ 分析失败: {symbol} - {e}")
                Logger.log_error("ai_analyze", e, f"分析股票失败: {symbol}")
                error_result = {
                    "symbol": symbol,
                    "name": position.get('name') or position.get('symbol_name') or symbol,
                    "price": current_price,
                    "prevClose": prev_close,
                    "changePercent": change_percent,
                    "volume": volume,
                    "indicators": indicator_payload or {},
                    "marketSummary": market_snapshot,
                    "modelPlan": model_plan,
                    "scanLayers": [],
                    "error": str(e),
                    "reason": str(e),
                    "indicatorSource": indicator_meta.get('source') or '',
                    "finalSignal": "danger",
                    "finalDecision": "分析失败"
                }
                results.append(error_result)
                continue
        
        duration = time.time() - start_time
        Logger.log_api_call("/api/ai/analyze_positions", "POST", 200, duration)
        
        return jsonify({
            "success": True,
            "data": results,
            "marketSummary": response_market_summary,
            "modelPlan": model_plan,
            "message": f"成功分析 {len(results)} 只股票",
            "duration": duration
        })
        
    except Exception as e:
        duration = time.time() - start_time
        Logger.log_api_call("/api/ai/analyze_positions", "POST", 500, duration)
        Logger.log_error("ai_analyze", e, "分析持仓失败")
        MonitorLink.log(f"❌ 分析持仓失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


def _process_stock_data(position):
    """处理单个股票的行情数据"""
    symbol = position.get('symbol')
    if not symbol:
        return None
    
    try:
        # 优先从券商API获取实时行情数据
        current_price, volume, change_percent, prev_close = _get_quote_from_broker(symbol)

        if current_price <= 0:
            # 无法从券商API获取行情，尝试使用持仓数据中的行情
            current_price = position.get('current_price', 0)
            volume = position.get('volume', 0)
            change_percent = position.get('change_percent', 0)
            prev_close = position.get('prev_close', 0)
            
            if current_price <= 0:
                # 持仓数据中也没有行情
                MonitorLink.log(f"❌ 无行情数据: {symbol}")
                return None
            else:
                MonitorLink.log(f"⚠️ 使用持仓数据中的行情: {symbol} = {current_price}")
        else:
            MonitorLink.log(f"✅ 获取到实时行情: {symbol} = {current_price}")
        
        # 将获取到的行情保存到数据库（如果表存在）
        try:
            db = DbUtil()
            # 先检查表是否存在
            table_exists = db.fetch_one(
                "SELECT 1 FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = 'stock_quote'"
            )
            if table_exists:
                db.execute(
                    """INSERT INTO stock_quote (symbol, price, volume, updated_at) 
                       VALUES (%s, %s, %s, NOW())
                       ON DUPLICATE KEY UPDATE price = VALUES(price), volume = VALUES(volume), updated_at = NOW()""",
                    (symbol, current_price, volume)
                )
                MonitorLink.log(f"💾 行情数据已保存到数据库: {symbol}")
            else:
                MonitorLink.log(f"⚠️ stock_quote表不存在，跳过保存: {symbol}")
        except Exception as db_error:
            # 忽略保存错误，不影响主流程
            MonitorLink.log(f"⚠️ 保存行情数据失败（忽略）: {symbol} - {str(db_error)[:50]}")
        
        stock_data = {
            'symbol': symbol,
            'current_price': current_price,
            'volume': volume,
            'change_percent': change_percent,
            'prev_close': prev_close,
            'position': position
        }
        
        # 缓存行情数据（1分钟）
        APICache.set_stock_quote(symbol, stock_data, 60)
        
        return stock_data
    except Exception as e:
        Logger.log_error("batch_analyze", e, f"获取行情失败: {symbol}")
        return None

def _calculate_indicators(stock_data):
    """计算单个股票的技术指标"""
    if not stock_data:
        return None
    
    symbol = stock_data['symbol']
    current_price = stock_data['current_price']
    volume = stock_data['volume']
    
    try:
        # 检查缓存
        cached_indicators = APICache.cache_indicators(symbol)
        if cached_indicators:
            indicators = cached_indicators
        else:
            history = HistoricalMarketDataService.get_history(symbol, timeframe='daily', limit=90)
            items = history.get('items') or []
            valid_items = [item for item in items if float(item.get('close') or 0) > 0]
            if len(valid_items) < 20:
                raise ValueError(f"{HistoricalMarketDataService.normalize_symbol(symbol)} 历史行情不足，无法计算技术指标")

            prices = [float(item.get('close') or 0) for item in valid_items]
            highs = [float(item.get('high') or item.get('close') or 0) for item in valid_items]
            lows = [float(item.get('low') or item.get('close') or 0) for item in valid_items]
            volumes_data = [float(item.get('volume') or 0) for item in valid_items]

            if current_price > 0:
                prices[-1] = current_price
            if highs:
                highs[-1] = max(highs[-1], current_price or highs[-1])
            if lows and current_price > 0:
                lows[-1] = min(lows[-1], current_price)
            if volumes_data and volume > 0:
                volumes_data[-1] = volume

            rsi = IndicatorUtil.calculate_rsi(prices)
            boll_mid, boll_upper, boll_lower = IndicatorUtil.calculate_boll(prices)
            macd_diff, macd_dea, macd_hist = IndicatorUtil.calculate_macd(prices)
            
            atr = IndicatorUtilEnhanced.calculate_atr(prices, highs, lows)
            ema_short = IndicatorUtilEnhanced.calculate_ema(prices, 12)
            ema_long = IndicatorUtilEnhanced.calculate_ema(prices, 26)
            k, d, j = IndicatorUtilEnhanced.calculate_kdj(prices, highs, lows)
            obv = IndicatorUtilEnhanced.calculate_obv(prices, volumes_data)
            roc = IndicatorUtilEnhanced.calculate_roc(prices)
            cci = IndicatorUtilEnhanced.calculate_cci(prices, highs, lows)
            support, resistance = IndicatorUtilEnhanced.calculate_support_resistance(prices)
            
            indicators = {
                "rsi": rsi,
                "macd": macd_diff,
                "kdj": j,
                "boll": {
                    "upper": boll_upper,
                    "mid": boll_mid,
                    "lower": boll_lower
                },
                "ema": {
                    "short": ema_short,
                    "long": ema_long
                },
                "atr": atr,
                "roc": roc,
                "cci": cci,
                "obv": obv,
                "support": support,
                "resistance": resistance
            }
            
            # 缓存指标数据（5分钟）
            APICache.set_indicators(symbol, indicators, 300)
        
        # 构建AI分析数据
        ai_data = {
            'price': current_price,
            'rsi': indicators['rsi'],
            'macd': indicators['macd'],
            'kdj': indicators['kdj'],
            'boll_upper': indicators['boll']['upper'],
            'boll_mid': indicators['boll']['mid'],
            'boll_lower': indicators['boll']['lower'],
            'ema_short': indicators['ema']['short'],
            'ema_long': indicators['ema']['long'],
            'atr': indicators['atr'],
            'roc': indicators['roc'],
            'cci': indicators['cci'],
            'obv': indicators['obv'],
            'support': indicators['support'],
            'resistance': indicators['resistance']
        }
        
        # 简单的算法信号
        algo_side = 'BUY' if indicators['rsi'] < 30 else 'SELL' if indicators['rsi'] > 70 else 'HOLD'
        
        return {
            'symbol': symbol,
            'indicators': indicators,
            'algo_side': algo_side,
            'ai_data': ai_data,
            'stock_data': stock_data
        }
    except Exception as e:
        Logger.log_error("batch_analyze", e, f"计算指标失败: {symbol}")
        return None

def _analyze_stock(item):
    """分析单个股票"""
    if not item:
        return None
    
    symbol = item['symbol']
    indicators = item['indicators']
    algo_side = item['algo_side']
    ai_data = item['ai_data']
    
    try:
        # 检查缓存
        cached_analysis = APICache.cache_ai_analysis(symbol, "combined")
        if cached_analysis:
            analysis_item = {
                'symbol': symbol,
                'indicators': indicators,
                'algo_side': algo_side,
                'verdict': cached_analysis.get('finalDecision', 'HOLD'),
                'reason': cached_analysis.get('reason', ''),
                'gemma_analysis': {
                    'summary': cached_analysis.get('gemma', ''),
                    'trend': cached_analysis.get('gemmaTrend', ''),
                    'indicators': cached_analysis.get('gemmaIndicators', ''),
                    'levels': cached_analysis.get('gemmaLevels', ''),
                    'full_text': cached_analysis.get('gemmaFullText', '')
                },
                'llama_analysis': {
                    'summary': cached_analysis.get('llama', ''),
                    'sentiment': cached_analysis.get('llamaSentiment', ''),
                    'flow': cached_analysis.get('llamaFlow', ''),
                    'risk': cached_analysis.get('llamaRisk', ''),
                    'market_env': cached_analysis.get('llamaMarket', ''),
                    'full_text': cached_analysis.get('llama', '')
                },
                'deepseek_analysis': {
                    'summary': cached_analysis.get('deepseek', ''),
                    'fundamental_score': cached_analysis.get('deepseekFundamental', 0),
                    'technical_score': cached_analysis.get('deepseekTechnical', 0),
                    'capital_score': cached_analysis.get('deepseekCapital', 0),
                    'confidence': cached_analysis.get('deepseekConfidence', 0),
                    'decision': cached_analysis.get('finalDecision', 'HOLD'),
                    'full_text': cached_analysis.get('deepseek', '')
                },
                'final_decision': cached_analysis.get('finalDecision', '观望'),
                'final_signal': cached_analysis.get('finalSignal', 'warning'),
                'stock_data': item.get('stock_data')
            }
        else:
            # 调用真实的AI模型
            verdict, reason, gemma_analysis, llama_analysis, deepseek_analysis = AiConsultant.get_final_decision_with_details(
                symbol, algo_side, ai_data
            )
            
            # 映射决策到中文
            decision_map = {
                'BUY': '买入',
                'SELL': '卖出',
                'HOLD': '观望'
            }
            signal_map = {
                'BUY': 'success',
                'SELL': 'danger',
                'HOLD': 'warning'
            }
            
            final_decision = decision_map.get(verdict, '观望')
            final_signal = signal_map.get(verdict, 'warning')
            
            analysis_item = {
                'symbol': symbol,
                'indicators': indicators,
                'algo_side': algo_side,
                'verdict': verdict,
                'reason': reason,
                'gemma_analysis': gemma_analysis,
                'llama_analysis': llama_analysis,
                'deepseek_analysis': deepseek_analysis,
                'final_decision': final_decision,
                'final_signal': final_signal,
                'stock_data': item.get('stock_data')
            }
        
        return analysis_item
    except Exception as ai_error:
        Logger.log_error("batch_analyze", ai_error, f"AI分析失败: {symbol}")
        return {
            'symbol': symbol,
            'indicators': indicators,
            'algo_side': algo_side,
            'error': str(ai_error),
            'reason': str(ai_error),
            'gemma_analysis': {},
            'llama_analysis': {},
            'deepseek_analysis': {},
            'final_decision': '分析失败',
            'final_signal': 'danger',
            'stock_data': item.get('stock_data')
        }

def _generate_decision(analysis):
    """生成单个股票的最终决策"""
    if not analysis:
        return None
    
    symbol = analysis['symbol']
    indicators = analysis['indicators']
    
    try:
        # 构建最终分析结果
        analysis_result = {
            "symbol": symbol,
            "indicators": indicators,
            
            "gemma": analysis['gemma_analysis'].get('summary', ''),
            "gemmaFullText": analysis['gemma_analysis'].get('full_text', ''),
            "gemmaTrend": analysis['gemma_analysis'].get('trend', ''),
            "gemmaIndicators": analysis['gemma_analysis'].get('indicators', ''),
            "gemmaLevels": analysis['gemma_analysis'].get('levels', ''),
            "gemmaSignal": analysis['final_signal'],
            "gemmaDecision": analysis['final_decision'],
            
            "llama": analysis['llama_analysis'].get('summary', ''),
            "llamaFullText": analysis['llama_analysis'].get('full_text', ''),
            "llamaSentiment": analysis['llama_analysis'].get('sentiment', ''),
            "llamaFlow": analysis['llama_analysis'].get('flow', ''),
            "llamaRisk": analysis['llama_analysis'].get('risk', ''),
            "llamaMarket": analysis['llama_analysis'].get('market_env', ''),
            "llamaSignal": analysis['final_signal'],
            "llamaDecision": analysis['final_decision'],
            
            "deepseek": analysis['deepseek_analysis'].get('summary', ''),
            "deepseekFullText": analysis['deepseek_analysis'].get('full_text', ''),
            "deepseekTrend": analysis['deepseek_analysis'].get('trend', ''),
            "deepseekIndicators": analysis['deepseek_analysis'].get('indicators', ''),
            "deepseekStrategy": analysis['deepseek_analysis'].get('strategy', ''),
            "deepseekTarget": analysis['deepseek_analysis'].get('target', ''),
            "deepseekStopLoss": analysis['deepseek_analysis'].get('stop_loss', ''),
            "deepseekFundamental": analysis['deepseek_analysis'].get('fundamental_score', 0),
            "deepseekTechnical": analysis['deepseek_analysis'].get('technical_score', 0),
            "deepseekCapital": analysis['deepseek_analysis'].get('capital_score', 0),
            "deepseekConfidence": analysis['deepseek_analysis'].get('confidence', 0),
            "deepseekSignal": analysis['final_signal'],
            "deepseekDecision": analysis['final_decision'],
            
            "finalSignal": analysis['final_signal'],
            "finalDecision": analysis['final_decision'],
            "reason": analysis.get('reason', ''),
            "timestamp": time.time()
        }
        
        # 保存AI分析历史到数据库
        try:
            persistence = get_persistence_manager()
            # 从stock_data中获取价格信息
            price = 0
            if analysis.get('stock_data'):
                price = analysis['stock_data'].get('current_price', 0)
            elif indicators.get('close'):
                price = indicators['close']
            else:
                price = 0
            
            ai_history = AIAnalysisHistory(
                symbol=symbol,
                market='US' if symbol.endswith('.US') else 'CN' if symbol.endswith('.SZ') or symbol.endswith('.SH') else 'US',
                price=price,
                gemma_decision=analysis['gemma_analysis'].get('trend', ''),
                gemma_confidence=80.0,  # 假设的置信度
                gemma_analysis=analysis['gemma_analysis'].get('full_text', ''),
                llama_decision=analysis['llama_analysis'].get('sentiment', ''),
                llama_confidence=80.0,  # 假设的置信度
                llama_analysis=analysis['llama_analysis'].get('full_text', ''),
                deepseek_decision=analysis['deepseek_analysis'].get('decision', ''),
                deepseek_confidence=analysis['deepseek_analysis'].get('confidence', 75.0),
                deepseek_analysis=analysis['deepseek_analysis'].get('full_text', ''),
                final_decision=analysis_result['finalDecision'],
                final_confidence=analysis['deepseek_analysis'].get('confidence', 75.0),
                indicators=analysis_result['indicators'],
                analysis_time=datetime.now()
            )
            persistence.save_ai_analysis(ai_history)
        except Exception as db_error:
            Logger.log_error("batch_analyze", db_error, f"保存分析历史失败: {symbol}")
        
        # 缓存最终结果
        APICache.set_ai_analysis(symbol, "combined", analysis_result, 1800)  # 30分钟缓存
        
        return analysis_result
    except Exception as e:
        Logger.log_error("batch_analyze", e, f"生成决策失败: {symbol}")
        return None


@ai_bp.route('/api/ai/batch_analyze_positions', methods=['POST'])
@login_required
@rate_limit(key_func=lambda: f"ai-batch:{getattr(request, 'user_id', 'anonymous')}", limit=4, window=60)
def batch_analyze_positions():
    """批量分析持仓 - 4层批量处理架构"""
    start_time = time.time()
    logger = Logger.get_logger('api')
    
    try:
        data = request.json
        positions = data.get('positions', [])
        account_id = data.get('account_id')

        if not positions:
            return jsonify({"success": False, "error": "持仓数据不能为空"}), 400

        original_positions = positions if isinstance(positions, list) else []
        accepted_positions, batch_meta = _normalize_position_batch_payload(original_positions)
        if batch_meta["partial"]:
            duration = time.time() - start_time
            response_payload = {
                "success": True,
                "data": _build_deferred_batch_placeholders(
                    original_positions,
                    sync_limit=batch_meta["syncLimit"],
                ),
                "message": f"批量分析请求共 {batch_meta['requested']} 只股票，超过同步上限 {batch_meta['syncLimit']}，已快速接受并延后处理",
                "duration": duration,
                "accepted": True,
                "degraded": True,
                "syncLimit": batch_meta["syncLimit"],
                "stats": {
                    "total": batch_meta["requested"],
                    "accepted": 0,
                    "successful": 0,
                    "failed": 0,
                    "deferred": batch_meta["requested"],
                },
                "meta": {
                    **batch_meta,
                    "status": "accepted",
                    "executionMode": "deferred",
                }
            }
            Logger.log_api_call("/api/ai/batch_analyze_positions", "POST", 202, duration)
            return jsonify(response_payload), 202

        positions = accepted_positions

        MonitorLink.log(
            f"⚡ [批量AI分析] 开始分析 {len(positions)} 只股票"
            + (f"，其余 {batch_meta['deferred']} 只已降级为延后处理" if batch_meta["partial"] else "")
        )
        logger.info(
            f"开始批量分析 {len(positions)} 只股票"
            + (f"，延后 {batch_meta['deferred']} 只" if batch_meta["partial"] else "")
        )
        
        # 初始化结果列表
        final_results = []
        
        # 第一层：批量获取行情数据（串行）
        MonitorLink.log(f"   [第1层] 开始批量获取行情数据")
        stock_data_list = []
        error_symbols = []
        
        for position in positions:
            result = _process_stock_data(position)
            symbol = position.get('symbol')
            if result:
                stock_data_list.append(result)
            else:
                # 记录没有行情数据的股票
                error_symbols.append(symbol)
                # 构建错误结果
                error_result = {
                    "symbol": symbol,
                    "error": "无行情数据",
                    "finalSignal": "danger",
                    "finalDecision": "无行情"
                }
                final_results.append(error_result)
        
        MonitorLink.log(f"   [第1层] 完成，成功获取 {len(stock_data_list)} 只股票的行情，{len(error_symbols)} 只股票无行情")
        
        if not stock_data_list and not error_symbols:
            return jsonify({"success": False, "error": "无法获取任何股票的行情数据"}), 400
        
        # 第二层：批量计算技术指标（串行）
        if stock_data_list:
            MonitorLink.log(f"   [第2层] 开始批量计算技术指标")
            indicators_list = []
            
            for stock_data in stock_data_list:
                result = _calculate_indicators(stock_data)
                if result:
                    indicators_list.append(result)
            
            MonitorLink.log(f"   [第2层] 完成，成功计算 {len(indicators_list)} 只股票的技术指标")
            
            if indicators_list:
                # 第三层：批量AI模型分析（串行）
                MonitorLink.log(f"   [第3层] 开始批量AI模型分析")
                ai_analysis_list = []
                
                for item in indicators_list:
                    result = _analyze_stock(item)
                    if result:
                        ai_analysis_list.append(result)
                        MonitorLink.log(f"   [分析完成] {result['symbol']} -> {result['final_decision']}")
                
                MonitorLink.log(f"   [第3层] 完成，成功分析 {len(ai_analysis_list)} 只股票")
                
                if ai_analysis_list:
                    # 第四层：批量生成综合决策（串行）
                    MonitorLink.log(f"   [第4层] 开始批量生成综合决策")
                    
                    for analysis in ai_analysis_list:
                        result = _generate_decision(analysis)
                        if result:
                            final_results.append(result)
                    
                    MonitorLink.log(f"   [第4层] 完成，成功生成 {len(final_results) - len(error_symbols)} 个综合决策")

        duration = time.time() - start_time
        Logger.log_api_call("/api/ai/batch_analyze_positions", "POST", 200, duration)
        
        response_payload = {
            "success": True,
            "data": final_results,
            "message": (
                f"本次同步分析 {batch_meta['accepted']} 只股票，成功分析 {len(final_results) - len(error_symbols)} 只股票，"
                f"{len(error_symbols)} 只股票无行情"
                + (f"；其余 {batch_meta['deferred']} 只已接受但延后处理" if batch_meta["partial"] else "")
            ),
            "duration": duration,
            "accepted": True,
            "degraded": bool(batch_meta["partial"]),
            "syncLimit": batch_meta["syncLimit"],
            "stats": {
                "total": batch_meta["requested"],
                "accepted": batch_meta["accepted"],
                "successful": len(final_results) - len(error_symbols),
                "failed": len(error_symbols),
                "deferred": batch_meta["deferred"],
            },
            "meta": {
                **batch_meta,
                "status": "accepted" if batch_meta["partial"] else "completed",
            }
        }
        status_code = 202 if batch_meta["partial"] else 200
        return jsonify(response_payload), status_code
        
    except Exception as e:
        duration = time.time() - start_time
        Logger.log_api_call("/api/ai/batch_analyze_positions", "POST", 500, duration)
        Logger.log_error("batch_analyze", e, "批量分析失败")
        MonitorLink.log(f"❌ 批量分析失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
