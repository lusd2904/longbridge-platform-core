from __future__ import annotations

from typing import Any, Dict, List, Optional

from utils.DbUtil import DbUtil


WATCHLIST_TABLE = "user_watchlist_stocks"


def _normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper()


def _normalize_text(value: Any, *, upper: bool = False) -> str:
    token = str(value or "").strip()
    return token.upper() if upper else token


def _normalize_asset_type(value: Any) -> str:
    token = str(value or "").strip().lower()
    return token if token in {"stock", "etf"} else ""


def _as_bool(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _quote_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


class WatchlistService:
    @staticmethod
    def ensure_schema() -> None:
        DbUtil.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {WATCHLIST_TABLE} (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                symbol VARCHAR(32) NOT NULL,
                name VARCHAR(255) NOT NULL DEFAULT '',
                market VARCHAR(16) NOT NULL DEFAULT '',
                asset_type VARCHAR(32) NOT NULL DEFAULT 'stock',
                category VARCHAR(255) NOT NULL DEFAULT '',
                scan_before_open TINYINT(1) NOT NULL DEFAULT 1,
                scan_after_close TINYINT(1) NOT NULL DEFAULT 1,
                added_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                last_scan_at TIMESTAMP NULL DEFAULT NULL,
                UNIQUE KEY uniq_user_watchlist_symbol (user_id, symbol),
                KEY idx_user_watchlist_market_type (user_id, market, asset_type),
                KEY idx_user_watchlist_sessions (user_id, scan_before_open, scan_after_close)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )

    @staticmethod
    def list_watchlist(
        *,
        user_id: int,
        market: str = "",
        asset_type: str = "",
        symbol: str = "",
        session_filter: str = "",
    ) -> List[Dict[str, Any]]:
        WatchlistService.ensure_schema()
        where_clauses = ["user_id = %s"]
        params: List[Any] = [int(user_id)]

        market_value = _normalize_text(market, upper=True)
        if market_value:
            where_clauses.append("market = %s")
            params.append(market_value)

        asset_type_value = _normalize_asset_type(asset_type)
        if asset_type_value:
            where_clauses.append("asset_type = %s")
            params.append(asset_type_value)

        symbol_value = _normalize_symbol(symbol)
        if symbol_value:
            where_clauses.append("(symbol LIKE %s OR name LIKE %s)")
            params.extend([f"%{symbol_value}%", f"%{symbol_value}%"])

        session_value = _normalize_text(session_filter).lower()
        if session_value == "before_open":
            where_clauses.append("scan_before_open = 1")
        elif session_value == "after_close":
            where_clauses.append("scan_after_close = 1")

        rows = DbUtil.fetch_all(
            f"""
            SELECT
                symbol,
                name,
                market,
                asset_type,
                category,
                scan_before_open,
                scan_after_close,
                added_at,
                updated_at,
                last_scan_at
            FROM {WATCHLIST_TABLE}
            WHERE {' AND '.join(where_clauses)}
            ORDER BY added_at DESC, symbol ASC
            """,
            tuple(params),
        ) or []
        return [
            {
                "symbol": row.get("symbol"),
                "name": row.get("name") or row.get("symbol"),
                "market": row.get("market"),
                "asset_type": row.get("asset_type") or "stock",
                "type": row.get("asset_type") or "stock",
                "category": row.get("category") or "",
                "scan_before_open": bool(row.get("scan_before_open")),
                "scan_after_close": bool(row.get("scan_after_close")),
                "added_at": row.get("added_at"),
                "updated_at": row.get("updated_at"),
                "last_scan_at": row.get("last_scan_at"),
            }
            for row in rows
        ]

    @staticmethod
    def upsert_watchlist_item(*, user_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        WatchlistService.ensure_schema()
        symbol = _normalize_symbol(payload.get("symbol"))
        if not symbol:
            raise ValueError("股票代码不能为空")

        market = _normalize_text(payload.get("market"), upper=True)
        if not market:
            raise ValueError("market 不能为空")

        asset_type = _normalize_asset_type(payload.get("asset_type") or payload.get("type"))
        if not asset_type:
            asset_type = "stock"

        scan_before_open = _as_bool(
            payload.get("scan_before_open")
            if "scan_before_open" in payload
            else payload.get("scanBeforeOpen", True)
        )
        scan_after_close = _as_bool(
            payload.get("scan_after_close")
            if "scan_after_close" in payload
            else payload.get("scanAfterClose", True)
        )

        DbUtil.execute(
            f"""
            INSERT INTO {WATCHLIST_TABLE} (
                user_id,
                symbol,
                name,
                market,
                asset_type,
                category,
                scan_before_open,
                scan_after_close,
                added_at,
                updated_at,
                last_scan_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, %s)
            ON DUPLICATE KEY UPDATE
                name = VALUES(name),
                market = VALUES(market),
                asset_type = VALUES(asset_type),
                category = VALUES(category),
                scan_before_open = VALUES(scan_before_open),
                scan_after_close = VALUES(scan_after_close),
                updated_at = CURRENT_TIMESTAMP,
                last_scan_at = VALUES(last_scan_at)
            """,
            (
                int(user_id),
                symbol,
                str(payload.get("name") or symbol),
                market,
                asset_type,
                str(payload.get("category") or ""),
                1 if scan_before_open else 0,
                1 if scan_after_close else 0,
                payload.get("last_scan_at"),
            ),
        )
        item = WatchlistService.get_watchlist_item(user_id=int(user_id), symbol=symbol)
        return item or {
            "symbol": symbol,
            "name": str(payload.get("name") or symbol),
            "market": market,
            "asset_type": asset_type,
            "type": asset_type,
            "category": str(payload.get("category") or ""),
            "scan_before_open": scan_before_open,
            "scan_after_close": scan_after_close,
            "added_at": None,
            "updated_at": None,
            "last_scan_at": payload.get("last_scan_at"),
        }

    @staticmethod
    def get_watchlist_item(*, user_id: int, symbol: str) -> Optional[Dict[str, Any]]:
        items = WatchlistService.list_watchlist(user_id=int(user_id), symbol=_normalize_symbol(symbol))
        exact_symbol = _normalize_symbol(symbol)
        for item in items:
            if _normalize_symbol(item.get("symbol")) == exact_symbol:
                return item
        return None

    @staticmethod
    def delete_watchlist_item(*, user_id: int, symbol: str) -> int:
        WatchlistService.ensure_schema()
        normalized_symbol = _normalize_symbol(symbol)
        if not normalized_symbol:
            return 0
        return DbUtil.execute(
            f"DELETE FROM {WATCHLIST_TABLE} WHERE user_id = %s AND symbol = %s",
            (int(user_id), normalized_symbol),
        )

    @staticmethod
    def list_scan_targets(
        *,
        user_id: int,
        market: str = "",
        asset_type: str = "",
        session_filter: str = "",
    ) -> Dict[str, Any]:
        WatchlistService.ensure_schema()
        where_clauses = ["user_id = %s"]
        params: List[Any] = [int(user_id)]

        market_value = _normalize_text(market, upper=True)
        if market_value:
            where_clauses.append("market = %s")
            params.append(market_value)

        asset_type_value = _normalize_asset_type(asset_type)
        if asset_type_value:
            where_clauses.append("asset_type = %s")
            params.append(asset_type_value)

        session_value = _normalize_text(session_filter).lower()
        if session_value == "before_open":
            where_clauses.append("scan_before_open = 1")
        elif session_value == "after_close":
            where_clauses.append("scan_after_close = 1")
        elif session_value in {"all", ""}:
            pass
        else:
            where_clauses.append("(scan_before_open = 1 OR scan_after_close = 1)")

        rows = DbUtil.fetch_all(
            f"""
            SELECT
                symbol,
                name,
                market,
                asset_type,
                category,
                scan_before_open,
                scan_after_close,
                added_at,
                updated_at,
                last_scan_at
            FROM {WATCHLIST_TABLE}
            WHERE {' AND '.join(where_clauses)}
            ORDER BY market ASC, asset_type ASC, added_at DESC, symbol ASC
            """,
            tuple(params),
        ) or []

        items: List[Dict[str, Any]] = []
        for row in rows:
            item = {
                "symbol": row.get("symbol"),
                "name": row.get("name") or row.get("symbol"),
                "market": row.get("market"),
                "asset_type": row.get("asset_type") or "stock",
                "type": row.get("asset_type") or "stock",
                "category": row.get("category") or "",
                "scan_before_open": bool(row.get("scan_before_open")),
                "scan_after_close": bool(row.get("scan_after_close")),
                "added_at": row.get("added_at"),
                "updated_at": row.get("updated_at"),
                "last_scan_at": row.get("last_scan_at"),
            }
            if session_value == "before_open" and not item["scan_before_open"]:
                continue
            if session_value == "after_close" and not item["scan_after_close"]:
                continue
            item["sessions"] = [
                session_name
                for session_name, enabled in (
                    ("before_open", item["scan_before_open"]),
                    ("after_close", item["scan_after_close"]),
                )
                if enabled
            ]
            items.append(item)

        return {
            "items": items,
            "total": len(items),
            "filters": {
                "market": market_value or None,
                "type": asset_type_value or None,
                "session": session_value or "all",
            },
            "markets": sorted({str(item.get("market") or "") for item in items if item.get("market")}),
            "types": sorted({str(item.get("type") or "") for item in items if item.get("type")}),
        }

    @staticmethod
    def ensure_watchlist_join_view() -> None:
        WatchlistService.ensure_schema()
        table_exists = DbUtil.query_one(
            "SELECT 1 FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = %s",
            (WATCHLIST_TABLE,),
        )
        if not table_exists:
            raise RuntimeError(f"{WATCHLIST_TABLE} 表初始化失败")

    @staticmethod
    def build_scan_targets_response(
        *,
        user_id: int,
        market: str = "",
        asset_type: str = "",
        session_filter: str = "",
    ) -> Dict[str, Any]:
        payload = WatchlistService.list_scan_targets(
            user_id=int(user_id),
            market=market,
            asset_type=asset_type,
            session_filter=session_filter,
        )
        return {
            "targets": payload["items"],
            "total": payload["total"],
            "filters": payload["filters"],
            "markets": payload["markets"],
            "types": payload["types"],
            "query": _quote_string(
                f"market={payload['filters']['market'] or 'ALL'},type={payload['filters']['type'] or 'all'},session={payload['filters']['session']}"
            ),
        }
