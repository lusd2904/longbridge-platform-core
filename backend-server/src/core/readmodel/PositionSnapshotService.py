from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.broker.BrokerInterface import get_broker_manager
from utils.DbUtil import DbUtil


class PositionSnapshotService:
    TABLE_NAME = "position_snapshots"
    EMPTY_SYMBOL = "__EMPTY__"

    @classmethod
    def ensure_schema(cls) -> None:
        DbUtil.execute_sql(
            f"""
            CREATE TABLE IF NOT EXISTS {cls.TABLE_NAME} (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                account_id INT NOT NULL,
                symbol VARCHAR(32) NOT NULL,
                market VARCHAR(10) NOT NULL,
                name VARCHAR(160) DEFAULT NULL,
                quantity DECIMAL(18, 4) DEFAULT 0,
                available_quantity DECIMAL(18, 4) DEFAULT 0,
                avg_price DECIMAL(18, 4) DEFAULT 0,
                current_price DECIMAL(18, 4) DEFAULT 0,
                market_value DECIMAL(18, 4) DEFAULT 0,
                pnl DECIMAL(18, 4) DEFAULT 0,
                pnl_percent DECIMAL(10, 4) DEFAULT 0,
                weight DECIMAL(10, 4) DEFAULT 0,
                snapshot_at DATETIME NOT NULL,
                source VARCHAR(32) DEFAULT 'broker',
                payload_json JSON DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uniq_account_symbol_snapshot (account_id, symbol, snapshot_at),
                INDEX idx_user_account_time (user_id, account_id, snapshot_at),
                INDEX idx_symbol_time (symbol, snapshot_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )

    @classmethod
    def replace_account_positions(
        cls,
        *,
        user_id: int,
        account_id: int,
        positions: List[Dict[str, Any]],
        source: str = "broker",
        snapshot_at: Optional[datetime] = None,
    ) -> None:
        cls.ensure_schema()
        safe_snapshot_at = snapshot_at or datetime.now()
        safe_positions = list(positions or [])
        if not safe_positions:
            safe_positions = [
                {
                    "symbol": cls.EMPTY_SYMBOL,
                    "market": "NA",
                    "name": "EMPTY",
                    "quantity": 0,
                    "availableQuantity": 0,
                    "avgPrice": 0,
                    "currentPrice": 0,
                    "marketValue": 0,
                    "pnl": 0,
                    "pnlPercent": 0,
                    "weight": 0,
                }
            ]
        total_market_value = sum(float(item.get("marketValue") or item.get("market_value") or 0) for item in safe_positions)
        for item in safe_positions:
            symbol = str(item.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            market_value = float(item.get("marketValue") or item.get("market_value") or 0)
            DbUtil.execute_sql(
                f"""
                INSERT INTO {cls.TABLE_NAME} (
                    user_id, account_id, symbol, market, name, quantity, available_quantity,
                    avg_price, current_price, market_value, pnl, pnl_percent, weight,
                    snapshot_at, source, payload_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    market = VALUES(market),
                    name = VALUES(name),
                    quantity = VALUES(quantity),
                    available_quantity = VALUES(available_quantity),
                    avg_price = VALUES(avg_price),
                    current_price = VALUES(current_price),
                    market_value = VALUES(market_value),
                    pnl = VALUES(pnl),
                    pnl_percent = VALUES(pnl_percent),
                    weight = VALUES(weight),
                    source = VALUES(source),
                    payload_json = VALUES(payload_json)
                """,
                (
                    int(user_id),
                    int(account_id),
                    symbol,
                    cls._detect_market(symbol, item.get("market")),
                    str(item.get("name") or symbol)[:160],
                    float(item.get("quantity") or 0),
                    float(item.get("availableQuantity") or item.get("available_quantity") or item.get("quantity") or 0),
                    float(item.get("avgPrice") or item.get("avg_price") or item.get("average_cost") or 0),
                    float(item.get("currentPrice") or item.get("current_price") or item.get("market_price") or 0),
                    market_value,
                    float(item.get("pnl") or item.get("unrealized_pnl") or 0),
                    float(item.get("pnlPercent") or item.get("pnl_percent") or 0),
                    round((market_value / total_market_value * 100), 4) if total_market_value > 0 else float(item.get("weight") or 0),
                    safe_snapshot_at,
                    source,
                    json.dumps(item, ensure_ascii=False),
                ),
            )

    @classmethod
    def refresh_for_account(cls, user_id: int, account_id: int, source: str = "broker") -> List[Dict[str, Any]]:
        cls.ensure_schema()
        manager = get_broker_manager()
        broker = manager.get_broker(int(account_id), user_id=user_id)
        if not broker:
            raise ValueError("券商实例不可用")

        connected = getattr(broker, "is_connected", False)
        if not (connected() if callable(connected) else bool(connected)):
            if not broker.connect():
                raise ValueError("券商连接失败")

        snapshot_at = datetime.now()
        live_positions = broker.get_positions() or []
        serialized = [
            {
                "symbol": getattr(item, "symbol", ""),
                "name": getattr(item, "name", "") or getattr(item, "symbol", ""),
                "quantity": float(getattr(item, "quantity", 0) or 0),
                "availableQuantity": float(getattr(item, "quantity", 0) or 0),
                "avgPrice": float(getattr(item, "average_cost", 0) or 0),
                "currentPrice": float(getattr(item, "market_price", 0) or 0),
                "marketValue": float(getattr(item, "market_value", 0) or 0),
                "pnl": float(getattr(item, "unrealized_pnl", 0) or 0),
                "pnlPercent": cls._pnl_percent(
                    float(getattr(item, "average_cost", 0) or 0),
                    float(getattr(item, "market_price", 0) or 0),
                ),
            }
            for item in live_positions
        ]
        cls.replace_account_positions(
            user_id=user_id,
            account_id=int(account_id),
            positions=serialized,
            source=source,
            snapshot_at=snapshot_at,
        )
        return cls.get_latest(user_id=user_id, account_id=int(account_id), use_primary=True)

    @classmethod
    def refresh_for_user(cls, user_id: int, source: str = "broker") -> Dict[int, List[Dict[str, Any]]]:
        payload: Dict[int, List[Dict[str, Any]]] = {}
        manager = get_broker_manager()
        for account in manager.list_accounts(user_id=user_id) or []:
            account_id = int(account.get("id") or 0)
            if account_id <= 0:
                continue
            try:
                payload[account_id] = cls.refresh_for_account(user_id=user_id, account_id=account_id, source=source)
            except Exception:
                continue
        return payload

    @classmethod
    def get_latest(
        cls,
        *,
        user_id: int,
        account_id: int,
        use_primary: bool = False,
    ) -> List[Dict[str, Any]]:
        cls.ensure_schema()
        fetch_one = DbUtil.fetch_one_primary if use_primary else DbUtil.fetch_one
        fetch_all = DbUtil.fetch_all_primary if use_primary else DbUtil.fetch_all
        latest = fetch_one(
            f"""
            SELECT snapshot_at
            FROM {cls.TABLE_NAME}
            WHERE user_id = %s AND account_id = %s
            ORDER BY snapshot_at DESC, id DESC
            LIMIT 1
            """,
            (int(user_id), int(account_id)),
        )
        if not latest or not latest.get("snapshot_at"):
            return []

        rows = fetch_all(
            f"""
            SELECT *
            FROM {cls.TABLE_NAME}
            WHERE user_id = %s AND account_id = %s AND snapshot_at = %s
            ORDER BY market_value DESC, symbol ASC
            """,
            (int(user_id), int(account_id), latest.get("snapshot_at")),
        ) or []
        return [
            cls._normalize_row(row)
            for row in rows
            if str(row.get("symbol") or "").strip().upper() != cls.EMPTY_SYMBOL
        ]

    @staticmethod
    def _detect_market(symbol: str, provided: Any = None) -> str:
        market = str(provided or "").strip().upper()
        if market:
            return market
        normalized = str(symbol or "").strip().upper()
        if normalized.endswith(".HK"):
            return "HK"
        if normalized.endswith(".SH") or normalized.endswith(".SZ") or normalized.endswith(".BJ"):
            return "CN"
        return "US"

    @staticmethod
    def _pnl_percent(avg_price: float, current_price: float) -> float:
        if avg_price <= 0:
            return 0.0
        return round(((current_price - avg_price) / avg_price) * 100, 4)

    @classmethod
    def _normalize_row(cls, row: Dict[str, Any]) -> Dict[str, Any]:
        payload = row.get("payload_json")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                payload = {}
        elif not isinstance(payload, dict):
            payload = {}

        snapshot_at = row.get("snapshot_at")
        return {
            "userId": int(row.get("user_id") or 0),
            "accountId": int(row.get("account_id") or 0),
            "symbol": row.get("symbol") or "",
            "market": row.get("market") or "",
            "name": row.get("name") or row.get("symbol") or "",
            "quantity": float(row.get("quantity") or 0),
            "availableQuantity": float(row.get("available_quantity") or 0),
            "avgPrice": float(row.get("avg_price") or 0),
            "currentPrice": float(row.get("current_price") or 0),
            "marketValue": float(row.get("market_value") or 0),
            "pnl": float(row.get("pnl") or 0),
            "pnlPercent": float(row.get("pnl_percent") or 0),
            "weight": float(row.get("weight") or 0),
            "snapshotAt": snapshot_at.strftime("%Y-%m-%d %H:%M:%S") if snapshot_at else None,
            "source": row.get("source") or "broker",
            "payload": payload,
        }
