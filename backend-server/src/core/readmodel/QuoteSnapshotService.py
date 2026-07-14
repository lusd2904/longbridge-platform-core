from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import Any

from core.analysis.HistoricalMarketDataService import HistoricalMarketDataService
from utils.DbUtil import DbUtil


class QuoteSnapshotService:
    TABLE_NAME = "quote_snapshots"

    @classmethod
    def ensure_schema(cls) -> None:
        DbUtil.execute_sql(
            f"""
            CREATE TABLE IF NOT EXISTS {cls.TABLE_NAME} (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                symbol VARCHAR(32) NOT NULL,
                market VARCHAR(10) NOT NULL,
                last_price DECIMAL(18, 4) DEFAULT NULL,
                prev_close DECIMAL(18, 4) DEFAULT NULL,
                open_price DECIMAL(18, 4) DEFAULT NULL,
                high_price DECIMAL(18, 4) DEFAULT NULL,
                low_price DECIMAL(18, 4) DEFAULT NULL,
                volume BIGINT DEFAULT NULL,
                turnover DECIMAL(20, 4) DEFAULT NULL,
                change_amount DECIMAL(18, 4) DEFAULT NULL,
                change_percent DECIMAL(12, 4) DEFAULT NULL,
                snapshot_at DATETIME NOT NULL,
                source VARCHAR(32) DEFAULT 'scheduler',
                payload_json JSON DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uniq_symbol_snapshot (symbol, snapshot_at),
                INDEX idx_symbol_snapshot (symbol, snapshot_at),
                INDEX idx_market_snapshot (market, snapshot_at),
                INDEX idx_snapshot_at (snapshot_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )

    @classmethod
    def save_quotes(
        cls,
        quotes: Iterable[dict[str, Any]],
        *,
        source: str = "scheduler",
        snapshot_at: datetime | None = None,
    ) -> int:
        cls.ensure_schema()
        safe_snapshot_at = snapshot_at or datetime.now()
        saved = 0
        for raw in quotes or []:
            normalized = cls._normalize_quote(raw, snapshot_at=safe_snapshot_at, source=source)
            if not normalized:
                continue
            DbUtil.execute_sql(
                f"""
                INSERT INTO {cls.TABLE_NAME} (
                    symbol, market, last_price, prev_close, open_price, high_price, low_price,
                    volume, turnover, change_amount, change_percent, snapshot_at, source, payload_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    market = VALUES(market),
                    last_price = VALUES(last_price),
                    prev_close = VALUES(prev_close),
                    open_price = VALUES(open_price),
                    high_price = VALUES(high_price),
                    low_price = VALUES(low_price),
                    volume = VALUES(volume),
                    turnover = VALUES(turnover),
                    change_amount = VALUES(change_amount),
                    change_percent = VALUES(change_percent),
                    source = VALUES(source),
                    payload_json = VALUES(payload_json)
                """,
                (
                    normalized["symbol"],
                    normalized["market"],
                    normalized["lastPrice"],
                    normalized["prevClose"],
                    normalized["open"],
                    normalized["high"],
                    normalized["low"],
                    normalized["volume"],
                    normalized["turnover"],
                    normalized["change"],
                    normalized["changePercent"],
                    normalized["snapshotAt"],
                    normalized["source"],
                    json.dumps(normalized["payload"], ensure_ascii=False),
                ),
            )
            saved += 1
        return saved

    @classmethod
    def get_latest(
        cls,
        symbol: str,
        *,
        use_primary: bool = False,
        max_age_minutes: int | None = None,
    ) -> dict[str, Any] | None:
        snapshot_map = cls.get_latest_map([symbol], use_primary=use_primary, max_age_minutes=max_age_minutes)
        normalized_symbol = HistoricalMarketDataService.normalize_symbol(symbol)
        return snapshot_map.get(normalized_symbol)

    @classmethod
    def get_latest_map(
        cls,
        symbols: Iterable[str],
        *,
        use_primary: bool = False,
        max_age_minutes: int | None = None,
    ) -> dict[str, dict[str, Any]]:
        cls.ensure_schema()
        normalized_symbols: list[str] = []
        for raw_symbol in symbols or []:
            symbol = HistoricalMarketDataService.normalize_symbol(raw_symbol)
            if symbol and symbol not in normalized_symbols:
                normalized_symbols.append(symbol)
        if not normalized_symbols:
            return {}

        cutoff = None
        if max_age_minutes is not None:
            cutoff = datetime.now() - timedelta(minutes=max(1, int(max_age_minutes)))

        placeholders = ", ".join(["%s"] * len(normalized_symbols))
        fetch_all = DbUtil.fetch_all_primary if use_primary else DbUtil.fetch_all
        params: list[Any] = list(normalized_symbols)
        latest_filters = [f"symbol IN ({placeholders})"]
        outer_filters = [f"snap.symbol IN ({placeholders})"]
        outer_params: list[Any] = list(normalized_symbols)
        if cutoff is not None:
            latest_filters.append("snapshot_at >= %s")
            params.append(cutoff)
            outer_filters.append("snap.snapshot_at >= %s")
            outer_params.append(cutoff)

        rows = (
            fetch_all(
                f"""
            SELECT snap.*
            FROM {cls.TABLE_NAME} snap
            INNER JOIN (
                SELECT symbol, MAX(snapshot_at) AS max_snapshot_at
                FROM {cls.TABLE_NAME}
                WHERE {' AND '.join(latest_filters)}
                GROUP BY symbol
            ) latest
              ON latest.symbol = snap.symbol
             AND latest.max_snapshot_at = snap.snapshot_at
            WHERE {' AND '.join(outer_filters)}
            ORDER BY snap.snapshot_at DESC, snap.id DESC
            """,
                tuple(params + outer_params),
            )
            or []
        )

        deduped: dict[str, dict[str, Any]] = {}
        for row in rows:
            symbol = HistoricalMarketDataService.normalize_symbol(row.get("symbol"))
            if not symbol or symbol in deduped:
                continue
            deduped[symbol] = cls._normalize_row(row)
        return deduped

    @classmethod
    def _normalize_quote(
        cls,
        quote: dict[str, Any],
        *,
        snapshot_at: datetime,
        source: str,
    ) -> dict[str, Any] | None:
        symbol = HistoricalMarketDataService.normalize_symbol(quote.get("symbol"))
        if not symbol:
            return None

        market = str(quote.get("market") or HistoricalMarketDataService.detect_market(symbol)).strip().upper()
        last_price = cls._safe_float(quote.get("last_price"), quote.get("lastPrice"), quote.get("price"))
        prev_close = cls._safe_float(quote.get("prev_close"), quote.get("prevClose"))
        open_price = cls._safe_float(quote.get("open"), quote.get("open_price"), default=prev_close)
        high_price = cls._safe_float(quote.get("high"), quote.get("high_price"), default=last_price)
        low_price = cls._safe_float(quote.get("low"), quote.get("low_price"), default=last_price)
        turnover = cls._safe_float(quote.get("turnover"))

        change = cls._safe_float(quote.get("change"), quote.get("change_amount"))
        if change is None and last_price is not None and prev_close:
            change = last_price - prev_close

        change_percent = cls._safe_float(quote.get("change_percent"), quote.get("changePercent"))
        if change_percent is None and change is not None and prev_close:
            change_percent = (change / prev_close) * 100

        volume_value = quote.get("volume")
        volume = int(volume_value or 0) if volume_value not in (None, "") else None

        payload = {
            **quote,
            "symbol": symbol,
            "market": market,
            "last_price": last_price,
            "prev_close": prev_close,
            "open": open_price,
            "high": high_price,
            "low": low_price,
            "volume": volume,
            "turnover": turnover,
            "change": change,
            "change_percent": change_percent,
            "snapshot_at": snapshot_at.strftime("%Y-%m-%d %H:%M:%S"),
            "source": source,
        }
        return {
            "symbol": symbol,
            "market": market,
            "lastPrice": last_price,
            "prevClose": prev_close,
            "open": open_price,
            "high": high_price,
            "low": low_price,
            "volume": volume,
            "turnover": turnover,
            "change": change,
            "changePercent": change_percent,
            "snapshotAt": snapshot_at,
            "source": source,
            "payload": payload,
        }

    @classmethod
    def _normalize_row(cls, row: dict[str, Any]) -> dict[str, Any]:
        payload = row.get("payload_json")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                payload = {}
        elif not isinstance(payload, dict):
            payload = {}

        snapshot_at = row.get("snapshot_at")
        last_price = cls._safe_float(row.get("last_price"))
        prev_close = cls._safe_float(row.get("prev_close"))
        open_price = cls._safe_float(row.get("open_price"))
        high_price = cls._safe_float(row.get("high_price"))
        low_price = cls._safe_float(row.get("low_price"))
        change = cls._safe_float(row.get("change_amount"))
        change_percent = cls._safe_float(row.get("change_percent"))
        volume_raw = row.get("volume")
        volume = int(volume_raw or 0) if volume_raw is not None else None
        turnover = cls._safe_float(row.get("turnover"))

        return {
            "symbol": row.get("symbol"),
            "market": row.get("market"),
            "price": last_price,
            "last_price": last_price,
            "lastPrice": last_price,
            "prev_close": prev_close,
            "prevClose": prev_close,
            "open": open_price,
            "high": high_price,
            "low": low_price,
            "volume": volume,
            "turnover": turnover,
            "change": change,
            "changeAmount": change,
            "change_percent": change_percent,
            "changePercent": change_percent,
            "snapshot_at": snapshot_at.strftime("%Y-%m-%d %H:%M:%S")
            if hasattr(snapshot_at, "strftime")
            else snapshot_at,
            "snapshotAt": snapshot_at.strftime("%Y-%m-%d %H:%M:%S")
            if hasattr(snapshot_at, "strftime")
            else snapshot_at,
            "source": row.get("source") or "snapshot",
            "quoteReady": bool(last_price or prev_close or change_percent is not None or volume is not None),
            "payload": payload,
        }

    @staticmethod
    def _safe_float(*values: Any, default: float | None = None) -> float | None:
        for value in values:
            if value in (None, ""):
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return default
