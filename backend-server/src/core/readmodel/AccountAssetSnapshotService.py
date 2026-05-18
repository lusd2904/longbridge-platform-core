from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.broker.BrokerInterface import get_broker_manager
from utils.DbUtil import DbUtil


class AccountAssetSnapshotService:
    TABLE_NAME = "account_asset_snapshots"

    @classmethod
    def ensure_schema(cls) -> None:
        DbUtil.execute_sql(
            f"""
            CREATE TABLE IF NOT EXISTS {cls.TABLE_NAME} (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                account_id INT NOT NULL,
                broker_type VARCHAR(32) DEFAULT NULL,
                currency VARCHAR(16) DEFAULT 'USD',
                total_assets DECIMAL(18, 4) DEFAULT 0,
                cash DECIMAL(18, 4) DEFAULT 0,
                market_value DECIMAL(18, 4) DEFAULT 0,
                buying_power DECIMAL(18, 4) DEFAULT 0,
                maintenance_margin DECIMAL(18, 4) DEFAULT 0,
                today_pnl DECIMAL(18, 4) DEFAULT 0,
                today_pnl_percent DECIMAL(10, 4) DEFAULT 0,
                snapshot_at DATETIME NOT NULL,
                source VARCHAR(32) DEFAULT 'broker',
                payload_json JSON DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uniq_user_account_snapshot (user_id, account_id, snapshot_at),
                INDEX idx_user_account_time (user_id, account_id, snapshot_at),
                INDEX idx_snapshot_at (snapshot_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )

    @classmethod
    def save_summary(
        cls,
        *,
        user_id: int,
        account_id: int,
        summary: Dict[str, Any],
        broker_type: str = "",
        source: str = "broker",
        snapshot_at: Optional[datetime] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        cls.ensure_schema()
        safe_snapshot_at = snapshot_at or datetime.now()
        DbUtil.execute_sql(
            f"""
            INSERT INTO {cls.TABLE_NAME} (
                user_id, account_id, broker_type, currency, total_assets, cash,
                market_value, buying_power, maintenance_margin, today_pnl, today_pnl_percent,
                snapshot_at, source, payload_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                broker_type = VALUES(broker_type),
                currency = VALUES(currency),
                total_assets = VALUES(total_assets),
                cash = VALUES(cash),
                market_value = VALUES(market_value),
                buying_power = VALUES(buying_power),
                maintenance_margin = VALUES(maintenance_margin),
                today_pnl = VALUES(today_pnl),
                today_pnl_percent = VALUES(today_pnl_percent),
                source = VALUES(source),
                payload_json = VALUES(payload_json)
            """,
            (
                int(user_id),
                int(account_id),
                str(broker_type or "").strip() or None,
                str(summary.get("currency") or "USD"),
                float(summary.get("total_assets") or summary.get("totalAssets") or 0),
                float(summary.get("cash") or 0),
                float(summary.get("market_value") or summary.get("marketValue") or 0),
                float(summary.get("buying_power") or summary.get("buyingPower") or summary.get("cash") or 0),
                float(summary.get("maintenance_margin") or summary.get("maintenanceMargin") or 0),
                float(summary.get("today_pnl") or summary.get("todayPnL") or summary.get("daily_pnl") or 0),
                float(summary.get("today_pnl_percent") or summary.get("todayPnLPercent") or summary.get("pnl_ratio") or 0),
                safe_snapshot_at,
                source,
                json.dumps(payload or summary, ensure_ascii=False),
            ),
        )

    @classmethod
    def refresh_for_account(cls, user_id: int, account_id: int, source: str = "broker") -> Dict[str, Any]:
        cls.ensure_schema()
        manager = get_broker_manager()
        account = next(
            (item for item in (manager.list_accounts(user_id=user_id) or []) if int(item.get("id") or 0) == int(account_id)),
            None,
        )
        if not account:
            raise ValueError("券商账户不存在")

        broker = manager.get_broker(int(account_id), user_id=user_id)
        if not broker:
            raise ValueError("券商实例不可用")

        connected = getattr(broker, "is_connected", False)
        if not (connected() if callable(connected) else bool(connected)):
            if not broker.connect():
                raise ValueError("券商连接失败")

        account_info = broker.get_account_info()
        summary = {
            "account_id": getattr(account_info, "account_id", "") or account.get("account_id") or "",
            "currency": getattr(account_info, "currency", "") or "USD",
            "total_assets": float(getattr(account_info, "total_equity", 0) or 0),
            "cash": float(getattr(account_info, "cash", 0) or 0),
            "market_value": float(getattr(account_info, "market_value", 0) or 0),
            "buying_power": float(getattr(account_info, "buying_power", 0) or 0),
            "maintenance_margin": float(getattr(account_info, "maintenance_margin", 0) or 0),
            "today_pnl": 0.0,
            "today_pnl_percent": 0.0,
        }
        cls.save_summary(
            user_id=user_id,
            account_id=int(account_id),
            summary=summary,
            broker_type=str(account.get("broker_type") or ""),
            source=source,
            payload={"account": account, "accountInfo": summary},
        )
        saved = cls.get_latest(user_id=user_id, account_id=int(account_id), use_primary=True) or {}
        return saved

    @classmethod
    def refresh_for_user(cls, user_id: int, source: str = "broker") -> List[Dict[str, Any]]:
        snapshots: List[Dict[str, Any]] = []
        manager = get_broker_manager()
        for account in manager.list_accounts(user_id=user_id) or []:
            account_id = int(account.get("id") or 0)
            if account_id <= 0:
                continue
            try:
                snapshots.append(cls.refresh_for_account(user_id=user_id, account_id=account_id, source=source))
            except Exception:
                continue
        return snapshots

    @classmethod
    def get_latest(
        cls,
        *,
        user_id: int,
        account_id: Optional[int] = None,
        use_primary: bool = False,
    ) -> Optional[Dict[str, Any]]:
        cls.ensure_schema()
        fetch_one = DbUtil.fetch_one_primary if use_primary else DbUtil.fetch_one
        if account_id is not None:
            row = fetch_one(
                f"""
                SELECT *
                FROM {cls.TABLE_NAME}
                WHERE user_id = %s AND account_id = %s
                ORDER BY snapshot_at DESC, id DESC
                LIMIT 1
                """,
                (int(user_id), int(account_id)),
            )
            return cls._normalize_row(row) if row else None

        rows = cls.list_latest_for_user(user_id=user_id, use_primary=use_primary)
        return rows[0] if rows else None

    @classmethod
    def list_latest_for_user(cls, *, user_id: int, use_primary: bool = False) -> List[Dict[str, Any]]:
        cls.ensure_schema()
        fetch_all = DbUtil.fetch_all_primary if use_primary else DbUtil.fetch_all
        rows = fetch_all(
            f"""
            SELECT snap.*
            FROM {cls.TABLE_NAME} snap
            INNER JOIN (
                SELECT account_id, MAX(snapshot_at) AS max_snapshot_at
                FROM {cls.TABLE_NAME}
                WHERE user_id = %s
                GROUP BY account_id
            ) latest
              ON latest.account_id = snap.account_id
             AND latest.max_snapshot_at = snap.snapshot_at
            WHERE snap.user_id = %s
            ORDER BY snap.snapshot_at DESC, snap.id DESC
            """,
            (int(user_id), int(user_id)),
        ) or []

        deduped: Dict[int, Dict[str, Any]] = {}
        for row in rows:
            account_id = int(row.get("account_id") or 0)
            if account_id <= 0 or account_id in deduped:
                continue
            deduped[account_id] = cls._normalize_row(row)
        return list(deduped.values())

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
            "brokerType": row.get("broker_type") or "",
            "currency": row.get("currency") or "USD",
            "totalAssets": float(row.get("total_assets") or 0),
            "cash": float(row.get("cash") or 0),
            "marketValue": float(row.get("market_value") or 0),
            "buyingPower": float(row.get("buying_power") or 0),
            "maintenanceMargin": float(row.get("maintenance_margin") or 0),
            "todayPnL": float(row.get("today_pnl") or 0),
            "todayPnLPercent": float(row.get("today_pnl_percent") or 0),
            "snapshotAt": snapshot_at.strftime("%Y-%m-%d %H:%M:%S") if snapshot_at else None,
            "source": row.get("source") or "broker",
            "payload": payload,
        }

