"""
数据相关API路由
"""
from flask import Blueprint, request, jsonify
from utils.DbUtil import DbUtil
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from urllib.parse import urlencode
import json
from api.auth_routes import login_required, admin_required
from core.broker.BrokerInterface import get_broker_manager, get_broker
from core.analysis.MarketInsightService import MarketInsightService
from core.analysis.AgentRunService import AgentRunService
from core.analysis.StrategyMonitorService import StrategyMonitorService
from core.analysis.HistoricalMarketDataService import HistoricalMarketDataService
from core.readmodel.AccountAssetSnapshotService import AccountAssetSnapshotService
from core.readmodel.PositionSnapshotService import PositionSnapshotService
from core.readmodel.QuoteSnapshotService import QuoteSnapshotService
from utils.MarketUniverseSync import MarketUniverseSync

data_bp = Blueprint('data', __name__)


def _broker_is_connected(broker) -> bool:
    value = getattr(broker, 'is_connected', False)
    return value() if callable(value) else bool(value)


def _parse_account_id() -> Optional[int]:
    """解析可选的账户 ID 查询参数。"""
    account_id = request.args.get('account_id')
    if not account_id:
        return None

    try:
        return int(account_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("account_id 必须是整数") from exc


def _is_truthy_arg(value: Any) -> bool:
    return str(value or '').strip().lower() in {'1', 'true', 'yes', 'on'}


def _should_force_realtime() -> bool:
    return _is_truthy_arg(request.args.get('refresh')) or _is_truthy_arg(request.args.get('realtime'))


def _format_order_status_label(status: Any) -> str:
    if status is None:
        return "未知"

    status_text = str(status).strip()
    if "." in status_text:
        status_text = status_text.split(".")[-1]

    status_map = {
        "Unknown": "未知",
        "NotReported": "未报",
        "ReplacedNotReported": "换单未报",
        "ProtectedNotReported": "保价未报",
        "VarietiesNotReported": "竞价未报",
        "Filled": "已成交",
        "WaitToNew": "待提交",
        "New": "已提交",
        "WaitToReplace": "待修改",
        "PendingReplace": "修改中",
        "Replaced": "已修改",
        "PartialFilled": "部分成交",
        "WaitToCancel": "待撤单",
        "PendingCancel": "撤单中",
        "Rejected": "已拒绝",
        "Canceled": "已撤单",
        "Expired": "已过期",
        "Submitted": "已提交",
        "PendingSubmit": "提交中",
        "PreSubmitted": "预提交",
        "Inactive": "未激活",
    }
    return status_map.get(status_text, status_text or "未知")


def _resolve_account_id(account_id: Optional[int], user_id: int) -> Optional[int]:
    if account_id:
        return int(account_id)
    accounts = get_broker_manager().list_accounts(user_id=user_id) or []
    default_account = next((item for item in accounts if item.get('is_default')), None)
    target = default_account or (accounts[0] if accounts else None)
    if not target:
        return None
    resolved = int(target.get('id') or 0)
    return resolved or None


def _get_connected_broker(
    account_id: Optional[int] = None,
    user_id: Optional[int] = None,
    require_connection: bool = True
):
    """获取并连接券商实例。"""
    broker = get_broker(account_id, user_id=user_id)
    if not broker:
        raise LookupError("未找到可用的券商账户")

    if not _broker_is_connected(broker):
        connected = broker.connect()
        if not connected and require_connection:
            raise ConnectionError("券商连接失败")

    return broker


def _format_currency(value: float) -> str:
    return f"${float(value or 0):,.2f}"


def _format_signed_currency(value: float) -> str:
    amount = float(value or 0)
    sign = '+' if amount >= 0 else '-'
    return f"{sign}${abs(amount):,.2f}"


def _format_percent(value: float) -> str:
    return f"{float(value or 0):+.2f}%"


def _build_account_summary(account_info, positions) -> Dict[str, Any]:
    def read_value(position, attr_name: str, fallback_name: Optional[str] = None) -> float:
        if isinstance(position, dict):
            value = position.get(attr_name)
            if value is None and fallback_name:
                value = position.get(fallback_name)
            return float(value or 0)
        value = getattr(position, attr_name, None)
        if value is None and fallback_name:
            value = getattr(position, fallback_name, None)
        return float(value or 0)

    total_market_value = sum(read_value(p, 'market_value', 'marketValue') for p in positions)
    total_pnl = sum(read_value(p, 'unrealized_pnl', 'pnl') for p in positions)
    total_cost = sum(read_value(p, 'average_cost', 'avgPrice') * read_value(p, 'quantity') for p in positions)
    pnl_ratio = (total_pnl / total_cost * 100) if total_cost > 0 else 0.0

    if total_market_value <= 0:
        total_market_value = float(getattr(account_info, 'market_value', 0) or 0)

    return {
        "account_id": getattr(account_info, 'account_id', ''),
        "currency": getattr(account_info, 'currency', 'USD'),
        "total_assets": float(getattr(account_info, 'total_equity', 0) or 0),
        "daily_pnl": total_pnl,
        "today_pnl": total_pnl,
        "today_pnl_percent": pnl_ratio,
        "pnl_ratio": pnl_ratio,
        "cash": float(getattr(account_info, 'cash', 0) or 0),
        "market_value": total_market_value,
        "buying_power": float(getattr(account_info, 'buying_power', 0) or 0),
        "maintenance_margin": float(getattr(account_info, 'maintenance_margin', 0) or 0)
    }


def _load_snapshot_positions() -> List[Dict[str, Any]]:
    rows = DbUtil.fetch_all(
        """
        SELECT symbol, avg_price, quantity, current_price, update_time
        FROM positions
        ORDER BY update_time DESC
        LIMIT 50
        """
    )

    result: List[Dict[str, Any]] = []
    total_market_value = 0.0
    for row in rows:
        current_price = float(row.get('current_price') or 0)
        quantity = float(row.get('quantity') or 0)
        total_market_value += current_price * quantity

    for row in rows:
        avg_price = float(row.get('avg_price') or 0)
        current_price = float(row.get('current_price') or 0)
        quantity = float(row.get('quantity') or 0)
        market_value = quantity * current_price
        pnl = (current_price - avg_price) * quantity
        pnl_ratio = ((current_price - avg_price) / avg_price * 100) if avg_price > 0 else 0.0
        weight = (market_value / total_market_value * 100) if total_market_value > 0 else 0.0

        result.append({
            "symbol": row.get('symbol'),
            "name": row.get('symbol'),
            "quantity": quantity,
            "avg_price": avg_price,
            "avgPrice": avg_price,
            "current_price": current_price,
            "currentPrice": current_price,
            "market_value": market_value,
            "marketValue": market_value,
            "pnl": pnl,
            "pnl_ratio": pnl_ratio,
            "pnlPercent": pnl_ratio,
            "change": current_price - avg_price,
            "changePercent": pnl_ratio,
            "weight": weight,
            "holdDays": 0,
            "source": "snapshot"
        })

    return result


def _build_snapshot_summary(account_id: Optional[int], user_id: int, positions: List[Dict[str, Any]]) -> Dict[str, Any]:
    trends = DbUtil.get_asset_trend(days=7, user_id=user_id)
    latest = trends[-1] if trends else {}

    fallback_market_value = sum(float(item.get('market_value') or item.get('marketValue') or 0) for item in positions)
    market_value = float(latest.get('market_value') or 0) or fallback_market_value
    cash = float(latest.get('cash') or 0)
    total_assets = float(latest.get('total_assets') or 0)
    today_pnl = float(latest.get('today_pnl') or 0)
    today_pnl_percent = float(latest.get('today_pnl_percent') or 0)

    if total_assets <= 0:
        total_assets = cash + market_value

    return {
        "account_id": str(account_id or ''),
        "currency": "USD",
        "total_assets": total_assets,
        "daily_pnl": today_pnl,
        "today_pnl": today_pnl,
        "today_pnl_percent": today_pnl_percent,
        "pnl_ratio": today_pnl_percent,
        "cash": cash,
        "market_value": market_value,
        "buying_power": cash,
        "maintenance_margin": 0.0,
        "source": "snapshot"
    }


def _build_legacy_account_card(summary: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "account_id": summary.get("account_id"),
        "currency": summary.get("currency", "USD"),
        "total_val": _format_currency(summary.get("total_assets", 0)),
        "daily_pnl": _format_signed_currency(summary.get("daily_pnl", 0)),
        "pnl_ratio": _format_percent(summary.get("pnl_ratio", 0)),
        "cash": _format_currency(summary.get("cash", 0)),
        "mkt_val": _format_currency(summary.get("market_value", 0))
    }


def _load_realtime_account_state(account_id: Optional[int] = None, user_id: Optional[int] = None) -> Tuple[Any, Dict[str, Any], List[Any]]:
    if user_id is None:
        raise ValueError("user_id is required")
    broker = _get_connected_broker(account_id, user_id=user_id, require_connection=False)
    positions = broker.get_positions() or []

    if not positions:
        snapshot_positions = _load_snapshot_positions()
        if snapshot_positions:
            positions = snapshot_positions

    try:
        account_info = broker.get_account_info()
        summary = _build_account_summary(account_info, positions)
        summary.setdefault("source", "realtime")
    except Exception:
        summary = _build_snapshot_summary(account_id, user_id, positions if positions and isinstance(positions[0], dict) else [
            {
                "market_value": float(getattr(position, 'market_value', 0) or 0),
                "marketValue": float(getattr(position, 'market_value', 0) or 0)
            } for position in positions
        ])

    return broker, summary, positions


def _persist_asset_trend(summary: Dict[str, Any], user_id: int) -> None:
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        DbUtil.save_asset_trend(
            today,
            float(summary.get('total_assets', 0) or 0),
            float(summary.get('cash', 0) or 0),
            float(summary.get('market_value', 0) or 0),
            float(summary.get('today_pnl', 0) or 0),
            float(summary.get('today_pnl_percent', 0) or 0),
            user_id=user_id
        )
    except Exception as exc:
        print(f"⚠️ [API] 保存资产趋势失败: {exc}")


def _serialize_realtime_holding(position) -> Dict[str, Any]:
    avg_price = float(position.average_cost or 0)
    current_price = float(position.market_price or 0)
    quantity = float(position.quantity or 0)
    market_value = float(position.market_value or (current_price * quantity))
    pnl = float(position.unrealized_pnl or 0)
    pnl_ratio = ((current_price - avg_price) / avg_price * 100) if avg_price > 0 else 0.0

    return {
        "symbol": position.symbol,
        "name": position.name or position.symbol,
        "avg_price": avg_price,
        "quantity": quantity,
        "current_price": current_price,
        "market_value": market_value,
        "pnl": pnl,
        "pnl_ratio": pnl_ratio,
        "update_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }


def _serialize_legacy_holding(position) -> Dict[str, Any]:
    if isinstance(position, dict):
        current_price = float(position.get('currentPrice') or position.get('current_price') or 0)
        avg_price = float(position.get('avgPrice') or position.get('avg_price') or position.get('average_cost') or 0)
        pnl = float(position.get('pnl') or position.get('unrealized_pnl') or 0)
        quantity = float(position.get('quantity') or 0)
        return {
            "symbol": position.get('symbol') or '',
            "price": f"{current_price:.2f}",
            "cost": f"{avg_price:.2f}",
            "pnl": f"{pnl:+.2f}",
            "qty": quantity
        }
    pnl = float(position.unrealized_pnl or 0)
    return {
        "symbol": position.symbol,
        "price": f"{float(position.market_price or 0):.2f}",
        "cost": f"{float(position.average_cost or 0):.2f}",
        "pnl": f"{pnl:+.2f}",
        "qty": float(position.quantity or 0)
    }


def _serialize_legacy_order(order) -> Dict[str, Any]:
    if isinstance(order, dict):
        return {
            "id": order.get('orderId') or order.get('order_id') or '',
            "symbol": order.get('symbol') or '',
            "side": str(order.get('action') or order.get('side') or '').upper() or 'BUY',
            "price": float(order.get('price') or 0),
            "qty": float(order.get('quantity') or 0),
            "status": order.get('status') or '',
            "create_time": str(order.get('createTime') or order.get('create_time') or '')
        }
    return {
        "id": getattr(order, 'order_id', ''),
        "symbol": getattr(order, 'symbol', ''),
        "side": str(getattr(order, 'action', '') or '').upper() or 'BUY',
        "price": float(getattr(order, 'price', 0) or 0),
        "qty": float(getattr(order, 'quantity', 0) or 0),
        "status": getattr(order, 'status', ''),
        "create_time": str(getattr(order, 'create_time', '') or '')
    }


def _serialize_snapshot_position_row(position: Dict[str, Any]) -> Dict[str, Any]:
    avg_price = float(position.get('avgPrice') or position.get('avg_price') or 0)
    current_price = float(position.get('currentPrice') or position.get('current_price') or 0)
    quantity = float(position.get('quantity') or 0)
    pnl = float(position.get('pnl') or 0)
    pnl_percent = float(position.get('pnlPercent') or position.get('pnl_percent') or 0)
    market_value = float(position.get('marketValue') or position.get('market_value') or (current_price * quantity))
    return {
        **position,
        "avg_price": avg_price,
        "avgPrice": avg_price,
        "current_price": current_price,
        "currentPrice": current_price,
        "market_value": market_value,
        "marketValue": market_value,
        "pnl": pnl,
        "pnl_ratio": pnl_percent,
        "pnlPercent": pnl_percent,
        "change": current_price - avg_price,
        "changePercent": pnl_percent,
        "available_quantity": float(position.get('availableQuantity') or position.get('available_quantity') or quantity),
        "snapshot_at": position.get('snapshotAt') or position.get('snapshot_at'),
        "source": position.get('source') or 'snapshot'
    }


STOCK_TABLE_BY_MARKET = {
    'US': {'table': 'large_cap_stocks', 'name_field': 'company_name', 'market': 'US', 'type': 'stock', 'category_field': 'sector'},
    'CN': {'table': 'cn_stocks', 'name_field': 'name', 'market': 'CN', 'type': 'stock', 'category_field': 'sector'},
    'HK': {'table': 'hk_stocks', 'name_field': 'name', 'market': 'HK', 'type': 'stock', 'category_field': 'sector'}
}

ETF_TABLE_BY_MARKET = {
    'US': {'table': 'us_etf', 'name_field': 'etf_name', 'market': 'US', 'type': 'etf', 'category_field': 'category'},
    'CN': {'table': 'cn_etf', 'name_field': 'etf_name', 'market': 'CN', 'type': 'etf', 'category_field': 'category'},
    'HK': {'table': 'hk_etf', 'name_field': 'etf_name', 'market': 'HK', 'type': 'etf', 'category_field': 'category'}
}


def _table_exists(table_name: str) -> bool:
    row = DbUtil.query_one(
        "SELECT 1 FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = %s",
        (table_name,)
    )
    return bool(row)


def _resolve_stock_pool_table(market: str, asset_type: str = 'stock') -> Dict[str, str]:
    market_key = str(market or 'US').strip().upper()
    if str(asset_type or 'stock').strip().lower() == 'etf':
        return ETF_TABLE_BY_MARKET.get(market_key, ETF_TABLE_BY_MARKET['US'])
    return STOCK_TABLE_BY_MARKET.get(market_key, STOCK_TABLE_BY_MARKET['US'])


def _iter_stock_pool_tables(market: str) -> List[Dict[str, str]]:
    market_key = str(market or 'all').strip().upper()
    if market_key == 'ALL':
        return list(ETF_TABLE_BY_MARKET.values()) + list(STOCK_TABLE_BY_MARKET.values())

    tables = []
    if market_key in ETF_TABLE_BY_MARKET:
        tables.append(ETF_TABLE_BY_MARKET[market_key])
    if market_key in STOCK_TABLE_BY_MARKET:
        tables.append(STOCK_TABLE_BY_MARKET[market_key])
    return tables


def _fetch_stock_pool_rows(
    table_config: Dict[str, str],
    user_id: int,
    search: str = '',
    group_id: str = ''
) -> List[Dict[str, Any]]:
    table_name = table_config['table']
    if not _table_exists(table_name):
        return []

    where_clause = "WHERE is_active = 1 AND user_id = %s"
    params: List[Any] = [user_id]
    if search:
        where_clause += f" AND (symbol LIKE %s OR {table_config['name_field']} LIKE %s)"
        params.extend([f"%{search}%", f"%{search}%"])
    if group_id:
        where_clause += " AND group_id = %s"
        params.append(group_id)

    sql = f"""
        SELECT symbol,
               {table_config['name_field']} AS display_name,
               market,
               {table_config['category_field']} AS display_category,
               group_id,
               current_price,
               change_percent,
               volume,
               market_cap,
               pe_ratio
        FROM {table_name}
        {where_clause}
        ORDER BY symbol
    """
    results = DbUtil.query_all(sql, tuple(params))

    items = []
    for row in results:
        items.append({
            "symbol": row[0],
            "name": row[1] or row[0],
            "market": row[2] or table_config['market'],
            "sector": row[3] or "",
            "group_id": row[4],
            "price": None,
            "change_percent": None,
            "volume": None,
            "market_cap": float(row[8]) if row[8] is not None else None,
            "pe": float(row[9]) if row[9] is not None else None,
            "prev_close": None,
            "open": None,
            "high": None,
            "low": None,
            "change": None,
            "turnover": None,
            "quote_source": "pending",
            "quote_snapshot_at": None,
            "quoteReady": False,
            "type": table_config['type']
        })

    live_quotes = _fetch_live_quotes([item["symbol"] for item in items], user_id=user_id)
    merged_items: List[Dict[str, Any]] = []
    for item in items:
        symbol = _normalize_market_symbol(item["symbol"])
        quote = live_quotes.get(symbol) or {}
        last_price = quote.get("last_price")
        merged_items.append({
            **item,
            "price": float(last_price) if last_price not in (None, "") else None,
            "change": quote.get("change"),
            "change_percent": quote.get("change_percent"),
            "prev_close": quote.get("prev_close"),
            "open": quote.get("open"),
            "high": quote.get("high"),
            "low": quote.get("low"),
            "volume": quote.get("volume"),
            "quote_source": "longbridge-live" if quote else "pending",
            "quote_snapshot_at": quote.get("timestamp") or quote.get("updated_at") or None,
            "quoteReady": bool(quote),
        })
    return merged_items


def _count_stock_pool_rows(
    table_config: Dict[str, str],
    user_id: int,
    group_id: str = ''
) -> int:
    table_name = table_config['table']
    if not _table_exists(table_name):
        return 0

    where_clause = "WHERE is_active = 1 AND user_id = %s"
    params: List[Any] = [user_id]
    if group_id:
        where_clause += " AND group_id = %s"
        params.append(group_id)

    row = DbUtil.query_one(
        f"SELECT COUNT(1) FROM {table_name} {where_clause}",
        tuple(params)
    )
    return int(row[0] or 0) if row else 0


def _build_stock_pool_stats(user_id: int, group_id: str = '') -> Dict[str, Any]:
    stats = {
        "total": 0,
        "stocks": 0,
        "etfs": 0,
        "markets": {
            "US": 0,
            "CN": 0,
            "HK": 0
        }
    }

    for market, table_config in STOCK_TABLE_BY_MARKET.items():
        count = _count_stock_pool_rows(table_config, user_id, group_id=group_id)
        stats["stocks"] += count
        stats["markets"][market] += count
        stats["total"] += count

    for market, table_config in ETF_TABLE_BY_MARKET.items():
        count = _count_stock_pool_rows(table_config, user_id, group_id=group_id)
        stats["etfs"] += count
        stats["markets"][market] += count
        stats["total"] += count

    return stats


def _normalize_market_symbol(symbol: str) -> str:
    return HistoricalMarketDataService.normalize_symbol(str(symbol or '').strip().upper())


def _load_quote_snapshot_map(symbols: List[str], max_age_minutes: int = 20) -> Dict[str, Dict[str, Any]]:
    return QuoteSnapshotService.get_latest_map(symbols, max_age_minutes=max_age_minutes)


def _merge_quote_snapshot(base: Dict[str, Any], snapshot: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    merged = dict(base or {})
    quote_snapshot = snapshot or {}
    if quote_snapshot.get("price") not in (None, ""):
        merged["price"] = quote_snapshot.get("price")
    if quote_snapshot.get("change") not in (None, ""):
        merged["change"] = quote_snapshot.get("change")
    if quote_snapshot.get("change_percent") not in (None, ""):
        merged["change_percent"] = quote_snapshot.get("change_percent")
    if quote_snapshot.get("prev_close") not in (None, ""):
        merged["prev_close"] = quote_snapshot.get("prev_close")
    if quote_snapshot.get("open") not in (None, ""):
        merged["open"] = quote_snapshot.get("open")
    if quote_snapshot.get("high") not in (None, ""):
        merged["high"] = quote_snapshot.get("high")
    if quote_snapshot.get("low") not in (None, ""):
        merged["low"] = quote_snapshot.get("low")
    if quote_snapshot.get("volume") not in (None, ""):
        merged["volume"] = quote_snapshot.get("volume")
    if quote_snapshot.get("turnover") not in (None, ""):
        merged["turnover"] = quote_snapshot.get("turnover")
    merged["quote_source"] = quote_snapshot.get("source") or merged.get("quote_source") or "universe"
    merged["quote_snapshot_at"] = quote_snapshot.get("snapshotAt") or merged.get("quote_snapshot_at")
    merged["quoteReady"] = bool(
        merged.get("quoteReady")
        or merged.get("price")
        or merged.get("prev_close")
        or merged.get("open")
        or merged.get("high")
        or merged.get("low")
        or merged.get("quote_snapshot_at")
    )
    return merged


def _candidate_quote_accounts(user_id: int, account_id: Optional[int] = None) -> List[Dict[str, Any]]:
    manager = get_broker_manager()
    accounts: List[Dict[str, Any]] = []

    if account_id:
        row = DbUtil.fetch_one(
            """
            SELECT id, user_id, broker_type
            FROM broker_accounts
            WHERE id = %s AND is_active = 1
            LIMIT 1
            """,
            (int(account_id),)
        )
        return [row] if row else []

    for account in manager.list_accounts(user_id=user_id) or []:
        candidate = {
            "id": int(account.get("id") or 0),
            "user_id": user_id,
            "broker_type": account.get("broker_type")
        }
        if candidate["id"]:
            accounts.append(candidate)

    if accounts:
        return accounts

    rows = DbUtil.fetch_all(
        """
        SELECT id, user_id, broker_type
        FROM broker_accounts
        WHERE is_active = 1
        ORDER BY is_default DESC, id ASC
        LIMIT 3
        """
    ) or []
    return rows


def _fetch_live_quotes(symbols: List[str], user_id: int, account_id: Optional[int] = None) -> Dict[str, Dict[str, Any]]:
    normalized_symbols = []
    for raw_symbol in symbols:
        symbol = _normalize_market_symbol(raw_symbol)
        if symbol and symbol not in normalized_symbols:
            normalized_symbols.append(symbol)

    if not normalized_symbols:
        return {}

    manager = get_broker_manager()
    result: Dict[str, Dict[str, Any]] = {}
    for account in _candidate_quote_accounts(user_id=user_id, account_id=account_id):
        try:
            broker = manager.get_broker(int(account.get("id")), user_id=int(account.get("user_id") or user_id))
            if not broker:
                continue
            if not broker.is_connected and not broker.connect():
                continue

            raw_quotes = broker.get_quote(normalized_symbols) or {}
            for symbol in normalized_symbols:
                quote = raw_quotes.get(symbol)
                if not quote:
                    continue

                if hasattr(quote, 'last_price'):
                    last_price = float(getattr(quote, 'last_price', 0) or 0)
                    prev_close = float(getattr(quote, 'prev_close', 0) or 0)
                    change_percent = float(getattr(quote, 'change_percent', 0) or 0)
                    result[symbol] = {
                        "symbol": symbol,
                        "last_price": last_price,
                        "prev_close": prev_close,
                        "open": float(getattr(quote, 'open', 0) or 0),
                        "high": float(getattr(quote, 'high', 0) or 0),
                        "low": float(getattr(quote, 'low', 0) or 0),
                        "volume": int(getattr(quote, 'volume', 0) or 0),
                        "change_percent": change_percent,
                        "change": (last_price - prev_close) if prev_close else 0.0
                    }
                    continue

                last_price = float(quote.get('last_price', 0) or 0)
                prev_close = float(quote.get('prev_close', 0) or 0)
                change_percent = quote.get('change_percent')
                if change_percent is None and prev_close:
                    change_percent = ((last_price - prev_close) / prev_close) * 100
                result[symbol] = {
                    "symbol": symbol,
                    "last_price": last_price,
                    "prev_close": prev_close,
                    "open": float(quote.get('open', prev_close) or 0),
                    "high": float(quote.get('high', last_price) or 0),
                    "low": float(quote.get('low', last_price) or 0),
                    "volume": int(quote.get('volume', 0) or 0),
                    "change_percent": float(change_percent or 0),
                    "change": (last_price - prev_close) if prev_close else 0.0
                }

            if len(result) >= len(normalized_symbols):
                break
        except Exception as exc:
            print(f"⚠️ [API] 批量获取行情失败: account={account.get('id')} error={exc}")
            continue

    return result


def _universe_table_candidates(symbol: str) -> List[Dict[str, str]]:
    market = HistoricalMarketDataService.detect_market(symbol)
    candidates = []
    stock_table = STOCK_TABLE_BY_MARKET.get(market)
    etf_table = ETF_TABLE_BY_MARKET.get(market)
    if stock_table:
        candidates.append(stock_table)
    if etf_table:
        candidates.append(etf_table)
    return candidates


def _lookup_universe_snapshot(symbol: str) -> Dict[str, Any]:
    normalized_symbol = _normalize_market_symbol(symbol)
    for table_config in _universe_table_candidates(normalized_symbol):
        table_name = table_config['table']
        if not _table_exists(table_name):
            continue
        row = DbUtil.fetch_one(
            f"""
            SELECT symbol,
                   {table_config['name_field']} AS display_name,
                   market,
                   {table_config['category_field']} AS display_category,
                   current_price,
                   change_percent,
                   volume,
                   market_cap,
                   pe_ratio
            FROM {table_name}
            WHERE symbol = %s
            LIMIT 1
            """,
            (normalized_symbol,)
        )
        if not row:
            continue
        base_snapshot = {
            "symbol": row.get("symbol") or normalized_symbol,
            "name": row.get("display_name") or normalized_symbol,
            "market": row.get("market") or HistoricalMarketDataService.detect_market(normalized_symbol),
            "sector": row.get("display_category") or "",
            "type": table_config["type"],
            "price": None,
            "change_percent": None,
            "volume": None,
            "market_cap": float(row.get("market_cap") or 0),
            "pe": float(row.get("pe_ratio") or 0) if row.get("pe_ratio") is not None else None,
            "pb": None,
            "prev_close": None,
            "open": None,
            "high": None,
            "low": None,
            "change": None,
            "turnover": None,
            "quote_source": "metadata",
            "quote_snapshot_at": None,
            "quoteReady": False,
        }
        return base_snapshot
    return {
        "symbol": normalized_symbol,
        "name": normalized_symbol,
        "market": HistoricalMarketDataService.detect_market(normalized_symbol),
        "sector": "",
        "type": "stock",
        "price": None,
        "change_percent": None,
        "volume": None,
        "market_cap": 0.0,
        "pe": None,
        "pb": None,
        "prev_close": None,
        "open": None,
        "high": None,
        "low": None,
        "change": None,
        "turnover": None,
        "quote_source": "metadata",
        "quote_snapshot_at": None,
        "quoteReady": False,
    }


def _search_universe(keyword: str, market: str = 'ALL', limit: int = 20) -> List[Dict[str, Any]]:
    search = str(keyword or '').strip()
    if not search:
        return []

    table_configs = _iter_stock_pool_tables(market)
    items: List[Dict[str, Any]] = []
    for table_config in table_configs:
        if not _table_exists(table_config['table']):
            continue
        rows = DbUtil.fetch_all(
            f"""
            SELECT symbol,
                   {table_config['name_field']} AS display_name,
                   market,
                   {table_config['category_field']} AS display_category,
                   current_price,
                   change_percent,
                   volume,
                   market_cap,
                   pe_ratio
            FROM {table_config['table']}
            WHERE is_active = 1
              AND (symbol LIKE %s OR {table_config['name_field']} LIKE %s)
            ORDER BY
              CASE WHEN symbol = %s THEN 0
                   WHEN symbol LIKE %s THEN 1
                   WHEN {table_config['name_field']} LIKE %s THEN 2
                   ELSE 3 END,
              symbol ASC
            LIMIT %s
            """,
            (f"%{search}%", f"%{search}%", search.upper(), f"{search.upper()}%", f"{search}%", int(limit))
        ) or []

        for row in rows:
            items.append({
                "symbol": row.get("symbol"),
                "name": row.get("display_name") or row.get("symbol"),
                "market": row.get("market") or table_config["market"],
                "sector": row.get("display_category") or "",
                "type": table_config["type"],
                "price": float(row.get("current_price") or 0) if row.get("current_price") is not None else None,
                "change_percent": float(row.get("change_percent") or 0) if row.get("change_percent") is not None else None,
                "volume": int(row.get("volume") or 0) if row.get("volume") is not None else None,
                "market_cap": float(row.get("market_cap") or 0) if row.get("market_cap") is not None else None,
                "pe": float(row.get("pe_ratio") or 0) if row.get("pe_ratio") is not None else None
            })

    deduped: Dict[str, Dict[str, Any]] = {}
    for item in items:
        symbol = item.get("symbol")
        if symbol and symbol not in deduped:
            deduped[symbol] = item
        if len(deduped) >= int(limit):
            break
    return list(deduped.values())[:int(limit)]


def _ensure_risk_control_tables() -> None:
    DbUtil.execute_sql(
        """
        CREATE TABLE IF NOT EXISTS user_risk_limits (
            user_id INT NOT NULL PRIMARY KEY,
            max_position_size DECIMAL(10, 2) DEFAULT 35.00,
            max_loss_per_trade DECIMAL(18, 2) DEFAULT 1000.00,
            max_daily_loss DECIMAL(18, 2) DEFAULT 5000.00,
            max_drawdown DECIMAL(10, 2) DEFAULT 20.00,
            volatility_limit DECIMAL(10, 2) DEFAULT 50.00,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    DbUtil.execute_sql(
        """
        CREATE TABLE IF NOT EXISTS user_risk_orders (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            account_id INT DEFAULT NULL,
            symbol VARCHAR(32) NOT NULL,
            order_type VARCHAR(16) NOT NULL,
            trigger_price DECIMAL(18, 4) DEFAULT 0,
            quantity DECIMAL(18, 4) DEFAULT NULL,
            status VARCHAR(20) DEFAULT 'active',
            note VARCHAR(255) DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uniq_user_symbol_type (user_id, symbol, order_type),
            INDEX idx_user_type_status (user_id, order_type, status)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )


def _default_risk_limits() -> Dict[str, float]:
    return {
        "maxPositionSize": 35.0,
        "maxLossPerTrade": 1000.0,
        "maxDailyLoss": 5000.0,
        "maxDrawdown": 20.0,
        "volatilityLimit": 50.0
    }


def _load_risk_limits(user_id: int) -> Dict[str, float]:
    _ensure_risk_control_tables()
    row = DbUtil.fetch_one(
        """
        SELECT max_position_size, max_loss_per_trade, max_daily_loss, max_drawdown, volatility_limit
        FROM user_risk_limits
        WHERE user_id = %s
        LIMIT 1
        """,
        (user_id,)
    ) or {}
    defaults = _default_risk_limits()
    values = {
        "maxPositionSize": float(row.get("max_position_size") or defaults["maxPositionSize"]),
        "maxLossPerTrade": float(row.get("max_loss_per_trade") or defaults["maxLossPerTrade"]),
        "maxDailyLoss": float(row.get("max_daily_loss") or defaults["maxDailyLoss"]),
        "maxDrawdown": float(row.get("max_drawdown") or defaults["maxDrawdown"]),
        "volatilityLimit": float(row.get("volatility_limit") or defaults["volatilityLimit"])
    }
    return {
        **values,
        "max_position_size": values["maxPositionSize"],
        "max_loss_per_trade": values["maxLossPerTrade"],
        "max_daily_loss": values["maxDailyLoss"],
        "max_drawdown": values["maxDrawdown"],
        "volatility_limit": values["volatilityLimit"]
    }


def _load_position_snapshot(user_id: int, account_id: Optional[int] = None) -> Dict[str, Dict[str, Any]]:
    positions_by_symbol: Dict[str, Dict[str, Any]] = {}
    try:
        manager = get_broker_manager()
        accounts = _candidate_quote_accounts(user_id=user_id, account_id=account_id)
        for account in accounts:
            broker = manager.get_broker(int(account.get("id")), user_id=int(account.get("user_id") or user_id))
            if not broker:
                continue
            if not broker.is_connected and not broker.connect():
                continue
            positions = broker.get_positions() or []
            total_market_value = sum(float(getattr(item, 'market_value', 0) or 0) for item in positions)
            for position in positions:
                symbol = _normalize_market_symbol(getattr(position, 'symbol', ''))
                quantity = float(getattr(position, 'quantity', 0) or 0)
                current_price = float(getattr(position, 'market_price', 0) or 0)
                market_value = float(getattr(position, 'market_value', quantity * current_price) or 0)
                avg_price = float(getattr(position, 'average_cost', 0) or 0)
                pnl_percent = ((current_price - avg_price) / avg_price * 100) if avg_price > 0 else 0.0
                positions_by_symbol[symbol] = {
                    "symbol": symbol,
                    "quantity": quantity,
                    "currentPrice": current_price,
                    "marketValue": market_value,
                    "weight": (market_value / total_market_value * 100) if total_market_value > 0 else 0.0,
                    "pnlPercent": pnl_percent
                }
        return positions_by_symbol
    except Exception as exc:
        print(f"⚠️ [API] 加载持仓快照失败: {exc}")
        return {}


def _load_risk_orders(user_id: int, order_type: str, account_id: Optional[int] = None) -> List[Dict[str, Any]]:
    _ensure_risk_control_tables()
    rows = DbUtil.fetch_all(
        """
        SELECT id, account_id, symbol, trigger_price, quantity, status, note, created_at, updated_at
        FROM user_risk_orders
        WHERE user_id = %s AND order_type = %s AND status = 'active'
        ORDER BY updated_at DESC, id DESC
        LIMIT 100
        """,
        (user_id, order_type)
    ) or []

    symbols = [row.get("symbol") for row in rows if row.get("symbol")]
    quote_map = _fetch_live_quotes(symbols, user_id=user_id, account_id=account_id)
    position_map = _load_position_snapshot(user_id=user_id, account_id=account_id)

    results = []
    for row in rows:
        symbol = _normalize_market_symbol(row.get("symbol"))
        quote = quote_map.get(symbol) or {}
        position = position_map.get(symbol) or {}
        current_price = float(quote.get("last_price") or position.get("currentPrice") or _lookup_universe_snapshot(symbol).get("price") or 0)
        trigger_price = float(row.get("trigger_price") or 0)
        if order_type == 'stop_loss':
            distance = ((current_price - trigger_price) / current_price * 100) if current_price else 0.0
        else:
            distance = ((trigger_price - current_price) / current_price * 100) if current_price else 0.0
        results.append({
            "id": int(row.get("id") or 0),
            "accountId": row.get("account_id"),
            "symbol": symbol,
            "price": trigger_price,
            "stopPrice": trigger_price if order_type == 'stop_loss' else None,
            "profitPrice": trigger_price if order_type == 'take_profit' else None,
            "quantity": float(row.get("quantity") or position.get("quantity") or 0),
            "currentPrice": round(current_price, 4),
            "distance": round(distance, 2),
            "status": row.get("status") or 'active',
            "note": row.get("note") or '',
            "updatedAt": row.get("updated_at").strftime('%Y-%m-%d %H:%M:%S') if row.get("updated_at") else None,
            "createdAt": row.get("created_at").strftime('%Y-%m-%d %H:%M:%S') if row.get("created_at") else None
        })
    return results


def _compute_asset_drawdown(user_id: int) -> float:
    trend_rows = DbUtil.get_asset_trend(days=90, user_id=user_id) or []
    if len(trend_rows) < 2:
        return 0.0
    peak = 0.0
    max_drawdown = 0.0
    for row in trend_rows:
        value = float(row.get('total_assets') or 0)
        peak = max(peak, value)
        if peak > 0:
            max_drawdown = min(max_drawdown, (value - peak) / peak)
    return round(abs(max_drawdown) * 100, 2)


AGENT_REVIEW_SCENE_LABELS = {
    "watchlist_pre_open_review": "自选股盘前复核",
    "watchlist_post_close_review": "自选股盘后复核",
}
AGENT_REVIEW_SLA_HOURS = {
    "watchlist_pre_open_review": 2,
    "watchlist_post_close_review": 18,
}


def _coerce_agent_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return [item for item in value if item not in (None, "")]
    if value in (None, ""):
        return []
    return [value]


def _first_agent_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, (list, tuple)):
            text = "，".join(str(item).strip() for item in value if str(item or "").strip())
        elif isinstance(value, dict):
            text = str(value.get("summary") or value.get("message") or value.get("title") or "").strip()
        else:
            text = str(value or "").strip()
        if text:
            return text
    return ""


def _normalize_agent_risk_level(value: Any) -> str:
    text = str(value or "").strip().lower()
    if any(token in text for token in ("critical", "severe", "high", "高", "严重")):
        return "high"
    if any(token in text for token in ("medium", "moderate", "中")):
        return "medium"
    return "low"


def _extract_agent_risk_symbols(item: Any) -> List[str]:
    if not isinstance(item, dict):
        return []
    raw_symbols = item.get("symbols") or item.get("symbol") or item.get("tickers") or item.get("ticker")
    if isinstance(raw_symbols, list):
        values = raw_symbols
    else:
        values = [raw_symbols]
    symbols = []
    for value in values:
        symbol = str(value or "").strip().upper()
        if symbol and symbol not in symbols:
            symbols.append(symbol)
    return symbols


def _collect_agent_risk_events(user_id: int, limit: int = 20) -> List[Dict[str, Any]]:
    try:
        rows = AgentRunService.list_recent_runs(
            user_id=user_id,
            limit=max(1, min(int(limit or 20), 80)),
            use_primary=True,
        )
    except Exception as exc:
        print(f"⚠️ [API] 获取 Agent 风险事件失败: user={user_id} error={exc}")
        return []

    events: List[Dict[str, Any]] = []
    for row in rows:
        run_id = row.get("runId") or row.get("run_id") or row.get("id")
        scene = str(row.get("scene") or "").strip()
        if not run_id or scene not in AGENT_REVIEW_SCENE_LABELS:
            continue

        result = row.get("resultSummary") if isinstance(row.get("resultSummary"), dict) else {}
        risk_flags = _coerce_agent_list(result.get("riskFlags") or result.get("risk_flags"))
        if not risk_flags:
            continue

        timestamp = row.get("finishedAt") or row.get("updatedAt") or row.get("createdAt")
        route_query = urlencode({"agentRunId": str(run_id), "scene": scene})
        lifecycle = _agent_review_lifecycle(row, scene)
        for index, risk_flag in enumerate(risk_flags, start=1):
            if isinstance(risk_flag, dict):
                level = _normalize_agent_risk_level(
                    risk_flag.get("severity")
                    or risk_flag.get("level")
                    or risk_flag.get("riskLevel")
                    or risk_flag.get("risk_level")
                )
                symbols = _extract_agent_risk_symbols(risk_flag)
                message = _first_agent_text(
                    risk_flag.get("message"),
                    risk_flag.get("summary"),
                    risk_flag.get("description"),
                    risk_flag.get("title"),
                    risk_flag.get("reason"),
                )
                evidence = _coerce_agent_list(risk_flag.get("evidence") or risk_flag.get("evidenceRefs"))
            else:
                level = "medium"
                symbols = []
                message = _first_agent_text(risk_flag)
                evidence = []

            if not message:
                message = "Agent 复核识别到结构化风险，请进入任务中心查看证据和复核建议。"

            active = _is_active_agent_review_risk(lifecycle)
            events.append({
                "id": f"agent:{run_id}:risk:{index}",
                "level": level,
                "type": f"{AGENT_REVIEW_SCENE_LABELS[scene]} Agent 风险",
                "symbol": symbols[0] if symbols else None,
                "symbols": symbols,
                "message": message[:500],
                "timestamp": timestamp,
                "source": "agent-review",
                "route": f"/scheduler-center?{route_query}",
                "runId": run_id,
                "run_id": run_id,
                "scene": scene,
                "evidence": evidence[:5],
                "active": active,
                **lifecycle,
            })
            if len(events) >= limit:
                return events

    events.sort(key=lambda item: _parse_datetime_value(item.get("timestamp")), reverse=True)
    return events[:limit]


def _build_risk_overview(user_id: int, account_id: Optional[int] = None) -> Dict[str, Any]:
    limits = _load_risk_limits(user_id)
    alerts = StrategyMonitorService.get_alerts(user_id=user_id, limit=50)
    agent_risk_events = _collect_agent_risk_events(user_id=user_id, limit=20)
    active_agent_risk_events = [item for item in agent_risk_events if _is_active_agent_review_risk(item)]
    stop_loss_orders = _load_risk_orders(user_id=user_id, order_type='stop_loss', account_id=account_id)
    take_profit_orders = _load_risk_orders(user_id=user_id, order_type='take_profit', account_id=account_id)
    positions = list(_load_position_snapshot(user_id=user_id, account_id=account_id).values())

    high_risk_count = len([item for item in alerts if item.get('severity') == 'high'])
    high_risk_count += len([item for item in active_agent_risk_events if item.get('level') == 'high'])
    medium_risk_count = len([item for item in alerts if item.get('severity') == 'medium'])
    medium_risk_count += len([item for item in active_agent_risk_events if item.get('level') == 'medium'])
    max_weight = max((float(item.get('weight') or 0) for item in positions), default=0.0)
    drawdown = _compute_asset_drawdown(user_id)
    protection_count = len(stop_loss_orders) + len(take_profit_orders)

    score = 100.0
    score -= high_risk_count * 12
    score -= medium_risk_count * 6
    score -= max(0.0, max_weight - float(limits["maxPositionSize"])) * 0.6
    score -= max(0.0, drawdown - float(limits["maxDrawdown"])) * 0.8
    score = max(8.0, min(98.0, score))

    score_label = '低风险'
    if score < 55:
        score_label = '高风险'
    elif score < 75:
        score_label = '中风险'

    events = []
    for alert in alerts:
        severity = alert.get('severity') or 'medium'
        strategy_name = alert.get('strategyName') or '持仓规则'
        action = alert.get('actionSuggested') or 'ALERT'
        events.append({
            "id": alert.get("id"),
            "level": severity,
            "type": strategy_name,
            "symbol": alert.get("symbol"),
            "message": f"{alert.get('message') or ''}，建议动作: {action}",
            "timestamp": alert.get("createdAt")
        })
    events.extend(agent_risk_events)
    events.sort(key=lambda item: _parse_datetime_value(item.get("timestamp")), reverse=True)

    return {
        "config": limits,
        "overview": {
            "score": round(score, 2),
            "scoreLabel": score_label,
            "scoreDescription": f"高风险 {high_risk_count} 条，中风险 {medium_risk_count} 条",
            "maxWeight": round(max_weight, 2),
            "positionLimit": float(limits["maxPositionSize"]),
            "drawdown": drawdown,
            "drawdownLimit": float(limits["maxDrawdown"]),
            "protectionCount": protection_count,
            "stopLossCount": len(stop_loss_orders),
            "takeProfitCount": len(take_profit_orders),
            "positionCount": len(positions)
        },
        "events": events,
        "stopLossOrders": stop_loss_orders,
        "takeProfitOrders": take_profit_orders
    }


def _ensure_notification_state_table() -> None:
    DbUtil.execute_sql(
        """
        CREATE TABLE IF NOT EXISTS user_notification_states (
            user_id INT NOT NULL,
            notification_key VARCHAR(120) NOT NULL,
            is_read TINYINT(1) DEFAULT 0,
            is_hidden TINYINT(1) DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, notification_key),
            INDEX idx_user_hidden (user_id, is_hidden, updated_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )


def _parse_datetime_value(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    text = str(value or '').strip()
    if not text:
        return datetime.min
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
    return datetime.min


def _format_agent_datetime(value: datetime) -> str:
    return value.strftime('%Y-%m-%d %H:%M:%S')


def _agent_review_lifecycle(row: Dict[str, Any], scene: str) -> Dict[str, Any]:
    status = str(row.get("status") or "").strip().lower()
    review_action = str(row.get("reviewAction") or "").strip().lower()
    if review_action == "acknowledged":
        review_status = "reviewed"
    elif review_action == "dismissed":
        review_status = "dismissed"
    elif review_action == "needs_review":
        review_status = "needs_review"
    elif status in {"queued", "running"}:
        review_status = "in_progress"
    elif status in {"failed", "cancelled"}:
        review_status = status
    else:
        review_status = "pending_review"

    base_time = _parse_datetime_value(row.get("finishedAt") or row.get("updatedAt") or row.get("createdAt"))
    sla_hours = int(AGENT_REVIEW_SLA_HOURS.get(scene, 12))
    deadline_at = None
    overdue = False
    if base_time != datetime.min:
        deadline = base_time + timedelta(hours=sla_hours)
        deadline_at = _format_agent_datetime(deadline)
        overdue = review_status in {"pending_review", "needs_review"} and datetime.now() > deadline

    return {
        "reviewStatus": review_status,
        "reviewAction": review_action or None,
        "reviewedAt": row.get("reviewedAt"),
        "reviewedBy": row.get("reviewedBy"),
        "reviewDeadlineAt": deadline_at,
        "reviewOverdue": overdue,
        "reviewSlaHours": sla_hours,
    }


def _is_active_agent_review_risk(event: Dict[str, Any]) -> bool:
    status = str(event.get("reviewStatus") or "").strip().lower()
    return status not in {"reviewed", "dismissed", "cancelled", "failed"}


def _agent_review_status_label(status: str) -> str:
    return {
        "reviewed": "已确认",
        "dismissed": "已忽略",
        "needs_review": "需复核",
        "in_progress": "处理中",
        "pending_review": "待复核",
        "failed": "失败",
        "cancelled": "已取消",
    }.get(str(status or "").strip().lower(), "已更新")


def _agent_review_notification_prefix(lifecycle: Dict[str, Any]) -> str:
    status = str(lifecycle.get("reviewStatus") or "").strip().lower()
    if bool(lifecycle.get("reviewOverdue")):
        return "复核已超期"
    return {
        "reviewed": "已人工确认",
        "dismissed": "已忽略",
        "needs_review": "需要人工复核",
        "pending_review": "待人工复核",
        "in_progress": "复核处理中",
        "failed": "复核失败",
        "cancelled": "复核已取消",
    }.get(status, "")


def _get_notification_states(user_id: int, keys: List[str]) -> Dict[str, Dict[str, Any]]:
    _ensure_notification_state_table()
    filtered_keys = [key for key in keys if key]
    if not filtered_keys:
        return {}

    placeholders = ', '.join(['%s'] * len(filtered_keys))
    rows = DbUtil.fetch_all(
        f"""
        SELECT notification_key, is_read, is_hidden
        FROM user_notification_states
        WHERE user_id = %s AND notification_key IN ({placeholders})
        """,
        tuple([user_id] + filtered_keys)
    ) or []
    return {
        row.get("notification_key"): {
            "is_read": bool(row.get("is_read")),
            "is_hidden": bool(row.get("is_hidden"))
        }
        for row in rows
    }


def _upsert_notification_states(user_id: int, keys: List[str], is_read: Optional[bool] = None, is_hidden: Optional[bool] = None) -> int:
    _ensure_notification_state_table()
    affected = 0
    for key in keys:
        if not key:
            continue
        DbUtil.execute_sql(
            """
            INSERT INTO user_notification_states (user_id, notification_key, is_read, is_hidden)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                is_read = COALESCE(VALUES(is_read), is_read),
                is_hidden = COALESCE(VALUES(is_hidden), is_hidden),
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                user_id,
                key,
                1 if is_read else 0 if is_read is not None else None,
                1 if is_hidden else 0 if is_hidden is not None else None
            )
        )
        affected += 1
    return affected


def _list_recent_live_orders(user_id: int, limit: int = 12) -> List[Dict[str, Any]]:
    manager = get_broker_manager()
    rows: List[Dict[str, Any]] = []
    for account in manager.list_accounts(user_id=user_id) or []:
        try:
            broker = manager.get_broker(int(account.get("id")), user_id=user_id)
            if not broker:
                continue
            if not broker.is_connected and not broker.connect():
                continue
            for order in (broker.get_orders() or [])[: max(limit, 12)]:
                created_at = getattr(order, 'create_time', None)
                if hasattr(created_at, 'strftime'):
                    created_at_text = created_at.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    created_at_text = str(created_at or '')
                action = str(getattr(order, 'action', '') or '').upper()
                quantity = float(getattr(order, 'quantity', 0) or 0)
                status_label = _format_order_status_label(getattr(order, 'status', None))
                rows.append({
                    "notificationKey": f"trade:{account.get('id')}:{getattr(order, 'order_id', '') or getattr(order, 'symbol', '')}:{created_at_text}",
                    "type": "trade",
                    "title": f"{getattr(order, 'symbol', '')} {('买入' if action == 'BUY' else '卖出' if action == 'SELL' else '订单更新')}",
                    "message": f"状态 {status_label}，数量 {quantity:.2f}，价格 {float(getattr(order, 'price', 0) or 0):.2f}",
                    "time": created_at_text,
                    "route": "/orders"
                })
        except Exception as exc:
            print(f"⚠️ [API] 获取订单通知失败: user={user_id} account={account.get('id')} error={exc}")
            continue

    rows.sort(key=lambda item: _parse_datetime_value(item.get("time")), reverse=True)
    return rows[:limit]


def _list_recent_order_projection_notifications(user_id: int, limit: int = 12) -> List[Dict[str, Any]]:
    if not _table_exists("trade_order_projections"):
        return []

    rows = DbUtil.fetch_all(
        """
        SELECT account_id, order_id, symbol, action, quantity, price, status,
               COALESCE(updated_at, created_at) AS event_time
        FROM trade_order_projections
        WHERE user_id = %s
        ORDER BY COALESCE(updated_at, created_at) DESC, order_id DESC
        LIMIT %s
        """,
        (user_id, max(1, min(int(limit or 12), 100))),
    ) or []

    items: List[Dict[str, Any]] = []
    for row in rows:
        event_time = row.get("event_time")
        if hasattr(event_time, "strftime"):
            event_time_text = event_time.strftime('%Y-%m-%d %H:%M:%S')
        else:
            event_time_text = str(event_time or '')
        action = str(row.get("action") or "").upper()
        quantity = float(row.get("quantity") or 0)
        price = float(row.get("price") or 0)
        items.append({
            "notificationKey": f"trade:{row.get('account_id')}:{row.get('order_id') or row.get('symbol')}:{event_time_text}",
            "type": "trade",
            "title": f"{row.get('symbol') or ''} {('买入' if action == 'BUY' else '卖出' if action == 'SELL' else '订单更新')}",
            "message": f"状态 {_format_order_status_label(row.get('status'))}，数量 {quantity:.2f}，价格 {price:.2f}",
            "time": event_time_text,
            "route": "/orders",
        })

    return items


def _collect_notifications(user_id: int, limit: int = 50, notification_type: str = '') -> List[Dict[str, Any]]:
    notification_type = str(notification_type or '').strip().lower()
    items: List[Dict[str, Any]] = []

    if notification_type in {'', 'risk'}:
        for alert in StrategyMonitorService.get_alerts(user_id=user_id, limit=max(limit, 20)):
            items.append({
                "notificationKey": f"risk:{alert.get('id')}",
                "type": "risk",
                "title": alert.get("strategyName") or "风险预警",
                "message": alert.get("message") or '',
                "symbol": alert.get("symbol"),
                "time": alert.get("createdAt"),
                "route": "/risk"
            })
        if notification_type == 'risk':
            items.extend(_collect_agent_review_notifications(
                user_id=user_id,
                limit=max(8, limit // 2),
                risk_only=True,
            ))

    if notification_type in {'', 'trade'}:
        trade_limit = max(8, limit // 2)
        trade_items = _list_recent_order_projection_notifications(user_id=user_id, limit=trade_limit)
        if not trade_items:
            trade_items = _list_recent_live_orders(user_id=user_id, limit=trade_limit)
        items.extend(trade_items)

    if notification_type in {'', 'agent', 'agent-review', 'agent-risk'}:
        items.extend(_collect_agent_review_notifications(
            user_id=user_id,
            limit=max(8, limit // 2),
            risk_only=notification_type == 'agent-risk',
        ))

    if notification_type in {'', 'system'}:
        login_rows = DbUtil.fetch_all(
            """
            SELECT id, login_time, login_status, fail_reason
            FROM login_logs
            WHERE user_id = %s
            ORDER BY id DESC
            LIMIT %s
            """,
            (user_id, max(8, limit // 2))
        ) or []
        for row in login_rows:
            login_time = row.get("login_time").strftime('%Y-%m-%d %H:%M:%S') if row.get("login_time") else None
            success = (row.get("login_status") or '') == 'success'
            items.append({
                "notificationKey": f"system:login:{row.get('id')}",
                "type": "system",
                "title": "登录记录",
                "message": "登录成功" if success else f"登录失败：{row.get('fail_reason') or '未知原因'}",
                "time": login_time,
                "route": "/profile"
            })

    items.sort(key=lambda item: _parse_datetime_value(item.get("time")), reverse=True)
    states = _get_notification_states(user_id, [item.get("notificationKey") for item in items])

    visible_items = []
    for item in items:
        state = states.get(item.get("notificationKey"), {})
        if state.get("is_hidden"):
            continue
        visible_items.append({
            **item,
            "id": item.get("notificationKey"),
            "read": bool(state.get("is_read")),
            "notificationKey": item.get("notificationKey")
        })
        if len(visible_items) >= limit:
            break
    return visible_items


def _collect_agent_review_notifications(user_id: int, limit: int = 20, risk_only: bool = False) -> List[Dict[str, Any]]:
    try:
        rows = AgentRunService.list_recent_runs(user_id=user_id, limit=max(1, min(int(limit or 20), 40)), use_primary=True)
    except Exception as exc:
        print(f"⚠️ [API] 获取 Agent 复核通知失败: user={user_id} error={exc}")
        return []

    items: List[Dict[str, Any]] = []
    for row in rows:
        run_id = row.get('runId') or row.get('run_id') or row.get('id')
        if not run_id:
            continue

        scene = str(row.get("scene") or "").strip()
        if scene not in AGENT_REVIEW_SCENE_LABELS:
            continue

        result = row.get("resultSummary") if isinstance(row.get("resultSummary"), dict) else {}
        status = str(row.get("status") or "").strip().lower()
        summary = str(result.get("summary") or row.get("error_summary") or row.get("errorSummary") or "").strip()
        if not summary:
            summary = "Agent 复核已生成，请进入任务中心查看结构化信号、风险和建议。"

        review_count = len(result.get("reviewAdvice") or result.get("review_advice") or [])
        risk_count = len(result.get("riskFlags") or result.get("risk_flags") or [])
        if risk_only and risk_count <= 0:
            continue
        extra_parts = []
        if review_count:
            extra_parts.append(f"{review_count} 条建议")
        if risk_count:
            extra_parts.append(f"{risk_count} 条风险")
        if extra_parts:
            summary = f"{summary}（{'，'.join(extra_parts)}）"

        route_query = urlencode({"agentRunId": str(run_id), "scene": scene})
        item_type = "agent-risk" if risk_count else "agent"
        lifecycle = _agent_review_lifecycle(row, scene)
        review_status_label = _agent_review_status_label(str(lifecycle.get("reviewStatus") or ""))
        lifecycle_prefix = _agent_review_notification_prefix(lifecycle)
        if lifecycle_prefix:
            summary = f"{lifecycle_prefix}：{summary}"
        items.append({
            "notificationKey": f"agent:{run_id}",
            "type": item_type,
            "title": f"{AGENT_REVIEW_SCENE_LABELS[scene]} {review_status_label}",
            "message": summary[:500],
            "time": row.get("finishedAt") or row.get("updatedAt") or row.get("createdAt"),
            "route": f"/scheduler-center?{route_query}",
            "runId": run_id,
            "run_id": run_id,
            "scene": scene,
            "riskCount": risk_count,
            "reviewCount": review_count,
            **lifecycle,
        })

    return items[:limit]


# ========== 股票池相关接口 ==========

@data_bp.route('/api/stock_pool', methods=['GET'])
@login_required
def get_stock_pool():
    """获取股票池列表 - 支持A股、美股、港股"""
    try:
        MarketUniverseSync.ensure_schema()
        user_id = request.user_id
        market = request.args.get('market', 'all')
        search = request.args.get('search', '')
        group_id = request.args.get('group_id', '')
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', 10))
        
        stocks: List[Dict[str, Any]] = []
        for table_config in _iter_stock_pool_tables(market):
            try:
                stocks.extend(_fetch_stock_pool_rows(table_config, user_id, search=search, group_id=group_id))
            except Exception as exc:
                print(f"❌ [API] 从 {table_config['table']} 获取失败: {exc}")

        deduped: Dict[str, Dict[str, Any]] = {}
        for stock in stocks:
            existing = deduped.get(stock["symbol"])
            if existing is None:
                deduped[stock["symbol"]] = stock
                continue
            if stock.get("type") == "etf" and existing.get("type") != "etf":
                deduped[stock["symbol"]] = stock

        unique_stocks = list(deduped.values())
        
        # 计算统计数据
        total = len(unique_stocks)
        stats = _build_stock_pool_stats(user_id=user_id, group_id=group_id)
        stats["filtered_total"] = total
        
        # 分页
        start = (page - 1) * page_size
        end = start + page_size
        paginated_stocks = unique_stocks[start:end]
        
        return jsonify({
            "success": True,
            "stocks": paginated_stocks,
            "total": total,
            "page": page,
            "page_size": page_size,
            "stats": stats
        })
    except Exception as e:
        print(f"❌ [API] 获取股票池失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@data_bp.route('/api/stock_pool/sync_universe', methods=['POST'])
@login_required
@admin_required
def sync_stock_universe():
    """同步全量市场基础行情到数据库。"""
    try:
        payload = request.get_json(silent=True) or {}
        markets = payload.get('markets') or ['US', 'HK', 'CN']
        if isinstance(markets, str):
            markets = [markets]

        result = MarketUniverseSync.sync_markets(markets=markets, user_id=request.user_id)
        message = "市场全量数据同步完成"
        if result.get("warning_count"):
            message = "市场数据已同步，部分外部数据源使用降级数据"
        return jsonify({
            "success": True,
            "message": message,
            "data": result
        })
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as e:
        print(f"❌ [API] 全量同步市场数据失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@data_bp.route('/api/stock_groups', methods=['GET'])
@login_required
def get_stock_groups():
    """获取股票分组列表"""
    try:
        user_id = request.user_id
        market = request.args.get('market', 'all')
        
        where_clause = "WHERE is_active = 1 AND user_id = %s"
        params = [user_id]
        
        if market != 'all':
            where_clause += " AND market = %s"
            params.append(market)
        
        sql = f"""
            SELECT id, market, name, color, sort_order, is_default 
            FROM stock_groups 
            {where_clause}
            ORDER BY market, sort_order
        """
        results = DbUtil.query_all(sql, tuple(params))
        
        groups = []
        for row in results:
            groups.append({
                "id": row[0],
                "market": row[1],
                "name": row[2],
                "color": row[3],
                "sort_order": row[4],
                "is_default": row[5]
            })
        
        return jsonify({
            "success": True,
            "data": groups
        })
    except Exception as e:
        print(f"❌ [API] 获取股票分组失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@data_bp.route('/api/stock_groups', methods=['POST'])
@login_required
def create_stock_group():
    """创建股票分组"""
    try:
        user_id = request.user_id
        data = request.json
        
        market = data.get('market')
        name = data.get('name')
        color = data.get('color', '#667eea')
        
        if not market or not name:
            return jsonify({"success": False, "error": "市场和名称不能为空"}), 400
        
        sql = """
            INSERT INTO stock_groups (user_id, market, name, color)
            VALUES (%s, %s, %s, %s)
        """
        DbUtil.execute_sql(sql, (user_id, market, name, color))
        
        return jsonify({"success": True, "message": "创建成功"})
    except Exception as e:
        print(f"❌ [API] 创建股票分组失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@data_bp.route('/api/stock_groups/<int:group_id>', methods=['PUT'])
@login_required
def update_stock_group(group_id):
    """更新股票分组"""
    try:
        data = request.json
        name = data.get('name')
        color = data.get('color')
        
        sql = """
            UPDATE stock_groups 
            SET name = %s, color = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """
        DbUtil.execute_sql(sql, (name, color, group_id))
        
        return jsonify({"success": True, "message": "更新成功"})
    except Exception as e:
        print(f"❌ [API] 更新股票分组失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@data_bp.route('/api/stock_groups/<int:group_id>', methods=['DELETE'])
@login_required
def delete_stock_group(group_id):
    """删除股票分组"""
    try:
        # 软删除
        sql = "UPDATE stock_groups SET is_active = 0 WHERE id = %s"
        DbUtil.execute_sql(sql, (group_id,))
        
        return jsonify({"success": True, "message": "删除成功"})
    except Exception as e:
        print(f"❌ [API] 删除股票分组失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@data_bp.route('/api/stock_pool/group', methods=['PUT'])
@login_required
def update_stock_group_assignment():
    """更新股票分组"""
    try:
        MarketUniverseSync.ensure_schema()
        data = request.json
        symbols = data.get('symbols', [])
        group_id = data.get('group_id')
        market = data.get('market', 'US')
        asset_type = data.get('type', 'stock')
        
        if not symbols:
            return jsonify({"success": False, "error": "股票代码不能为空"}), 400
        
        table = _resolve_stock_pool_table(market, asset_type)['table']
        
        # 批量更新分组
        for symbol in symbols:
            sql = f"UPDATE {table} SET group_id = %s WHERE symbol = %s"
            DbUtil.execute_sql(sql, (group_id, symbol))
        
        return jsonify({"success": True, "message": f"成功更新 {len(symbols)} 只股票的分组"})
    except Exception as e:
        print(f"❌ [API] 更新股票分组失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@data_bp.route('/api/stock_pool/broker', methods=['PUT'])
@login_required
def update_stock_broker():
    """更新股票关联的券商账户"""
    try:
        MarketUniverseSync.ensure_schema()
        data = request.json
        symbols = data.get('symbols', [])
        broker_account_id = data.get('broker_account_id')
        market = data.get('market', 'US')
        asset_type = data.get('type', 'stock')
        
        if not symbols:
            return jsonify({"success": False, "error": "股票代码不能为空"}), 400
        
        table = _resolve_stock_pool_table(market, asset_type)['table']
        
        # 批量更新券商账户
        for symbol in symbols:
            sql = f"UPDATE {table} SET broker_account_id = %s WHERE symbol = %s"
            DbUtil.execute_sql(sql, (broker_account_id, symbol))
        
        return jsonify({"success": True, "message": f"成功更新 {len(symbols)} 只股票的券商账户"})
    except Exception as e:
        print(f"❌ [API] 更新股票券商账户失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@data_bp.route('/api/stock_pool', methods=['POST'])
@login_required
def add_stock_to_pool():
    """添加股票到股票池"""
    try:
        MarketUniverseSync.ensure_schema()
        user_id = request.user_id
        data = request.json
        symbol = data.get('symbol')
        name = data.get('name', '')
        market = data.get('market', 'US')
        asset_type = data.get('type', 'stock')
        group_id = data.get('group_id')
        broker_account_id = data.get('broker_account_id')
        
        if not symbol:
            return jsonify({"success": False, "error": "股票代码不能为空"}), 400
        
        table_config = _resolve_stock_pool_table(market, asset_type)
        table_name = table_config['table']
        name_field = table_config['name_field']
        category_field = table_config['category_field']

        sql = f"""
            INSERT INTO {table_name} (
                symbol, {name_field}, market, {category_field}, user_id, group_id, broker_account_id, is_active
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, 1)
            ON DUPLICATE KEY UPDATE
            {name_field} = VALUES({name_field}),
            market = VALUES(market),
            user_id = VALUES(user_id),
            group_id = VALUES(group_id),
            broker_account_id = VALUES(broker_account_id),
            is_active = 1
        """
        DbUtil.execute_sql(
            sql,
            (
                symbol,
                name or symbol,
                table_config['market'],
                data.get('category', ''),
                user_id,
                group_id,
                broker_account_id
            )
        )
        
        return jsonify({"success": True, "message": "添加成功"})
    except Exception as e:
        print(f"❌ [API] 添加股票失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@data_bp.route('/api/stock_pool/<symbol>', methods=['DELETE'])
@login_required
def remove_stock_from_pool(symbol):
    """从股票池移除股票（软删除）"""
    try:
        MarketUniverseSync.ensure_schema()
        market = request.args.get('market', 'US')
        asset_type = request.args.get('type', 'stock')
        table = _resolve_stock_pool_table(market, asset_type)['table']
        
        # 软删除
        sql = f"UPDATE {table} SET is_active = 0 WHERE symbol = %s"
        DbUtil.execute_sql(sql, (symbol,))
        
        return jsonify({"success": True, "message": "删除成功"})
    except Exception as e:
        print(f"❌ [API] 删除股票失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@data_bp.route('/api/stocks', methods=['GET'])
@login_required
def get_stocks():
    """获取股票列表（简化版）"""
    try:
        MarketUniverseSync.ensure_schema()
        market = request.args.get('market', 'all')
        search = request.args.get('search', '')
        user_id = request.user_id
        stocks = []
        for table_config in _iter_stock_pool_tables(market):
            try:
                rows = _fetch_stock_pool_rows(table_config, user_id, search=search)
                stocks.extend({
                    "symbol": row["symbol"],
                    "name": row["name"],
                    "market": row["market"],
                    "type": row["type"]
                } for row in rows[:50])
            except Exception as exc:
                print(f"❌ [API] 从 {table_config['table']} 获取失败: {exc}")

        deduped = {}
        for stock in stocks:
            existing = deduped.get(stock["symbol"])
            if existing is None or stock.get("type") == "etf":
                deduped[stock["symbol"]] = stock

        unique_stocks = list(deduped.values())[:50]
        
        return jsonify({
            "success": True,
            "stocks": unique_stocks
        })
    except Exception as e:
        print(f"❌ [API] 获取股票列表失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@data_bp.route('/api/stock_quote/<symbol>', methods=['GET'])
@login_required
def get_stock_quote(symbol):
    """获取单个股票实时行情"""
    try:
        from utils.MonitorLink import MonitorLink
        from utils.DbUtil import DbUtil
        from core.broker.LongbridgeAPI import LongbridgeAPI
        from core.broker.TigerBrokerAPI import TigerBrokerAPI
        
        market = request.args.get('market', 'US')
        account_id = request.args.get('account_id')
        
        MonitorLink.log(f"📊 [股票行情] 获取 {symbol} ({market}) 行情")
        
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
        quotes = api.get_quote([symbol])
        quote = quotes.get(symbol)
        
        if not quote:
            return jsonify({"success": False, "error": "无法获取股票行情数据"}), 400
        
        # 获取价格数据
        current_price = quote.last_price if hasattr(quote, 'last_price') else 0
        prev_close = quote.prev_close if hasattr(quote, 'prev_close') else current_price
        open_price = quote.open if hasattr(quote, 'open') else prev_close
        high = quote.high if hasattr(quote, 'high') else current_price
        low = quote.low if hasattr(quote, 'low') else current_price
        volume = quote.volume if hasattr(quote, 'volume') else 0
        turnover = quote.turnover if hasattr(quote, 'turnover') else current_price * volume
        
        change = current_price - prev_close
        change_percent = (change / prev_close * 100) if prev_close > 0 else 0
        
        stock_data = {
            "symbol": symbol,
            "name": symbol,
            "price": current_price,
            "change": change,
            "change_percent": change_percent,
            "open": open_price,
            "high": high,
            "low": low,
            "volume": volume,
            "turnover": turnover
        }
        
        MonitorLink.log(f"✅ [股票行情] {symbol} 价格: {current_price}, 涨跌: {change_percent:.2f}%")
        
        return jsonify({
            "success": True,
            "data": stock_data
        })
    except Exception as e:
        print(f"❌ [API] 获取股票行情失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@data_bp.route('/api/stock_quotes', methods=['POST'])
@login_required
def get_stock_quotes():
    """获取股票实时行情"""
    try:
        data = request.get_json(silent=True) or {}
        symbols = data.get('symbols', [])
        broker_account_id = data.get('broker_account_id')
        
        if not symbols:
            return jsonify({"success": False, "error": "股票代码不能为空"}), 400

        live_quotes = _fetch_live_quotes(symbols, user_id=request.user_id, account_id=int(broker_account_id) if broker_account_id else None)
        quotes = []
        for symbol in symbols:
            normalized_symbol = _normalize_market_symbol(symbol)
            snapshot = _lookup_universe_snapshot(normalized_symbol)
            quote = live_quotes.get(normalized_symbol) or {}
            last_price = float(quote.get("last_price") or 0)
            change_percent = quote.get("change_percent")
            prev_close = float(quote.get("prev_close") or 0)
            change = quote.get("change")
            if change is None:
                change = (last_price - prev_close) if prev_close else (
                    last_price * float(change_percent or 0) / 100 if last_price else 0
                )
            quotes.append({
                "symbol": normalized_symbol,
                "name": snapshot.get("name") or normalized_symbol,
                "market": snapshot.get("market"),
                "type": snapshot.get("type"),
                "price": round(last_price, 4) if last_price else None,
                "change": round(float(change or 0), 4) if last_price else None,
                "change_percent": round(float(change_percent or 0), 4) if change_percent is not None else None,
                "volume": int(quote.get("volume") or 0) if quote.get("volume") is not None else None,
                "market_cap": snapshot.get("market_cap"),
                "pe": snapshot.get("pe"),
                "pb": snapshot.get("pb"),
                "quote_source": "longbridge-live" if quote else "pending",
                "quoteReady": bool(quote)
            })

        return jsonify({
            "success": True,
            "data": quotes
        })
    except Exception as e:
        print(f"❌ [API] 获取股票行情失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@data_bp.route('/api/stock_search', methods=['GET'])
@login_required
def search_stock():
    """搜索股票（通过SDK查询）"""
    try:
        keyword = request.args.get('keyword', '')
        market = request.args.get('market', 'US')
        limit = int(request.args.get('limit', 20) or 20)
        
        if not keyword:
            return jsonify({"success": False, "error": "搜索关键词不能为空"}), 400

        results = _search_universe(keyword=keyword, market=market, limit=max(5, min(limit, 50)))
        
        return jsonify({
            "success": True,
            "data": results
        })
    except Exception as e:
        print(f"❌ [API] 搜索股票失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ========== Dashboard页面需要的接口 ==========

@data_bp.route('/api/account_info', methods=['GET'])
@login_required
def get_account_info():
    """获取账户信息 - 从券商实时获取"""
    try:
        _, summary, _ = _load_realtime_account_state(_parse_account_id(), user_id=request.user_id)
        payload = {"success": True}
        payload.update(summary)
        return jsonify(payload)
    except Exception as e:
        print(f"❌ [API] 获取账户信息失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@data_bp.route('/api/asset_trend', methods=['GET'])
@login_required
def get_asset_trend():
    """获取资产趋势数据"""
    try:
        days = int(request.args.get('days', 30))

        results = DbUtil.get_asset_trend(days=days, user_id=request.user_id)
        data = []
        for row in results:
            data.append({
                "date": row.get('trend_date').strftime('%Y-%m-%d') if row.get('trend_date') else '',
                "total_assets": float(row.get('total_assets') or 0),
                "market_value": float(row.get('market_value') or 0)
            })
        
        return jsonify({
            "success": True,
            "data": data
        })
    except Exception as e:
        print(f"❌ [API] 获取资产趋势失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@data_bp.route('/api/scan_history', methods=['GET'])
@login_required
def get_scan_history():
    """获取扫描历史记录"""
    try:
        limit = int(request.args.get('limit', 50))
        
        # 从系统日志中获取扫描记录
        sql = """
            SELECT log_content, created_at
            FROM system_logs
            WHERE log_content LIKE %s
            ORDER BY id DESC
            LIMIT %s
        """
        results = DbUtil.query_all(sql, ('[扫描]%%', limit))
        
        data = []
        for row in results:
            data.append({
                "content": row[0].replace('[扫描]', '').strip() if row[0] else '',
                "time": row[1].strftime('%H:%M:%S') if row[1] else ''
            })
        
        return jsonify({
            "success": True,
            "data": data
        })
    except Exception as e:
        print(f"❌ [API] 获取扫描历史失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@data_bp.route('/api/ai_decisions', methods=['GET'])
@login_required
def get_ai_decisions():
    """获取AI决策记录"""
    try:
        limit = int(request.args.get('limit', 50))
        
        # 从系统日志中获取AI决策记录
        sql = """
            SELECT log_content, created_at
            FROM system_logs
            WHERE log_content LIKE %s
            ORDER BY id DESC
            LIMIT %s
        """
        results = DbUtil.query_all(sql, ('[AI决策]%%', limit))
        
        data = []
        for row in results:
            content = row[0] if row[0] else ''
            # 解析日志内容
            data.append({
                "symbol": "",
                "decision": "hold",
                "decisionText": "持有",
                "score": 0,
                "time": row[1].strftime('%H:%M:%S') if row[1] else ''
            })
        
        return jsonify({
            "success": True,
            "data": data
        })
    except Exception as e:
        print(f"❌ [API] 获取AI决策失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@data_bp.route('/api/market_status', methods=['GET'])
def get_market_status():
    """获取市场状态（美股、A股、港股）"""
    try:
        from datetime import datetime, timedelta
        import pytz
        
        def get_market_info(timezone_str, open_hour, open_minute, close_hour, close_minute, market_name):
            """获取市场信息"""
            tz = pytz.timezone(timezone_str)
            now = datetime.now(tz)
            current_time = now.strftime('%H:%M:%S')
            
            # 判断是否为工作日
            weekday = now.weekday()
            is_weekday = weekday < 5  # 周一到周五
            
            # 判断市场状态
            current_minutes = now.hour * 60 + now.minute
            open_minutes = open_hour * 60 + open_minute
            close_minutes = close_hour * 60 + close_minute
            
            if is_weekday and open_minutes <= current_minutes < close_minutes:
                status = 'open'
                status_text = '交易中'
            else:
                status = 'closed'
                status_text = '已休市'
            
            return {
                'status': status,
                'status_text': status_text,
                'current_time': current_time
            }
        
        # 美股 (美东时间 9:30 - 16:00)
        us_info = get_market_info('America/New_York', 9, 30, 16, 0, 'US')
        
        # A股 (北京时间 9:30 - 11:30, 13:00 - 15:00)
        cn_tz = pytz.timezone('Asia/Shanghai')
        cn_now = datetime.now(cn_tz)
        cn_time = cn_now.strftime('%H:%M:%S')
        cn_weekday = cn_now.weekday()
        cn_is_weekday = cn_weekday < 5
        cn_minutes = cn_now.hour * 60 + cn_now.minute
        
        # A股交易时间: 9:30-11:30, 13:00-15:00
        cn_open1 = 9 * 60 + 30
        cn_close1 = 11 * 60 + 30
        cn_open2 = 13 * 60 + 0
        cn_close2 = 15 * 60 + 0
        
        if cn_is_weekday and ((cn_open1 <= cn_minutes < cn_close1) or (cn_open2 <= cn_minutes < cn_close2)):
            cn_status = 'open'
            cn_status_text = '交易中'
        else:
            cn_status = 'closed'
            cn_status_text = '已休市'
        
        cn_info = {
            'status': cn_status,
            'status_text': cn_status_text,
            'current_time': cn_time
        }
        
        # 港股 (香港时间 9:30 - 12:00, 13:00 - 16:00)
        hk_tz = pytz.timezone('Asia/Hong_Kong')
        hk_now = datetime.now(hk_tz)
        hk_time = hk_now.strftime('%H:%M:%S')
        hk_weekday = hk_now.weekday()
        hk_is_weekday = hk_weekday < 5
        hk_minutes = hk_now.hour * 60 + hk_now.minute
        
        # 港股交易时间: 9:30-12:00, 13:00-16:00
        hk_open1 = 9 * 60 + 30
        hk_close1 = 12 * 60 + 0
        hk_open2 = 13 * 60 + 0
        hk_close2 = 16 * 60 + 0
        
        if hk_is_weekday and ((hk_open1 <= hk_minutes < hk_close1) or (hk_open2 <= hk_minutes < hk_close2)):
            hk_status = 'open'
            hk_status_text = '交易中'
        else:
            hk_status = 'closed'
            hk_status_text = '已休市'
        
        hk_info = {
            'status': hk_status,
            'status_text': hk_status_text,
            'current_time': hk_time
        }
        
        return jsonify({
            "success": True,
            "data": {
                "US": us_info,
                "CN": cn_info,
                "HK": hk_info
            }
        })
    except Exception as e:
        print(f"❌ [API] 获取市场状态失败: {e}")
        # 返回默认数据
        return jsonify({
            "success": True,
            "data": {
                "US": {"status": "closed", "status_text": "已休市", "current_time": "--:--:--"},
                "CN": {"status": "closed", "status_text": "已休市", "current_time": "--:--:--"},
                "HK": {"status": "closed", "status_text": "已休市", "current_time": "--:--:--"}
            }
        })


@data_bp.route('/api/dashboard/market-insights', methods=['GET'])
@login_required
def get_dashboard_market_insights():
    """获取仪表盘市场动态，优先读取数据库最新分析快照。"""
    try:
        insights = MarketInsightService.get_latest_snapshots(user_id=request.user_id)
        return jsonify({
            "success": True,
            "data": insights
        })
    except Exception as e:
        print(f"❌ [API] 获取市场动态失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@data_bp.route('/api/dashboard/market-insights/refresh', methods=['POST'])
@login_required
@admin_required
def refresh_dashboard_market_insights():
    """手动刷新市场动态分析并写入数据库。"""
    try:
        result = MarketInsightService.refresh_all_markets(
            user_id=request.user_id,
            source='manual'
        )
        return jsonify({
            "success": True,
            "data": result.get('markets', []),
            "generated_at": result.get('generated_at')
        })
    except Exception as e:
        print(f"❌ [API] 刷新市场动态失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@data_bp.route('/api/holdings', methods=['GET'])
@login_required
def get_holdings():
    """获取持仓列表 - 从券商实时获取"""
    try:
        _, _, positions = _load_realtime_account_state(_parse_account_id(), user_id=request.user_id)
        holdings = [_serialize_realtime_holding(position) for position in positions]

        return jsonify({
            "success": True,
            "data": holdings
        })
    except Exception as e:
        print(f"❌ [API] 获取持仓失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@data_bp.route('/api/get_data')
@login_required
def get_data():
    """获取数据 - 兼容旧接口，图表历史读库，账户/持仓/订单实时读取券商。"""
    try:
        # 获取扫描日志
        scan_logs = DbUtil.fetch_all(
            """
            SELECT id, log_time, content
            FROM scan_logs
            ORDER BY id DESC
            LIMIT 50
            """
        ) or []
        scans = [{
            "time": row.get("log_time").strftime('%Y-%m-%d %H:%M:%S') if row.get("log_time") else '',
            "content": row.get("content") or ''
        } for row in scan_logs]
        
        # 获取AI决策
        ai_logs = DbUtil.query_all(
            """
            SELECT log_content, created_at
            FROM system_logs
            WHERE log_content LIKE %s
            ORDER BY id DESC
            LIMIT 20
            """,
            ('[AI决策]%%',)
        ) or []
        ais = [{
            "time": row[1].strftime('%Y-%m-%d %H:%M:%S') if row[1] else '',
            "symbol": '',
            "gemma": '',
            "llama": '',
            "deepseek": row[0] or '',
            "status": 'info',
            "side": '',
            "detail": row[0] or ''
        } for row in ai_logs]

        account = None
        holdings = []
        orders = []

        try:
            broker, summary, positions = _load_realtime_account_state(_parse_account_id(), user_id=request.user_id)
            account = _build_legacy_account_card(summary)
            holdings = [_serialize_legacy_holding(position) for position in positions]
            orders = [_serialize_legacy_order(order) for order in (broker.get_orders() or [])[:20]]
        except Exception as realtime_error:
            print(f"⚠️ [API] 旧版聚合接口实时数据获取失败: {realtime_error}")

        return jsonify({
            "scans": scans,
            "ais": ais,
            "account": account,
            "holdings": holdings,
            "orders": orders
        })
    except Exception as e:
        print(f"获取数据失败: {e}")
        return jsonify({"scans": [], "ais": [], "account": None, "holdings": [], "orders": []})


# ========== 前端需要的额外接口 ==========

@data_bp.route('/api/dashboard/summary', methods=['GET'])
@login_required
def get_dashboard_summary():
    """获取仪表盘摘要，默认读快照，必要时可通过 refresh=1 强制实时。"""
    try:
        account_id = _parse_account_id()
        if not _should_force_realtime():
            resolved_account_id = _resolve_account_id(account_id, request.user_id)
            snapshot = AccountAssetSnapshotService.get_latest(
                user_id=request.user_id,
                account_id=resolved_account_id,
            ) if resolved_account_id else None
            if snapshot:
                summary = {
                    "account_id": str(resolved_account_id or ''),
                    "currency": snapshot.get("currency") or "USD",
                    "total_assets": float(snapshot.get("totalAssets") or 0),
                    "daily_pnl": float(snapshot.get("todayPnL") or 0),
                    "today_pnl": float(snapshot.get("todayPnL") or 0),
                    "today_pnl_percent": float(snapshot.get("todayPnLPercent") or 0),
                    "pnl_ratio": float(snapshot.get("todayPnLPercent") or 0),
                    "cash": float(snapshot.get("cash") or 0),
                    "market_value": float(snapshot.get("marketValue") or 0),
                    "buying_power": float(snapshot.get("buyingPower") or 0),
                    "maintenance_margin": float(snapshot.get("maintenanceMargin") or 0),
                    "source": "snapshot",
                    "snapshot_at": snapshot.get("snapshotAt"),
                }
                _persist_asset_trend(summary, user_id=request.user_id)
                return jsonify({
                    "success": True,
                    "data": summary
                })

        _, summary, _ = _load_realtime_account_state(account_id, user_id=request.user_id)
        _persist_asset_trend(summary, user_id=request.user_id)
        return jsonify({
            "success": True,
            "data": summary
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@data_bp.route('/api/account/data', methods=['GET'])
@login_required
def get_account_data():
    """兼容旧版前端的实时账户摘要接口。"""
    return get_dashboard_summary()


@data_bp.route('/api/positions', methods=['GET'])
@login_required
def get_positions_realtime():
    """获取持仓列表，默认读快照，必要时可通过 refresh=1 强制实时。"""
    try:
        account_id = _parse_account_id()
        if not _should_force_realtime():
            resolved_account_id = _resolve_account_id(account_id, request.user_id)
            if resolved_account_id:
                snapshot_positions = PositionSnapshotService.get_latest(
                    user_id=request.user_id,
                    account_id=resolved_account_id,
                )
                if snapshot_positions:
                    return jsonify({
                        "success": True,
                        "data": [_serialize_snapshot_position_row(item) for item in snapshot_positions]
                    })

        _, _, positions = _load_realtime_account_state(account_id, user_id=request.user_id)
        if positions and isinstance(positions[0], dict):
            return jsonify({"success": True, "data": positions})

        total_market_value = sum(float(p.market_value or 0) for p in positions)
        result = []
        for p in positions:
            avg_price = float(p.average_cost) if p.average_cost else 0
            current_price = float(p.market_price) if p.market_price else 0
            quantity = float(p.quantity) if p.quantity else 0
            pnl = float(p.unrealized_pnl) if p.unrealized_pnl else 0
            pnl_ratio = ((current_price - avg_price) / avg_price * 100) if avg_price > 0 else 0
            market_value = float(p.market_value) if p.market_value else quantity * current_price
            weight = (market_value / total_market_value * 100) if total_market_value > 0 else 0
            result.append({
                "symbol": p.symbol,
                "name": p.name or p.symbol,
                "quantity": quantity,
                "avg_price": avg_price,
                "avgPrice": avg_price,
                "current_price": current_price,
                "currentPrice": current_price,
                "market_value": market_value,
                "marketValue": market_value,
                "pnl": pnl,
                "pnl_ratio": pnl_ratio,
                "pnlPercent": pnl_ratio,
                "change": current_price - avg_price,
                "changePercent": pnl_ratio,
                "weight": weight,
                "holdDays": 0
            })
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@data_bp.route('/api/market/history', methods=['GET'])
@login_required
def get_market_history():
    """获取数据库中的历史行情数据，必要时触发单标的回补。"""
    try:
        symbol = str(request.args.get('symbol', '')).strip().upper()
        timeframe = str(request.args.get('timeframe', 'daily')).strip().lower()
        limit = int(request.args.get('limit', 180) or 180)
        refresh = str(request.args.get('refresh', '')).strip().lower() in {'1', 'true', 'yes', 'on'}

        if not symbol:
            return jsonify({"success": False, "error": "symbol 不能为空"}), 400

        payload = HistoricalMarketDataService.get_history(
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
            user_id=request.user_id,
            refresh=refresh
        )
        return jsonify({"success": True, "data": payload})
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@data_bp.route('/api/market/history/compare', methods=['GET'])
@login_required
def get_market_history_compare():
    """批量获取多个标的历史行情与指标快照。"""
    try:
        raw_symbols = []
        for raw_value in request.args.getlist('symbols'):
            raw_symbols.extend([item.strip() for item in str(raw_value or '').split(',') if item.strip()])
        if not raw_symbols:
            merged = str(request.args.get('symbols', '') or request.args.get('symbol', '')).strip()
            raw_symbols = [item.strip() for item in merged.split(',') if item.strip()]

        timeframe = str(request.args.get('timeframe', 'daily')).strip().lower()
        limit = int(request.args.get('limit', 180) or 180)
        refresh = str(request.args.get('refresh', '')).strip().lower() in {'1', 'true', 'yes', 'on'}

        payload = HistoricalMarketDataService.get_compare_history(
            symbols=raw_symbols,
            timeframe=timeframe,
            limit=limit,
            user_id=request.user_id,
            refresh=refresh
        )
        return jsonify({"success": True, "data": payload})
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@data_bp.route('/api/market/history/backfill-status', methods=['GET'])
@login_required
def get_market_history_backfill_status():
    """返回历史行情全市场补数覆盖率与任务状态。"""
    try:
        payload = HistoricalMarketDataService.get_backfill_status()
        return jsonify({"success": True, "data": payload})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@data_bp.route('/api/accounts', methods=['GET'])
@login_required
def get_accounts():
    """获取账户列表 - 从券商实时获取"""
    try:
        manager = get_broker_manager()
        accounts = manager.list_accounts(request.user_id)
        result = []
        for account in accounts:
            account_id = account.get('account_id')
            masked_account_id = account_id[:2] + '*' * (len(account_id) - 4) + account_id[-2:] if account_id and len(account_id) > 4 else account_id
            broker_name = account.get('broker_name') or account.get('broker_type') or '账户'
            result.append({
                "id": account.get('id'),
                "account_id": masked_account_id,
                "broker_type": account.get('broker_type'),
                "broker_name": broker_name,
                "name": f"{broker_name} - {masked_account_id or account.get('id')}",
                "is_default": bool(account.get('is_default')),
                "is_active": bool(account.get('is_active'))
            })
        return jsonify({
            "success": True,
            "data": result
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@data_bp.route('/api/strategies', methods=['GET'])
@login_required
def get_strategies():
    """获取策略列表"""
    try:
        result = StrategyMonitorService.list_strategies(user_id=request.user_id)
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@data_bp.route('/api/strategies', methods=['POST'])
@login_required
def create_strategy():
    """创建策略"""
    try:
        strategy = StrategyMonitorService.save_strategy(request.user_id, request.json or {})
        return jsonify({"success": True, "data": strategy})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@data_bp.route('/api/strategies/<int:strategy_id>', methods=['PUT'])
@login_required
def update_strategy(strategy_id):
    """更新策略"""
    try:
        strategy = StrategyMonitorService.save_strategy(request.user_id, request.json or {}, strategy_id=strategy_id)
        return jsonify({"success": True, "data": strategy})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@data_bp.route('/api/strategies/<int:strategy_id>', methods=['DELETE'])
@login_required
def delete_strategy(strategy_id):
    """删除策略"""
    try:
        StrategyMonitorService.delete_strategy(request.user_id, strategy_id)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@data_bp.route('/api/backtest', methods=['GET'])
@login_required
def get_backtest_list():
    """获取回测列表"""
    try:
        result = StrategyMonitorService.list_backtests(user_id=request.user_id)
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@data_bp.route('/api/backtest', methods=['POST'])
@login_required
def run_backtest():
    """运行回测"""
    try:
        result = StrategyMonitorService.run_backtest(request.user_id, request.json or {})
        return jsonify({"success": True, "message": "回测已完成", "data": result})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@data_bp.route('/api/strategy-monitor', methods=['GET'])
@login_required
def get_strategy_monitor_summary():
    """获取策略监控摘要"""
    try:
        account_id = _parse_account_id()
        result = StrategyMonitorService.get_monitor_summary(user_id=request.user_id, account_id=account_id)
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@data_bp.route('/api/strategy-monitor/run', methods=['POST'])
@login_required
def run_strategy_monitor():
    """手动运行持仓监控"""
    try:
        payload = request.get_json(silent=True) or {}
        account_id = payload.get('account_id')
        result = StrategyMonitorService.run_monitor(
            user_id=request.user_id,
            account_id=int(account_id) if account_id else None,
            source='manual'
        )
        return jsonify({"success": True, "data": result})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@data_bp.route('/api/strategy-monitor/alerts', methods=['GET'])
@login_required
def get_strategy_monitor_alerts():
    """获取持仓监控告警"""
    try:
        limit = int(request.args.get('limit', 20))
        result = StrategyMonitorService.get_alerts(user_id=request.user_id, limit=limit)
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@data_bp.route('/api/risk/overview', methods=['GET'])
@login_required
def get_risk_overview():
    """获取风控总览。"""
    try:
        payload = _build_risk_overview(user_id=request.user_id, account_id=_parse_account_id())
        return jsonify({"success": True, "data": payload})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@data_bp.route('/api/risk/limits', methods=['GET'])
@login_required
def get_risk_limits():
    """获取风险限制"""
    try:
        return jsonify({"success": True, "data": _load_risk_limits(request.user_id)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@data_bp.route('/api/risk/limits', methods=['PUT'])
@login_required
def update_risk_limits():
    """更新风险限制"""
    try:
        data = request.get_json(silent=True) or {}
        _ensure_risk_control_tables()
        max_position_size = float(data.get('maxPositionSize', data.get('max_position_size', 35)) or 35)
        max_loss_per_trade = float(data.get('maxLossPerTrade', data.get('max_loss_per_trade', 1000)) or 1000)
        max_daily_loss = float(data.get('maxDailyLoss', data.get('max_daily_loss', 5000)) or 5000)
        max_drawdown = float(data.get('maxDrawdown', data.get('max_drawdown', 20)) or 20)
        volatility_limit = float(data.get('volatilityLimit', data.get('volatility_limit', 50)) or 50)

        DbUtil.execute_sql(
            """
            INSERT INTO user_risk_limits (
                user_id, max_position_size, max_loss_per_trade, max_daily_loss, max_drawdown, volatility_limit
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                max_position_size = VALUES(max_position_size),
                max_loss_per_trade = VALUES(max_loss_per_trade),
                max_daily_loss = VALUES(max_daily_loss),
                max_drawdown = VALUES(max_drawdown),
                volatility_limit = VALUES(volatility_limit),
                updated_at = CURRENT_TIMESTAMP
            """,
            (request.user_id, max_position_size, max_loss_per_trade, max_daily_loss, max_drawdown, volatility_limit)
        )
        return jsonify({"success": True, "data": _load_risk_limits(request.user_id)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@data_bp.route('/api/risk/events', methods=['GET'])
@login_required
def get_risk_events():
    """获取风险事件"""
    try:
        result = _build_risk_overview(user_id=request.user_id, account_id=_parse_account_id())
        return jsonify({"success": True, "data": result.get("events", [])})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@data_bp.route('/api/risk/stoploss', methods=['GET'])
@login_required
def get_stoploss_orders():
    """获取止损单"""
    try:
        result = _load_risk_orders(user_id=request.user_id, order_type='stop_loss', account_id=_parse_account_id())
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@data_bp.route('/api/risk/stoploss', methods=['POST'])
@login_required
def set_stoploss():
    """设置止损单"""
    try:
        data = request.get_json(silent=True) or {}
        _ensure_risk_control_tables()
        symbol = _normalize_market_symbol(data.get('symbol'))
        if not symbol:
            return jsonify({"success": False, "error": "symbol 不能为空"}), 400

        trigger_price = float(data.get('price') or data.get('stopPrice') or 0)
        if trigger_price <= 0:
            return jsonify({"success": False, "error": "止损价必须大于0"}), 400

        quantity = data.get('quantity')
        account_id = data.get('account_id')
        DbUtil.execute_sql(
            """
            INSERT INTO user_risk_orders (user_id, account_id, symbol, order_type, trigger_price, quantity, status, note)
            VALUES (%s, %s, %s, 'stop_loss', %s, %s, 'active', %s)
            ON DUPLICATE KEY UPDATE
                account_id = VALUES(account_id),
                trigger_price = VALUES(trigger_price),
                quantity = VALUES(quantity),
                status = 'active',
                note = VALUES(note),
                updated_at = CURRENT_TIMESTAMP
            """,
            (request.user_id, account_id, symbol, trigger_price, quantity, data.get('note'))
        )
        return jsonify({"success": True, "message": "止损规则已保存"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@data_bp.route('/api/risk/stoploss/cancel', methods=['POST'])
@login_required
def cancel_stoploss():
    """取消止损单"""
    try:
        data = request.get_json(silent=True) or {}
        order_id = int(data.get('order_id') or 0)
        if order_id <= 0:
            return jsonify({"success": False, "error": "order_id 无效"}), 400
        DbUtil.execute_sql(
            """
            UPDATE user_risk_orders
            SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND user_id = %s AND order_type = 'stop_loss'
            """,
            (order_id, request.user_id)
        )
        return jsonify({"success": True, "message": "止损规则已取消"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@data_bp.route('/api/risk/takeprofit', methods=['GET'])
@login_required
def get_takeprofit_orders():
    """获取止盈单"""
    try:
        result = _load_risk_orders(user_id=request.user_id, order_type='take_profit', account_id=_parse_account_id())
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@data_bp.route('/api/risk/takeprofit', methods=['POST'])
@login_required
def set_takeprofit():
    """设置止盈单"""
    try:
        data = request.get_json(silent=True) or {}
        _ensure_risk_control_tables()
        symbol = _normalize_market_symbol(data.get('symbol'))
        if not symbol:
            return jsonify({"success": False, "error": "symbol 不能为空"}), 400

        trigger_price = float(data.get('price') or data.get('profitPrice') or 0)
        if trigger_price <= 0:
            return jsonify({"success": False, "error": "止盈价必须大于0"}), 400

        quantity = data.get('quantity')
        account_id = data.get('account_id')
        DbUtil.execute_sql(
            """
            INSERT INTO user_risk_orders (user_id, account_id, symbol, order_type, trigger_price, quantity, status, note)
            VALUES (%s, %s, %s, 'take_profit', %s, %s, 'active', %s)
            ON DUPLICATE KEY UPDATE
                account_id = VALUES(account_id),
                trigger_price = VALUES(trigger_price),
                quantity = VALUES(quantity),
                status = 'active',
                note = VALUES(note),
                updated_at = CURRENT_TIMESTAMP
            """,
            (request.user_id, account_id, symbol, trigger_price, quantity, data.get('note'))
        )
        return jsonify({"success": True, "message": "止盈规则已保存"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@data_bp.route('/api/risk/takeprofit/cancel', methods=['POST'])
@login_required
def cancel_takeprofit():
    """取消止盈单"""
    try:
        data = request.get_json(silent=True) or {}
        order_id = int(data.get('order_id') or 0)
        if order_id <= 0:
            return jsonify({"success": False, "error": "order_id 无效"}), 400
        DbUtil.execute_sql(
            """
            UPDATE user_risk_orders
            SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND user_id = %s AND order_type = 'take_profit'
            """,
            (order_id, request.user_id)
        )
        return jsonify({"success": True, "message": "止盈规则已取消"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@data_bp.route('/api/notifications', methods=['GET'])
@login_required
def get_notifications():
    """获取当前用户通知中心数据。"""
    try:
        limit = max(10, min(int(request.args.get('limit', 50) or 50), 100))
        notification_type = str(request.args.get('type', '') or '').strip().lower()
        payload = _collect_notifications(user_id=request.user_id, limit=limit, notification_type=notification_type)
        return jsonify({"success": True, "data": payload})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@data_bp.route('/api/notifications/read', methods=['POST'])
@login_required
def read_notification():
    try:
        data = request.get_json(silent=True) or {}
        keys = data.get('keys') if isinstance(data.get('keys'), list) else [data.get('notification_key') or data.get('id')]
        updated = _upsert_notification_states(request.user_id, keys, is_read=True)
        return jsonify({"success": True, "data": {"updated": updated}})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@data_bp.route('/api/notifications/read-all', methods=['POST'])
@login_required
def read_all_notifications():
    try:
        data = request.get_json(silent=True) or {}
        notification_type = str(data.get('type', '') or '').strip().lower()
        items = _collect_notifications(user_id=request.user_id, limit=100, notification_type=notification_type)
        keys = [item.get('notificationKey') for item in items]
        updated = _upsert_notification_states(request.user_id, keys, is_read=True)
        return jsonify({"success": True, "data": {"updated": updated}})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@data_bp.route('/api/notifications/delete', methods=['POST'])
@login_required
def delete_notification():
    try:
        data = request.get_json(silent=True) or {}
        keys = data.get('keys') if isinstance(data.get('keys'), list) else [data.get('notification_key') or data.get('id')]
        updated = _upsert_notification_states(request.user_id, keys, is_hidden=True)
        return jsonify({"success": True, "data": {"updated": updated}})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@data_bp.route('/api/notifications/clear', methods=['POST'])
@login_required
def clear_notifications():
    try:
        data = request.get_json(silent=True) or {}
        notification_type = str(data.get('type', '') or '').strip().lower()
        items = _collect_notifications(user_id=request.user_id, limit=100, notification_type=notification_type)
        keys = [item.get('notificationKey') for item in items]
        updated = _upsert_notification_states(request.user_id, keys, is_hidden=True)
        return jsonify({"success": True, "data": {"updated": updated}})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
