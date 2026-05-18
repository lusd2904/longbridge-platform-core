#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import queue
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

ROOT_DIR = Path(__file__).resolve().parents[1]
RUNTIME_DIR = ROOT_DIR / "runtime"
DEFAULT_ACCOUNTS_FILE = RUNTIME_DIR / "longbridge_accounts.local.json"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from apps.runtime_shared.bootstrap import bootstrap_runtime
from apps.market.longbridge_runtime import AdjustType, Period, QuoteContext, build_quote_context

bootstrap_runtime()

import pymysql

from config.settings import settings
from core.analysis.HistoricalMarketDataService import HistoricalMarketDataService

# longbridge Rust SDK 在本机 socks5 代理环境下会直接连接失败，
# 这里主动清掉代理变量，确保长桥 OpenAPI 直连可用。
for proxy_key in (
    "all_proxy",
    "ALL_PROXY",
    "http_proxy",
    "HTTP_PROXY",
    "https_proxy",
    "HTTPS_PROXY",
):
    os.environ.pop(proxy_key, None)
os.environ.setdefault("LONGPORT_PRINT_QUOTE_PACKAGES", "false")


UNIVERSE_TABLES = {
    "us": {"table": "large_cap_stocks", "name_field": "company_name"},
    "us_etf": {"table": "us_etf", "name_field": "etf_name"},
    "cn": {"table": "cn_stocks", "name_field": "name"},
    "cn_etf": {"table": "cn_etf", "name_field": "etf_name"},
    "hk": {"table": "hk_stocks", "name_field": "name"},
    "hk_etf": {"table": "hk_etf", "name_field": "etf_name"},
}


@dataclass
class LongbridgeAccount:
    id: int
    user_id: int
    broker_name: str
    account_id: str


@dataclass
class SyncResult:
    symbol: str
    market: str
    request_count: int
    saved_count: int
    first_trade_date: Optional[str]
    last_trade_date: Optional[str]
    source: str
    deferred: bool = False
    deferred_error: Optional[str] = None


@dataclass
class SyncFailure:
    symbol: str
    account_id: int
    error: str


class DeferredSyncError(RuntimeError):
    def __init__(self, symbol: str, start_date: date, end_date: date, message: str):
        super().__init__(message)
        self.symbol = symbol
        self.start_date = start_date
        self.end_date = end_date
        self.message = message


class ProgressStore:
    def __init__(
        self,
        path: Path,
        *,
        source: str,
        start_date: date,
        end_date: date,
    ):
        self.path = path
        self.source = source
        self.start_date = start_date
        self.end_date = end_date
        self._lock = threading.Lock()
        self._payload = self._load()

    def _load(self) -> Dict[str, object]:
        payload: Dict[str, object] = {}
        if self.path.exists():
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                payload = {}
        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
        expected = {
            "source": self.source,
            "start_date": self.start_date.strftime("%Y-%m-%d"),
            "end_date": self.end_date.strftime("%Y-%m-%d"),
        }
        if any(meta.get(key) != value for key, value in expected.items()):
            payload = {}
        payload["meta"] = {
            **expected,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        payload["symbols"] = payload.get("symbols") if isinstance(payload.get("symbols"), dict) else {}
        return payload

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._payload["meta"]["updated_at"] = datetime.now().isoformat(timespec="seconds")
        temp_path = self.path.with_name(
            f"{self.path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
        )
        temp_path.write_text(
            json.dumps(self._payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temp_path.replace(self.path)

    def get_symbol_state(self, symbol: str) -> Dict[str, object]:
        with self._lock:
            return dict(self._payload["symbols"].get(symbol) or {})

    def mark_range_cleared(self, symbol: str) -> None:
        with self._lock:
            state = self._payload["symbols"].setdefault(symbol, {})
            state["range_cleared"] = True
            state["updated_at"] = datetime.now().isoformat(timespec="seconds")
            self._write()

    def mark_chunk_complete(
        self,
        symbol: str,
        *,
        current_end: date,
        next_start: date,
        first_trade_date: Optional[str],
        last_trade_date: Optional[str],
    ) -> None:
        with self._lock:
            state = self._payload["symbols"].setdefault(symbol, {})
            state["next_start_date"] = next_start.strftime("%Y-%m-%d")
            state["last_completed_end_date"] = current_end.strftime("%Y-%m-%d")
            if first_trade_date:
                state["first_trade_date"] = first_trade_date
            if last_trade_date:
                state["last_trade_date"] = last_trade_date
            state.pop("deferred", None)
            state.pop("deferred_reason", None)
            state.pop("last_error", None)
            state["updated_at"] = datetime.now().isoformat(timespec="seconds")
            self._write()

    def mark_deferred(
        self,
        symbol: str,
        *,
        next_start: date,
        first_trade_date: Optional[str],
        last_trade_date: Optional[str],
        reason: str,
    ) -> None:
        with self._lock:
            state = self._payload["symbols"].setdefault(symbol, {})
            state["completed"] = False
            state["deferred"] = True
            state["deferred_reason"] = str(reason)
            state["next_start_date"] = next_start.strftime("%Y-%m-%d")
            if first_trade_date:
                state["first_trade_date"] = first_trade_date
            if last_trade_date:
                state["last_trade_date"] = last_trade_date
            state["updated_at"] = datetime.now().isoformat(timespec="seconds")
            self._write()

    def mark_completed(
        self,
        symbol: str,
        *,
        first_trade_date: Optional[str],
        last_trade_date: Optional[str],
    ) -> None:
        with self._lock:
            state = self._payload["symbols"].setdefault(symbol, {})
            state["completed"] = True
            state["range_cleared"] = True
            state["next_start_date"] = (self.end_date + timedelta(days=1)).strftime("%Y-%m-%d")
            if first_trade_date:
                state["first_trade_date"] = first_trade_date
            if last_trade_date:
                state["last_trade_date"] = last_trade_date
            state.pop("deferred", None)
            state.pop("deferred_reason", None)
            state.pop("last_error", None)
            state["updated_at"] = datetime.now().isoformat(timespec="seconds")
            self._write()

    def mark_failed(self, symbol: str, error: str) -> None:
        with self._lock:
            state = self._payload["symbols"].setdefault(symbol, {})
            state["last_error"] = str(error)
            state["updated_at"] = datetime.now().isoformat(timespec="seconds")
            self._write()

    def seed_completed_symbols(self, rows: Sequence[Dict[str, object]]) -> None:
        if not rows:
            return
        with self._lock:
            symbols_state = self._payload["symbols"]
            for row in rows:
                symbol = str(row.get("symbol") or "").strip()
                if not symbol:
                    continue
                state = symbols_state.setdefault(symbol, {})
                state["completed"] = True
                state["range_cleared"] = True
                state["next_start_date"] = (self.end_date + timedelta(days=1)).strftime("%Y-%m-%d")
                state["first_trade_date"] = str(row.get("first_trade_date") or "") or None
                state["last_trade_date"] = str(row.get("last_trade_date") or "") or None
                state["seeded_from_db"] = True
                state.pop("deferred", None)
                state.pop("deferred_reason", None)
                state.pop("last_error", None)
                state["updated_at"] = datetime.now().isoformat(timespec="seconds")
            self._write()


class LongbridgeRateLimiter:
    def __init__(self, max_requests_per_second: float = 8.0):
        self.min_interval = 1.0 / max_requests_per_second
        self._next_allowed_at = 0.0

    def acquire(self) -> None:
        now = time.monotonic()
        if now < self._next_allowed_at:
            time.sleep(self._next_allowed_at - now)
            now = time.monotonic()
        self._next_allowed_at = now + self.min_interval


class LongbridgeHistorySyncWorker:
    def __init__(
        self,
        account: LongbridgeAccount,
        *,
        source: str,
        chunk_days: int = 330,
        rate_limit_per_second: float = 8.0,
    ):
        self.account = account
        self.source = source
        self.chunk_days = max(90, min(int(chunk_days or 330), 900))
        self.rate_limiter = LongbridgeRateLimiter(rate_limit_per_second)
        self.quote_context = self._build_quote_context()

    def _build_quote_context(self) -> QuoteContext:
        return build_quote_context(user_id=self.account.user_id)

    def sync_symbol(
        self,
        symbol: str,
        *,
        start_date: date,
        end_date: date,
        replace_range: bool = False,
        chunk_sleep_seconds: float = 0.12,
        progress_store: Optional[ProgressStore] = None,
        defer_on_minute_limit: bool = False,
    ) -> SyncResult:
        normalized_symbol = HistoricalMarketDataService.normalize_symbol(symbol)
        market = HistoricalMarketDataService.detect_market(normalized_symbol)
        request_count = 0
        saved_count = 0
        state = progress_store.get_symbol_state(normalized_symbol) if progress_store else {}
        first_trade_date = str(state.get("first_trade_date") or "") or None
        last_trade_date = str(state.get("last_trade_date") or "") or None

        next_start_raw = str(state.get("next_start_date") or "").strip()
        cursor = start_date
        if next_start_raw:
            try:
                cursor = max(cursor, datetime.strptime(next_start_raw, "%Y-%m-%d").date())
            except ValueError:
                cursor = start_date

        if replace_range:
            if not state.get("range_cleared"):
                self._delete_symbol_range(normalized_symbol, start_date, end_date)
                if progress_store:
                    progress_store.mark_range_cleared(normalized_symbol)

        if state.get("completed") or cursor > end_date:
            if progress_store:
                progress_store.mark_completed(
                    normalized_symbol,
                    first_trade_date=first_trade_date,
                    last_trade_date=last_trade_date,
                )
            return SyncResult(
                symbol=normalized_symbol,
                market=market,
                request_count=0,
                saved_count=0,
                first_trade_date=first_trade_date,
                last_trade_date=last_trade_date,
                source=self.source,
            )

        try:
            while cursor <= end_date:
                current_end = min(end_date, cursor + timedelta(days=self.chunk_days - 1))
                candles = self._fetch_chunk_with_retry(
                    normalized_symbol,
                    start_date=cursor,
                    end_date=current_end,
                    defer_on_minute_limit=defer_on_minute_limit,
                )
                request_count += 1
                payload = self._format_candles(candles)
                if payload:
                    saved_count += self._save_candles(normalized_symbol, market, payload)
                    first_trade_date = first_trade_date or payload[0]["trade_date"]
                    last_trade_date = payload[-1]["trade_date"]

                next_cursor = current_end + timedelta(days=1)
                if progress_store:
                    progress_store.mark_chunk_complete(
                        normalized_symbol,
                        current_end=current_end,
                        next_start=next_cursor,
                        first_trade_date=first_trade_date,
                        last_trade_date=last_trade_date,
                    )

                cursor = next_cursor
                if cursor <= end_date:
                    time.sleep(max(float(chunk_sleep_seconds or 0), 0))
        except DeferredSyncError as exc:
            if progress_store:
                progress_store.mark_deferred(
                    normalized_symbol,
                    next_start=cursor,
                    first_trade_date=first_trade_date,
                    last_trade_date=last_trade_date,
                    reason=exc.message,
                )
            return SyncResult(
                symbol=normalized_symbol,
                market=market,
                request_count=request_count,
                saved_count=saved_count,
                first_trade_date=first_trade_date,
                last_trade_date=last_trade_date,
                source=self.source,
                deferred=True,
                deferred_error=exc.message,
            )
        except Exception as exc:
            if progress_store:
                progress_store.mark_failed(normalized_symbol, str(exc))
            raise

        if progress_store:
            progress_store.mark_completed(
                normalized_symbol,
                first_trade_date=first_trade_date,
                last_trade_date=last_trade_date,
            )

        return SyncResult(
            symbol=normalized_symbol,
            market=market,
            request_count=request_count,
            saved_count=saved_count,
            first_trade_date=first_trade_date,
            last_trade_date=last_trade_date,
            source=self.source,
        )

    def _fetch_chunk_with_retry(
        self,
        symbol: str,
        *,
        start_date: date,
        end_date: date,
        max_retries: int = 8,
        defer_on_minute_limit: bool = False,
    ):
        last_error: Optional[Exception] = None
        for attempt in range(1, max_retries + 1):
            try:
                self.rate_limiter.acquire()
                return self.quote_context.history_candlesticks_by_date(
                    symbol=symbol,
                    period=Period.Day,
                    adjust_type=AdjustType.ForwardAdjust,
                    start=start_date,
                    end=end_date,
                ) or []
            except Exception as exc:  # pragma: no cover - runtime guard
                last_error = exc
                message = str(exc)
                message_lower = message.lower()
                wait_seconds = 1.5 * attempt
                if "301600" in message or "invalid symbol" in message_lower:
                    raise RuntimeError(
                        f"{symbol} {start_date}~{end_date} 获取失败: {exc}"
                    ) from exc
                if (
                    "301607" in message
                    or "count out of limit" in message_lower
                    or "within one minute" in message_lower
                ):
                    if defer_on_minute_limit:
                        raise DeferredSyncError(
                            symbol,
                            start_date,
                            end_date,
                            f"{symbol} {start_date}~{end_date} 命中分钟限流，占位后补",
                        ) from exc
                    wait_seconds = 65 + (attempt - 1) * 5
                    print(
                        f"{symbol} 命中分钟限流，等待 {wait_seconds:.0f}s 后重试 "
                        f"({start_date}~{end_date})",
                        flush=True,
                    )
                    time.sleep(wait_seconds)
                    continue
                if "301606" in message or "rate" in message_lower or "limit" in message_lower:
                    time.sleep(wait_seconds)
                    continue
                if attempt < max_retries:
                    time.sleep(wait_seconds)
                    continue
                raise RuntimeError(
                    f"{symbol} {start_date}~{end_date} 获取失败: {exc}"
                ) from exc

        raise RuntimeError(
            f"{symbol} {start_date}~{end_date} 获取失败: {last_error}"
        )

    @staticmethod
    def _format_candles(candles) -> List[Dict[str, object]]:
        payload: List[Dict[str, object]] = []
        for candle in candles or []:
            trade_date = getattr(candle, "timestamp", None)
            trade_day = getattr(trade_date, "date", lambda: trade_date)()
            if not trade_day:
                continue
            payload.append(
                {
                    "trade_date": trade_day.strftime("%Y-%m-%d"),
                    "open": float(getattr(candle, "open", 0) or 0),
                    "high": float(getattr(candle, "high", 0) or 0),
                    "low": float(getattr(candle, "low", 0) or 0),
                    "close": float(getattr(candle, "close", 0) or 0),
                    "volume": int(getattr(candle, "volume", 0) or 0),
                    "turnover": float(getattr(candle, "turnover", 0) or 0),
                }
            )
        payload.sort(key=lambda item: item["trade_date"])
        return payload

    def _delete_symbol_range(self, symbol: str, start_date: date, end_date: date) -> None:
        sql = f"""
        DELETE FROM {HistoricalMarketDataService.TABLE_NAME}
        WHERE symbol = %s AND trade_date BETWEEN %s AND %s
        """
        with self._db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, (symbol, start_date, end_date))
            conn.commit()

    def _save_candles(self, symbol: str, market: str, candles: Sequence[Dict[str, object]]) -> int:
        if not candles:
            return 0
        safe_source = str(self.source or "longbridge-rebuild")[:64]
        sql = f"""
        INSERT INTO {HistoricalMarketDataService.TABLE_NAME} (
            symbol, market, trade_date, open_price, high_price, low_price,
            close_price, volume, turnover, source, synced_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON DUPLICATE KEY UPDATE
            market = VALUES(market),
            open_price = VALUES(open_price),
            high_price = VALUES(high_price),
            low_price = VALUES(low_price),
            close_price = VALUES(close_price),
            volume = VALUES(volume),
            turnover = VALUES(turnover),
            source = VALUES(source),
            synced_at = NOW(),
            updated_at = CURRENT_TIMESTAMP
        """
        rows = [
            (
                symbol,
                market,
                item["trade_date"],
                item["open"],
                item["high"],
                item["low"],
                item["close"],
                item["volume"],
                item["turnover"],
                safe_source,
            )
            for item in candles
        ]
        with self._db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.executemany(sql, rows)
            conn.commit()
        return len(rows)

    @staticmethod
    def _db_connection():
        return pymysql.connect(
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            database=settings.DB_NAME,
            charset=settings.DB_CHARSET,
            autocommit=False,
        )


def load_longbridge_accounts(account_ids: Optional[Iterable[int]] = None) -> List[LongbridgeAccount]:
    account_filter = [int(item) for item in account_ids or [] if str(item).strip()]
    sql = """
    SELECT id, user_id, broker_name, account_id
    FROM broker_accounts
    WHERE broker_type = 'longbridge' AND is_active = 1
    """
    params: List[object] = []
    if account_filter:
        placeholders = ", ".join(["%s"] * len(account_filter))
        sql += f" AND id IN ({placeholders})"
        params.extend(account_filter)
    sql += " ORDER BY is_default DESC, id ASC"

    with pymysql.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=settings.DB_NAME,
        charset=settings.DB_CHARSET,
        cursorclass=pymysql.cursors.DictCursor,
    ) as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, tuple(params))
            rows = cursor.fetchall() or []

    accounts: List[LongbridgeAccount] = []
    for row in rows:
        accounts.append(
            LongbridgeAccount(
                id=int(row["id"]),
                user_id=int(row["user_id"]),
                broker_name=str(row.get("broker_name") or "长桥证券"),
                account_id=str(row.get("account_id") or ""),
            )
        )
    return accounts


def load_accounts_from_file(accounts_file: Path) -> List[LongbridgeAccount]:
    if not accounts_file.exists():
        return []

    payload = json.loads(accounts_file.read_text(encoding="utf-8"))
    raw_accounts = payload if isinstance(payload, list) else payload.get("accounts") or []
    accounts: List[LongbridgeAccount] = []
    next_id = 10000

    for item in raw_accounts:
        if not isinstance(item, dict):
            continue
        raw_id = item.get("id")
        try:
            account_id_value = int(raw_id)
        except (TypeError, ValueError):
            account_id_value = next_id
            next_id += 1

        accounts.append(
            LongbridgeAccount(
                id=account_id_value,
                user_id=int(item.get("user_id") or 1),
                broker_name=str(item.get("broker_name") or item.get("name") or "长桥证券外部账户"),
                account_id=str(item.get("account_id") or ""),
            )
        )

    return accounts


def combine_accounts(
    db_accounts: Sequence[LongbridgeAccount],
    file_accounts: Sequence[LongbridgeAccount],
    mode: str,
) -> List[LongbridgeAccount]:
    safe_mode = str(mode or "merge").strip().lower()
    if safe_mode == "file-only":
        selected = list(file_accounts)
    elif safe_mode == "db-only":
        selected = list(db_accounts)
    else:
        selected = [*db_accounts, *file_accounts]

    deduped: List[LongbridgeAccount] = []
    seen = set()
    for account in selected:
        key = (
            account.id,
            account.account_id,
            account.broker_name,
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(account)
    return deduped


def load_symbols_from_universe(universes: Sequence[str], limit: Optional[int] = None) -> List[str]:
    selected = [item for item in universes if item in UNIVERSE_TABLES]
    if not selected:
        return []

    symbols: List[str] = []
    with pymysql.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=settings.DB_NAME,
        charset=settings.DB_CHARSET,
        cursorclass=pymysql.cursors.DictCursor,
    ) as conn:
        with conn.cursor() as cursor:
            for universe in selected:
                table_name = UNIVERSE_TABLES[universe]["table"]
                cursor.execute(
                    f"""
                    SELECT symbol
                    FROM {table_name}
                    WHERE is_active = 1 AND symbol IS NOT NULL AND symbol <> ''
                    ORDER BY symbol ASC
                    """
                )
                for row in cursor.fetchall() or []:
                    symbol = HistoricalMarketDataService.normalize_symbol(row.get("symbol") or "")
                    if symbol and symbol not in symbols:
                        symbols.append(symbol)
                        if limit and len(symbols) >= limit:
                            return symbols
    return symbols


def ensure_history_table_capacity(source_length: int) -> None:
    required_length = max(64, int(source_length or 0))
    with pymysql.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=settings.DB_NAME,
        charset=settings.DB_CHARSET,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    ) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT CHARACTER_MAXIMUM_LENGTH AS max_len
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = 'source'
                """,
                (settings.DB_NAME, HistoricalMarketDataService.TABLE_NAME),
            )
            row = cursor.fetchone() or {}
            current_length = int(row.get("max_len") or 0)
            if current_length >= required_length:
                return
            cursor.execute(
                f"""
                ALTER TABLE {HistoricalMarketDataService.TABLE_NAME}
                MODIFY COLUMN source VARCHAR({required_length}) DEFAULT 'longbridge'
                """
            )
            print(
                f"已自动扩展 {HistoricalMarketDataService.TABLE_NAME}.source: "
                f"{current_length} -> {required_length}",
                flush=True,
            )


def sanitize_progress_name(raw: str) -> str:
    normalized = []
    for char in str(raw or "").strip():
        if char.isalnum() or char in ("-", "_", "."):
            normalized.append(char)
        else:
            normalized.append("_")
    return "".join(normalized).strip("._") or "longbridge_rebuild"


def default_progress_file(*, source: str, start_date: date, end_date: date) -> Path:
    file_name = (
        f"kline_resume_{sanitize_progress_name(source)}_"
        f"{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.json"
    )
    return RUNTIME_DIR / file_name


def seed_progress_from_existing_rows(
    progress_store: ProgressStore,
    *,
    source: str,
    start_date: date,
    end_date: date,
    target_symbols: Sequence[str],
) -> None:
    symbols = sorted({HistoricalMarketDataService.normalize_symbol(item) for item in target_symbols if item})
    if not symbols:
        return
    completion_floor = end_date - timedelta(days=10)
    placeholders = ", ".join(["%s"] * len(symbols))
    sql = f"""
    SELECT symbol, MIN(trade_date) AS first_trade_date, MAX(trade_date) AS last_trade_date
    FROM {HistoricalMarketDataService.TABLE_NAME}
    WHERE source = %s
      AND trade_date BETWEEN %s AND %s
      AND symbol IN ({placeholders})
    GROUP BY symbol
    HAVING MAX(trade_date) >= %s
    """
    params: List[object] = [source, start_date, end_date, *symbols, completion_floor]
    with pymysql.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=settings.DB_NAME,
        charset=settings.DB_CHARSET,
        cursorclass=pymysql.cursors.DictCursor,
    ) as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, tuple(params))
            rows = cursor.fetchall() or []
    progress_store.seed_completed_symbols(rows)


def run_batch(
    accounts: Sequence[LongbridgeAccount],
    symbols: Sequence[str],
    *,
    start_date: date,
    end_date: date,
    replace_range: bool,
    source: str,
    chunk_days: int,
    rate_limit_per_second: float,
    progress_store: Optional[ProgressStore] = None,
    defer_on_minute_limit: bool = False,
) -> tuple[List[SyncResult], List[SyncFailure]]:
    if not accounts:
        raise RuntimeError("未找到可用的长桥账户")
    if not symbols:
        return [], []

    results: List[SyncResult] = []
    failures: List[SyncFailure] = []
    task_queue: "queue.Queue[str]" = queue.Queue()
    for symbol in symbols:
        task_queue.put(symbol)
    total = len(symbols)
    progress_lock = threading.Lock()
    progress_counter = {"started": 0}

    def _worker(account: LongbridgeAccount) -> tuple[List[SyncResult], List[SyncFailure]]:
        worker = LongbridgeHistorySyncWorker(
            account,
            source=source,
            chunk_days=chunk_days,
            rate_limit_per_second=rate_limit_per_second,
        )
        account_results: List[SyncResult] = []
        account_failures: List[SyncFailure] = []
        while True:
            try:
                symbol = task_queue.get_nowait()
            except queue.Empty:
                break
            with progress_lock:
                progress_counter["started"] += 1
                index = progress_counter["started"]
            print(
                f"[account={account.id}] {index}/{total} 同步 {symbol} "
                f"{start_date} -> {end_date}",
                flush=True,
            )
            try:
                result = worker.sync_symbol(
                    symbol,
                    start_date=start_date,
                    end_date=end_date,
                    replace_range=replace_range,
                    progress_store=progress_store,
                    defer_on_minute_limit=defer_on_minute_limit,
                )
                status_label = "占位延后" if result.deferred else "完成"
                print(
                    f"[account={account.id}] {status_label} {symbol} "
                    f"saved={result.saved_count} requests={result.request_count} "
                    f"range={result.first_trade_date}~{result.last_trade_date}",
                    flush=True,
                )
                account_results.append(result)
            except Exception as exc:
                error_text = str(exc)
                print(f"[account={account.id}] 失败 {symbol}: {error_text}", flush=True)
                account_failures.append(
                    SyncFailure(
                        symbol=HistoricalMarketDataService.normalize_symbol(symbol),
                        account_id=account.id,
                        error=error_text,
                    )
                )
            finally:
                task_queue.task_done()
        return account_results, account_failures

    max_workers = min(len(accounts), 5)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(_worker, account)
            for account in accounts
        ]
        for future in as_completed(futures):
            worker_results, worker_failures = future.result()
            results.extend(worker_results)
            failures.extend(worker_failures)

    results.sort(key=lambda item: item.symbol)
    failures.sort(key=lambda item: (item.symbol, item.account_id))
    return results, failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="使用长桥 OpenAPI 重建市场日 K 数据")
    parser.add_argument("--symbols", type=str, default="", help="逗号分隔的标的列表，例如 SPY.US,AAPL.US")
    parser.add_argument(
        "--universes",
        type=str,
        default="",
        help="逗号分隔的标的池代码：us,us_etf,cn,cn_etf,hk,hk_etf；为空时只跑 --symbols",
    )
    parser.add_argument("--account-ids", type=str, default="", help="逗号分隔的长桥账户 ID")
    parser.add_argument(
        "--accounts-file",
        type=str,
        default=str(DEFAULT_ACCOUNTS_FILE),
        help="本地长桥账户文件，默认 refactor-v2/runtime/longbridge_accounts.local.json",
    )
    parser.add_argument(
        "--account-mode",
        type=str,
        default="merge",
        choices=["merge", "db-only", "file-only"],
        help="账户来源模式：merge / db-only / file-only",
    )
    parser.add_argument("--start-date", type=str, default="2020-01-01", help="开始日期，格式 YYYY-MM-DD")
    parser.add_argument("--end-date", type=str, default=date.today().strftime("%Y-%m-%d"), help="结束日期，格式 YYYY-MM-DD")
    parser.add_argument("--chunk-days", type=int, default=330, help="单次分段抓取的自然日天数，默认 330")
    parser.add_argument("--limit-symbols", type=int, default=0, help="只抓前 N 个标的，0 表示不限制")
    parser.add_argument("--source", type=str, default="longbridge-rebuild", help="落库 source 标识")
    parser.add_argument("--replace-range", action="store_true", help="先删除目标区间再回写")
    parser.add_argument(
        "--progress-file",
        type=str,
        default="",
        help="断点续传进度文件；为空时自动写到 refactor-v2/runtime/",
    )
    parser.add_argument(
        "--reset-progress",
        action="store_true",
        help="忽略并重建断点文件；若搭配 --replace-range，会从头重跑当前任务",
    )
    parser.add_argument(
        "--disable-db-seed",
        action="store_true",
        help="默认会从库里已有 source 记录推断已完成标的；加上此参数可关闭",
    )
    parser.add_argument(
        "--defer-on-minute-limit",
        action="store_true",
        help="命中分钟限流时先占位并延后，后面再补，不在当前主流程里长时间等待",
    )
    parser.add_argument(
        "--deferred-only",
        action="store_true",
        help="只处理 progress 文件里已标记 deferred 的标的",
    )
    parser.add_argument(
        "--deferred-rate-limit-per-second",
        type=float,
        default=1.2,
        help="二次补跑 deferred 标的时每个账户每秒请求上限，默认 1.2 次",
    )
    parser.add_argument(
        "--disable-deferred-second-pass",
        action="store_true",
        help="默认主队列跑完后会低速补一轮 deferred 标的；加上此参数可关闭",
    )
    parser.add_argument(
        "--rate-limit-per-second",
        type=float,
        default=8.0,
        help="每个长桥账户每秒请求上限，默认 8 次，低于官方上限保守运行",
    )
    return parser.parse_args()


def parse_date(raw: str) -> date:
    return datetime.strptime(str(raw).strip(), "%Y-%m-%d").date()


def main() -> int:
    args = parse_args()
    HistoricalMarketDataService.ensure_schema()
    ensure_history_table_capacity(len(str(args.source or "longbridge-rebuild")))

    start_date = parse_date(args.start_date)
    end_date = min(parse_date(args.end_date), date.today())
    if end_date < start_date:
        raise SystemExit("end-date 不能早于 start-date")
    source = str(args.source or "longbridge-rebuild").strip() or "longbridge-rebuild"

    symbol_list = [
        HistoricalMarketDataService.normalize_symbol(item)
        for item in str(args.symbols or "").split(",")
        if str(item).strip()
    ]
    symbol_list = [item for item in symbol_list if item]

    universes = [item.strip() for item in str(args.universes or "").split(",") if item.strip()]
    if universes:
        universe_symbols = load_symbols_from_universe(universes, limit=args.limit_symbols or None)
        for symbol in universe_symbols:
            if symbol not in symbol_list:
                symbol_list.append(symbol)

    if args.limit_symbols and len(symbol_list) > args.limit_symbols:
        symbol_list = symbol_list[: args.limit_symbols]

    if not symbol_list:
        raise SystemExit("没有可抓取的标的，请传 --symbols 或 --universes")

    account_ids = [int(item.strip()) for item in str(args.account_ids or "").split(",") if item.strip()]
    db_accounts = load_longbridge_accounts(account_ids or None)
    accounts_file = Path(str(args.accounts_file or DEFAULT_ACCOUNTS_FILE)).expanduser()
    file_accounts = load_accounts_from_file(accounts_file)
    accounts = combine_accounts(db_accounts, file_accounts, args.account_mode)
    if not accounts:
        raise SystemExit("未找到可用的长桥账户")

    progress_path = (
        Path(str(args.progress_file)).expanduser()
        if str(args.progress_file or "").strip()
        else default_progress_file(source=source, start_date=start_date, end_date=end_date)
    )
    if args.reset_progress and progress_path.exists():
        progress_path.unlink()
    progress_store = ProgressStore(
        progress_path,
        source=source,
        start_date=start_date,
        end_date=end_date,
    )
    if not args.disable_db_seed and not args.reset_progress:
        seed_progress_from_existing_rows(
            progress_store,
            source=source,
            start_date=start_date,
            end_date=end_date,
            target_symbols=symbol_list,
        )
    completed_symbols: List[str] = []
    deferred_symbols: List[str] = []
    pending_symbols: List[str] = []
    for symbol in symbol_list:
        state = progress_store.get_symbol_state(symbol)
        if state.get("completed"):
            completed_symbols.append(symbol)
        elif state.get("deferred"):
            deferred_symbols.append(symbol)
        else:
            pending_symbols.append(symbol)

    if args.deferred_only:
        symbol_list = list(deferred_symbols)
    else:
        symbol_list = list(pending_symbols)

    print(
        f"准备同步 {len(symbol_list)} 个标的，账户数={len(accounts)}，"
        f"区间={start_date}~{end_date}，source={source}",
        flush=True,
    )
    print(f"断点文件: {progress_path}", flush=True)
    print(
        f"主队列 pending={len(pending_symbols)} deferred={len(deferred_symbols)} "
        f"completed_skipped={len(completed_symbols)}",
        flush=True,
    )

    started_at = time.time()
    results, failures = run_batch(
        accounts,
        symbol_list,
        start_date=start_date,
        end_date=end_date,
        replace_range=bool(args.replace_range),
        source=source,
        chunk_days=args.chunk_days,
        rate_limit_per_second=args.rate_limit_per_second,
        progress_store=progress_store,
        defer_on_minute_limit=bool(args.defer_on_minute_limit),
    )

    deferred_second_pass_results: List[SyncResult] = []
    deferred_second_pass_failures: List[SyncFailure] = []
    if (
        not args.deferred_only
        and not args.disable_deferred_second_pass
        and bool(args.defer_on_minute_limit)
    ):
        deferred_symbols = [
            symbol for symbol in pending_symbols + deferred_symbols
            if progress_store.get_symbol_state(symbol).get("deferred")
        ]
        if deferred_symbols:
            print(
                f"\n开始低速补跑 deferred 标的: {len(deferred_symbols)} 个，"
                f"rate_limit_per_second={float(args.deferred_rate_limit_per_second):.2f}",
                flush=True,
            )
            deferred_second_pass_results, deferred_second_pass_failures = run_batch(
                accounts,
                deferred_symbols,
                start_date=start_date,
                end_date=end_date,
                replace_range=bool(args.replace_range),
                source=source,
                chunk_days=args.chunk_days,
                rate_limit_per_second=float(args.deferred_rate_limit_per_second),
                progress_store=progress_store,
                defer_on_minute_limit=False,
            )
            results.extend(deferred_second_pass_results)
            failures.extend(deferred_second_pass_failures)

    results_by_symbol: Dict[str, SyncResult] = {}
    for item in results:
        results_by_symbol[item.symbol] = item
    results = sorted(results_by_symbol.values(), key=lambda item: item.symbol)

    elapsed = time.time() - started_at

    total_saved = sum(item.saved_count for item in results)
    total_requests = sum(item.request_count for item in results)
    total_deferred = sum(1 for item in results if item.deferred)
    print("\n同步完成", flush=True)
    print(f"symbols={len(results)}", flush=True)
    print(f"failed_symbols={len(failures)}", flush=True)
    print(f"deferred_symbols={total_deferred}", flush=True)
    print(f"saved_rows={total_saved}", flush=True)
    print(f"requests={total_requests}", flush=True)
    print(f"elapsed_seconds={elapsed:.1f}", flush=True)

    for item in results:
        print(
            f"{item.symbol} market={item.market} saved={item.saved_count} "
            f"requests={item.request_count} first={item.first_trade_date} last={item.last_trade_date}",
            flush=True,
        )
    if failures:
        print("\n失败明细", flush=True)
        for item in failures:
            print(
                f"{item.symbol} account={item.account_id} error={item.error}",
                flush=True,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
