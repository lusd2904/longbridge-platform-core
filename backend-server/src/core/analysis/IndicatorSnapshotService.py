from __future__ import annotations

import json
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional

from core.analysis.HistoricalMarketDataService import HistoricalMarketDataService
from utils.DbUtil import DbUtil
from utils.IndicatorUtil import IndicatorUtil
from utils.IndicatorUtilEnhanced import IndicatorUtilEnhanced


class IndicatorSnapshotService:
    TABLE_NAME = "symbol_indicator_snapshots"

    @classmethod
    def ensure_schema(cls) -> None:
        DbUtil.execute_sql(
            f"""
            CREATE TABLE IF NOT EXISTS {cls.TABLE_NAME} (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                symbol VARCHAR(32) NOT NULL,
                market VARCHAR(10) NOT NULL,
                timeframe VARCHAR(16) NOT NULL,
                trade_date DATE NOT NULL,
                close_price DECIMAL(18, 4) DEFAULT 0,
                change_percent DECIMAL(12, 4) DEFAULT 0,
                rsi DECIMAL(12, 4) DEFAULT 0,
                macd_diff DECIMAL(18, 6) DEFAULT 0,
                macd_dea DECIMAL(18, 6) DEFAULT 0,
                macd_hist DECIMAL(18, 6) DEFAULT 0,
                boll_mid DECIMAL(18, 4) DEFAULT 0,
                boll_upper DECIMAL(18, 4) DEFAULT 0,
                boll_lower DECIMAL(18, 4) DEFAULT 0,
                ema_short DECIMAL(18, 4) DEFAULT 0,
                ema_long DECIMAL(18, 4) DEFAULT 0,
                sma_mid DECIMAL(18, 4) DEFAULT 0,
                sma_long DECIMAL(18, 4) DEFAULT 0,
                atr DECIMAL(18, 4) DEFAULT 0,
                k_value DECIMAL(12, 4) DEFAULT 0,
                d_value DECIMAL(12, 4) DEFAULT 0,
                j_value DECIMAL(12, 4) DEFAULT 0,
                obv DECIMAL(24, 4) DEFAULT 0,
                roc DECIMAL(12, 4) DEFAULT 0,
                cci DECIMAL(12, 4) DEFAULT 0,
                support_price DECIMAL(18, 4) DEFAULT 0,
                resistance_price DECIMAL(18, 4) DEFAULT 0,
                trend_label VARCHAR(32) DEFAULT NULL,
                momentum_score DECIMAL(12, 4) DEFAULT 0,
                fundamentals_json JSON DEFAULT NULL,
                meta_json JSON DEFAULT NULL,
                generated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uniq_symbol_tf_date (symbol, timeframe, trade_date),
                INDEX idx_symbol_tf_generated (symbol, timeframe, generated_at),
                INDEX idx_market_tf_date (market, timeframe, trade_date)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )

    @classmethod
    def refresh_symbol(
        cls,
        symbol: str,
        user_id: int = 1,
        timeframes: Iterable[str] = ("daily", "weekly", "monthly", "quarterly", "yearly")
    ) -> Dict[str, object]:
        cls.ensure_schema()
        normalized_symbol = HistoricalMarketDataService.normalize_symbol(symbol)
        series = cls._load_price_series(normalized_symbol, user_id=user_id, limit=520)
        if len(series) < 30:
            raise ValueError(f"{normalized_symbol} 历史数据不足，无法生成技术快照")

        saved = []
        fundamentals = cls._load_fundamentals(normalized_symbol)
        for timeframe in timeframes:
            safe_timeframe = str(timeframe or "daily").strip().lower()
            if safe_timeframe not in {"daily", "weekly", "monthly", "quarterly", "yearly"}:
                continue

            tf_series = cls._aggregate_series(series, safe_timeframe)
            minimum_points = 20 if safe_timeframe != "yearly" else 2
            if len(tf_series) < minimum_points:
                continue
            snapshot = cls._build_snapshot(normalized_symbol, safe_timeframe, tf_series, fundamentals)
            cls._save_snapshot(snapshot)
            saved.append(snapshot)

        return {
            "symbol": normalized_symbol,
            "saved": len(saved),
            "snapshots": saved
        }

    @classmethod
    def refresh_universe(
        cls,
        markets: Optional[Iterable[str]] = None,
        user_id: int = 1,
        batch_size: int = 1500,
        cursor: int = 0
    ) -> Dict[str, object]:
        cls.ensure_schema()
        safe_cursor = max(0, int(cursor or 0))
        safe_batch_size = max(50, int(batch_size or 1500))
        symbols = cls._collect_universe_symbols(markets=markets, limit=safe_batch_size, offset=safe_cursor)

        processed = 0
        failed = []
        for item in symbols:
            try:
                cls.refresh_symbol(item["symbol"], user_id=user_id)
                processed += 1
            except Exception as exc:
                failed.append({"symbol": item["symbol"], "error": str(exc)[:180]})

        next_cursor = safe_cursor + len(symbols)
        return {
            "processed": processed,
            "failed": failed[:20],
            "cursor": safe_cursor,
            "nextCursor": next_cursor,
            "hasMore": len(symbols) == safe_batch_size
        }

    @classmethod
    def get_latest_snapshots(cls, symbol: str) -> Dict[str, Dict[str, object]]:
        cls.ensure_schema()
        normalized_symbol = HistoricalMarketDataService.normalize_symbol(symbol)
        # Each refresh writes at most one row per timeframe, so we only need a
        # bounded window of the newest rows to reconstruct the latest snapshot set.
        rows = DbUtil.fetch_all(
            f"""
            SELECT *
            FROM {cls.TABLE_NAME}
            WHERE symbol = %s
            ORDER BY generated_at DESC, id DESC
            LIMIT %s
            """,
            (normalized_symbol, 32)
        )
        latest: Dict[str, Dict[str, object]] = {}
        for row in rows:
            timeframe = row.get("timeframe")
            if timeframe in latest:
                continue
            latest[timeframe] = cls._normalize_snapshot_row(row)
            if len(latest) >= 5:
                break
        return latest

    @classmethod
    def get_snapshot(cls, symbol: str, timeframe: str = "daily", user_id: int = 1) -> Dict[str, object]:
        cls.ensure_schema()
        normalized_symbol = HistoricalMarketDataService.normalize_symbol(symbol)
        safe_timeframe = str(timeframe or "daily").strip().lower()
        if safe_timeframe not in {"daily", "weekly", "monthly", "quarterly", "yearly"}:
            raise ValueError("timeframe 仅支持 daily / weekly / monthly / quarterly / yearly")

        row = DbUtil.fetch_one(
            f"""
            SELECT *
            FROM {cls.TABLE_NAME}
            WHERE symbol = %s AND timeframe = %s
            ORDER BY generated_at DESC, id DESC
            LIMIT 1
            """,
            (normalized_symbol, safe_timeframe)
        )
        if row:
            return cls._normalize_snapshot_row(row)

        try:
            series = cls._load_price_series(normalized_symbol, user_id=user_id, limit=760)
        except Exception:
            return {}
        tf_series = cls._aggregate_series(series, safe_timeframe)
        minimum_points = 20 if safe_timeframe != "yearly" else 2
        if len(tf_series) < minimum_points:
            return {}

        snapshot = cls._build_snapshot(
            normalized_symbol,
            safe_timeframe,
            tf_series,
            cls._load_fundamentals(normalized_symbol)
        )
        cls._save_snapshot(snapshot)
        return snapshot

    @classmethod
    def get_symbol_overview(cls, symbol: str, user_id: int = 1, allow_refresh: bool = True) -> Dict[str, object]:
        normalized_symbol = HistoricalMarketDataService.normalize_symbol(symbol)
        latest = cls.get_latest_snapshots(normalized_symbol)
        if not latest and allow_refresh:
            try:
                cls.refresh_symbol(normalized_symbol, user_id=user_id)
            except Exception:
                pass
            latest = cls.get_latest_snapshots(normalized_symbol)

        fundamentals = cls._load_fundamentals(normalized_symbol)
        return {
            "symbol": normalized_symbol,
            "market": HistoricalMarketDataService.detect_market(normalized_symbol),
            "fundamentals": fundamentals,
            "snapshots": latest
        }

    @classmethod
    def _load_price_series(cls, symbol: str, user_id: int = 1, limit: int = 520) -> List[Dict[str, object]]:
        base_series = HistoricalMarketDataService._query_daily_series(symbol, limit)
        if len(base_series) >= 60:
            return base_series

        if HistoricalMarketDataService.detect_market(symbol) == "US":
            fallback_series = cls._query_us_history_table(symbol, limit)
            if len(fallback_series) >= len(base_series):
                return fallback_series

        try:
            HistoricalMarketDataService.ensure_symbol_history(symbol, user_id=user_id, min_points=min(limit, 180), refresh=False)
        except Exception:
            return base_series
        refreshed = HistoricalMarketDataService._query_daily_series(symbol, limit)
        if len(refreshed) >= len(base_series):
            return refreshed
        return base_series

    @classmethod
    def _query_us_history_table(cls, symbol: str, limit: int) -> List[Dict[str, object]]:
        short_symbol = symbol.split(".")[0]
        rows = DbUtil.fetch_all(
            """
            SELECT trade_date, open_price, high_price, low_price, close_price, volume, change_percent
            FROM us_stock_historical_data
            WHERE symbol = %s
            ORDER BY trade_date DESC
            LIMIT %s
            """,
            (short_symbol, int(limit))
        ) or []

        series = []
        for row in reversed(rows):
            trade_date = row.get("trade_date")
            series.append({
                "date": trade_date.strftime("%Y-%m-%d") if trade_date else "",
                "open": float(row.get("open_price") or 0),
                "high": float(row.get("high_price") or 0),
                "low": float(row.get("low_price") or 0),
                "close": float(row.get("close_price") or 0),
                "volume": int(row.get("volume") or 0),
                "changePercent": float(row.get("change_percent") or 0)
            })
        return series

    @classmethod
    def _aggregate_series(cls, series: List[Dict[str, object]], timeframe: str) -> List[Dict[str, object]]:
        if timeframe == "daily":
            return series
        if timeframe in {"weekly", "monthly"}:
            return HistoricalMarketDataService._aggregate_series(series, timeframe)

        buckets: Dict[str, List[Dict[str, object]]] = {}
        ordered_keys: List[str] = []
        for item in series:
            target_date = datetime.strptime(item["date"], "%Y-%m-%d").date()
            if timeframe == "quarterly":
                quarter = ((target_date.month - 1) // 3) + 1
                bucket_start_month = (quarter - 1) * 3 + 1
                bucket_key = f"{target_date.year}-{bucket_start_month:02d}-01"
            elif timeframe == "yearly":
                bucket_key = f"{target_date.year}-01-01"
            else:
                raise ValueError(f"不支持的周期: {timeframe}")
            if bucket_key not in buckets:
                buckets[bucket_key] = []
                ordered_keys.append(bucket_key)
            buckets[bucket_key].append(item)

        aggregated = []
        for bucket_key in ordered_keys:
            items = buckets[bucket_key]
            aggregated.append({
                "date": bucket_key,
                "open": float(items[0]["open"]),
                "high": max(float(entry["high"]) for entry in items),
                "low": min(float(entry["low"]) for entry in items),
                "close": float(items[-1]["close"]),
                "volume": int(sum(int(entry["volume"]) for entry in items)),
                "turnover": round(sum(float(entry.get("turnover") or 0) for entry in items), 2)
            })
        return aggregated

    @classmethod
    def _build_snapshot(
        cls,
        symbol: str,
        timeframe: str,
        series: List[Dict[str, object]],
        fundamentals: Dict[str, object]
    ) -> Dict[str, object]:
        prices = [float(item.get("close") or 0) for item in series]
        highs = [float(item.get("high") or item.get("close") or 0) for item in series]
        lows = [float(item.get("low") or item.get("close") or 0) for item in series]
        volumes = [int(item.get("volume") or 0) for item in series]

        rsi = IndicatorUtil.calculate_rsi(prices)
        boll_mid, boll_upper, boll_lower = IndicatorUtil.calculate_boll(prices)
        macd_diff, macd_dea, macd_hist = IndicatorUtil.calculate_macd(prices)
        atr = IndicatorUtilEnhanced.calculate_atr(prices, highs, lows)
        ema_short = IndicatorUtilEnhanced.calculate_ema(prices, 12)
        ema_long = IndicatorUtilEnhanced.calculate_ema(prices, 26)
        sma_mid = IndicatorUtilEnhanced.calculate_sma(prices, 20)
        sma_long = IndicatorUtilEnhanced.calculate_sma(prices, 60)
        k_value, d_value, j_value = IndicatorUtilEnhanced.calculate_kdj(prices, highs, lows)
        obv = IndicatorUtilEnhanced.calculate_obv(prices, volumes)
        roc = IndicatorUtilEnhanced.calculate_roc(prices)
        cci = IndicatorUtilEnhanced.calculate_cci(prices, highs, lows)
        support_price, resistance_price = IndicatorUtilEnhanced.calculate_support_resistance(prices)

        latest_close = float(prices[-1] or 0)
        previous_close = float(prices[-2] or latest_close) if len(prices) > 1 else latest_close
        change_percent = ((latest_close - previous_close) / previous_close * 100) if previous_close else 0
        trend_label = cls._trend_label(latest_close, ema_short, ema_long, rsi, roc)
        momentum_score = cls._momentum_score(rsi, macd_hist, roc)
        latest_date = series[-1]["date"]

        return {
            "symbol": symbol,
            "market": HistoricalMarketDataService.detect_market(symbol),
            "timeframe": timeframe,
            "tradeDate": latest_date,
            "closePrice": round(latest_close, 4),
            "changePercent": round(change_percent, 4),
            "rsi": round(rsi, 4),
            "macdDiff": round(macd_diff, 6),
            "macdDea": round(macd_dea, 6),
            "macdHist": round(macd_hist, 6),
            "bollMid": round(boll_mid, 4),
            "bollUpper": round(boll_upper, 4),
            "bollLower": round(boll_lower, 4),
            "emaShort": round(ema_short, 4),
            "emaLong": round(ema_long, 4),
            "smaMid": round(sma_mid, 4),
            "smaLong": round(sma_long, 4),
            "atr": round(atr, 4),
            "kValue": round(k_value, 4),
            "dValue": round(d_value, 4),
            "jValue": round(j_value, 4),
            "obv": round(obv, 4),
            "roc": round(roc, 4),
            "cci": round(cci, 4),
            "supportPrice": round(support_price, 4),
            "resistancePrice": round(resistance_price, 4),
            "trendLabel": trend_label,
            "momentumScore": round(momentum_score, 4),
            "fundamentals": fundamentals,
            "meta": {
                "points": len(series),
                "latestVolume": volumes[-1] if volumes else 0
            }
        }

    @classmethod
    def _save_snapshot(cls, snapshot: Dict[str, object]) -> None:
        DbUtil.execute_sql(
            f"""
            INSERT INTO {cls.TABLE_NAME} (
                symbol, market, timeframe, trade_date, close_price, change_percent, rsi,
                macd_diff, macd_dea, macd_hist, boll_mid, boll_upper, boll_lower,
                ema_short, ema_long, sma_mid, sma_long, atr, k_value, d_value, j_value,
                obv, roc, cci, support_price, resistance_price, trend_label, momentum_score,
                fundamentals_json, meta_json, generated_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
            )
            ON DUPLICATE KEY UPDATE
                close_price = VALUES(close_price),
                change_percent = VALUES(change_percent),
                rsi = VALUES(rsi),
                macd_diff = VALUES(macd_diff),
                macd_dea = VALUES(macd_dea),
                macd_hist = VALUES(macd_hist),
                boll_mid = VALUES(boll_mid),
                boll_upper = VALUES(boll_upper),
                boll_lower = VALUES(boll_lower),
                ema_short = VALUES(ema_short),
                ema_long = VALUES(ema_long),
                sma_mid = VALUES(sma_mid),
                sma_long = VALUES(sma_long),
                atr = VALUES(atr),
                k_value = VALUES(k_value),
                d_value = VALUES(d_value),
                j_value = VALUES(j_value),
                obv = VALUES(obv),
                roc = VALUES(roc),
                cci = VALUES(cci),
                support_price = VALUES(support_price),
                resistance_price = VALUES(resistance_price),
                trend_label = VALUES(trend_label),
                momentum_score = VALUES(momentum_score),
                fundamentals_json = VALUES(fundamentals_json),
                meta_json = VALUES(meta_json),
                generated_at = NOW(),
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                snapshot["symbol"],
                snapshot["market"],
                snapshot["timeframe"],
                snapshot["tradeDate"],
                snapshot["closePrice"],
                snapshot["changePercent"],
                snapshot["rsi"],
                snapshot["macdDiff"],
                snapshot["macdDea"],
                snapshot["macdHist"],
                snapshot["bollMid"],
                snapshot["bollUpper"],
                snapshot["bollLower"],
                snapshot["emaShort"],
                snapshot["emaLong"],
                snapshot["smaMid"],
                snapshot["smaLong"],
                snapshot["atr"],
                snapshot["kValue"],
                snapshot["dValue"],
                snapshot["jValue"],
                snapshot["obv"],
                snapshot["roc"],
                snapshot["cci"],
                snapshot["supportPrice"],
                snapshot["resistancePrice"],
                snapshot["trendLabel"],
                snapshot["momentumScore"],
                json.dumps(snapshot["fundamentals"] or {}, ensure_ascii=False),
                json.dumps(snapshot["meta"] or {}, ensure_ascii=False)
            )
        )

    @classmethod
    def _load_fundamentals(cls, symbol: str) -> Dict[str, object]:
        market = HistoricalMarketDataService.detect_market(symbol)
        short_symbol = symbol.split(".")[0]
        if market == "US":
            row = DbUtil.fetch_one(
                """
                SELECT symbol, company_name AS name, sector, market_cap, pe_ratio, pb_ratio, dividend_yield
                FROM large_cap_stocks
                WHERE symbol IN (%s, %s)
                ORDER BY CASE WHEN symbol = %s THEN 0 ELSE 1 END
                LIMIT 1
                """,
                (symbol, short_symbol, symbol)
            ) or DbUtil.fetch_one(
                """
                SELECT symbol, company_name AS name, sector, market_cap, NULL AS pe_ratio, NULL AS pb_ratio, NULL AS dividend_yield
                FROM us_stock_info
                WHERE symbol = %s
                LIMIT 1
                """,
                (short_symbol,)
            ) or DbUtil.fetch_one(
                """
                SELECT symbol, etf_name AS name, category AS sector, market_cap, pe_ratio, NULL AS pb_ratio, NULL AS dividend_yield
                FROM us_etf
                WHERE symbol IN (%s, %s)
                ORDER BY CASE WHEN symbol = %s THEN 0 ELSE 1 END
                LIMIT 1
                """,
                (symbol, short_symbol, symbol)
            )
        elif market == "CN":
            row = DbUtil.fetch_one(
                """
                SELECT symbol, name, sector, market_cap, pe_ratio, NULL AS pb_ratio, NULL AS dividend_yield
                FROM cn_stocks
                WHERE symbol = %s
                LIMIT 1
                """,
                (symbol,)
            ) or DbUtil.fetch_one(
                """
                SELECT symbol, etf_name AS name, category AS sector, market_cap, pe_ratio, NULL AS pb_ratio, NULL AS dividend_yield
                FROM cn_etf
                WHERE symbol = %s
                LIMIT 1
                """,
                (symbol,)
            )
        else:
            row = DbUtil.fetch_one(
                """
                SELECT symbol, name, sector, market_cap, pe_ratio, NULL AS pb_ratio, NULL AS dividend_yield
                FROM hk_stocks
                WHERE symbol = %s
                LIMIT 1
                """,
                (symbol,)
            ) or DbUtil.fetch_one(
                """
                SELECT symbol, etf_name AS name, category AS sector, market_cap, pe_ratio, NULL AS pb_ratio, NULL AS dividend_yield
                FROM hk_etf
                WHERE symbol = %s
                LIMIT 1
                """,
                (symbol,)
            )
        return cls._normalize_fundamentals_row(row or {})

    @classmethod
    def _collect_universe_symbols(
        cls,
        markets: Optional[Iterable[str]] = None,
        limit: int = 1000,
        offset: int = 0
    ) -> List[Dict[str, object]]:
        normalized_markets = [str(item).strip().upper() for item in (markets or ["US", "CN", "HK"]) if str(item).strip()]
        allowed_markets = [item for item in normalized_markets if item in {"US", "CN", "HK"}] or ["US", "CN", "HK"]

        union_parts = []
        params: List[object] = []
        table_map = [
            ("large_cap_stocks", "US"),
            ("us_etf", "US"),
            ("cn_stocks", "CN"),
            ("cn_etf", "CN"),
            ("hk_stocks", "HK"),
            ("hk_etf", "HK")
        ]
        for table_name, market in table_map:
            if market not in allowed_markets:
                continue
            union_parts.append(f"SELECT symbol, '{market}' AS market FROM {table_name} WHERE is_active = 1")

        if not union_parts:
            return []

        sql = f"""
        SELECT symbol, market
        FROM (
            {' UNION ALL '.join(union_parts)}
        ) universe
        ORDER BY market ASC, symbol ASC
        LIMIT %s OFFSET %s
        """
        params.extend([int(limit), int(offset)])
        rows = DbUtil.fetch_all(sql, tuple(params)) or []
        return [{"symbol": row.get("symbol"), "market": row.get("market")} for row in rows if row.get("symbol")]

    @classmethod
    def _normalize_snapshot_row(cls, row: Dict[str, object]) -> Dict[str, object]:
        return {
            "symbol": row.get("symbol"),
            "market": row.get("market"),
            "timeframe": row.get("timeframe"),
            "tradeDate": row.get("trade_date").strftime("%Y-%m-%d") if row.get("trade_date") else None,
            "closePrice": float(row.get("close_price") or 0),
            "changePercent": float(row.get("change_percent") or 0),
            "rsi": float(row.get("rsi") or 0),
            "macdDiff": float(row.get("macd_diff") or 0),
            "macdDea": float(row.get("macd_dea") or 0),
            "macdHist": float(row.get("macd_hist") or 0),
            "bollMid": float(row.get("boll_mid") or 0),
            "bollUpper": float(row.get("boll_upper") or 0),
            "bollLower": float(row.get("boll_lower") or 0),
            "emaShort": float(row.get("ema_short") or 0),
            "emaLong": float(row.get("ema_long") or 0),
            "smaMid": float(row.get("sma_mid") or 0),
            "smaLong": float(row.get("sma_long") or 0),
            "atr": float(row.get("atr") or 0),
            "kValue": float(row.get("k_value") or 0),
            "dValue": float(row.get("d_value") or 0),
            "jValue": float(row.get("j_value") or 0),
            "obv": float(row.get("obv") or 0),
            "roc": float(row.get("roc") or 0),
            "cci": float(row.get("cci") or 0),
            "supportPrice": float(row.get("support_price") or 0),
            "resistancePrice": float(row.get("resistance_price") or 0),
            "trendLabel": row.get("trend_label") or "",
            "momentumScore": float(row.get("momentum_score") or 0),
            "fundamentals": cls._json_load(row.get("fundamentals_json")),
            "meta": cls._json_load(row.get("meta_json")),
            "generatedAt": row.get("generated_at").strftime("%Y-%m-%d %H:%M:%S") if row.get("generated_at") else None
        }

    @staticmethod
    def _trend_label(close_price: float, ema_short: float, ema_long: float, rsi: float, roc: float) -> str:
        if close_price >= ema_short >= ema_long and rsi >= 55 and roc >= 0:
            return "多头强化"
        if close_price >= ema_short and ema_short >= ema_long:
            return "偏多震荡"
        if close_price <= ema_short <= ema_long and rsi <= 45 and roc <= 0:
            return "空头压制"
        return "震荡整理"

    @staticmethod
    def _momentum_score(rsi: float, macd_hist: float, roc: float) -> float:
        score = 50.0
        score += max(-18, min(18, (rsi - 50) * 0.65))
        score += max(-16, min(16, roc * 1.8))
        score += max(-12, min(12, macd_hist * 120))
        return max(0, min(100, score))

    @staticmethod
    def _json_load(raw_value):
        if isinstance(raw_value, dict):
            return raw_value
        if not raw_value:
            return {}
        try:
            parsed = json.loads(raw_value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _normalize_fundamentals_row(row: Dict[str, object]) -> Dict[str, object]:
        normalized = {}
        for key, value in (row or {}).items():
            if isinstance(value, Decimal):
                normalized[key] = float(value)
            elif hasattr(value, "strftime"):
                normalized[key] = value.strftime("%Y-%m-%d")
            else:
                normalized[key] = value
        return normalized
