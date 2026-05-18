#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
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

# longbridge Rust SDK 在本机 socks5 代理环境下容易直接失败，这里统一清理。
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


TABLE_UNDERLYINGS = "us_option_underlyings"
TABLE_CONTRACTS = "us_option_contracts"
TABLE_CHAIN_SNAPSHOTS = "us_option_chain_snapshots"
TABLE_QUOTE_SNAPSHOTS = "us_option_quote_snapshots"
TABLE_DAILY_PRICES = "us_option_daily_prices"

DEFAULT_BROAD_ETFS = [
    "SPY.US",
    "QQQ.US",
    "DIA.US",
    "IWM.US",
    "IVV.US",
    "VOO.US",
]

# Dow 成分用来做 price-weight proxy，再按当前价格取前 20。
DEFAULT_DOW_30 = [
    "AAPL.US",
    "AMGN.US",
    "AXP.US",
    "BA.US",
    "CAT.US",
    "CRM.US",
    "CSCO.US",
    "CVX.US",
    "DIS.US",
    "GS.US",
    "HD.US",
    "HON.US",
    "IBM.US",
    "JNJ.US",
    "JPM.US",
    "KO.US",
    "MCD.US",
    "MMM.US",
    "MRK.US",
    "MSFT.US",
    "NKE.US",
    "NVDA.US",
    "PG.US",
    "SHW.US",
    "TRV.US",
    "UNH.US",
    "V.US",
    "VZ.US",
    "WMT.US",
]

# 没有官方权重表时，先排掉明显不属于 S&P500 / Nasdaq100 / Dow 权重核心的符号。
DEFAULT_PROXY_EXCLUDES = {
    "ASML.US",
    "BRK_A.US",
    "TSM.US",
}


@dataclass
class LongbridgeAccount:
    id: int
    user_id: int
    broker_name: str
    account_id: str


@dataclass
class UnderlyingCandidate:
    symbol: str
    name: str
    is_etf: bool
    market_cap: Optional[float]
    current_price: Optional[float]
    tags: List[str] = field(default_factory=list)


@dataclass
class ContractSeed:
    option_symbol: str
    underlying_symbol: str
    expiry_date: date
    strike_price: Optional[float]
    option_type: str
    is_standard: bool


@dataclass
class UnderlyingSyncResult:
    underlying_symbol: str
    expiry_count: int
    contract_count: int
    quote_count: int
    saved_price_rows: int
    history_symbols_done: int
    history_symbols_failed: int
    history_symbols_deferred: int
    request_count: int


class DeferredOptionHistoryError(RuntimeError):
    def __init__(self, option_symbol: str, start_date: date, end_date: date, message: str):
        super().__init__(message)
        self.option_symbol = option_symbol
        self.start_date = start_date
        self.end_date = end_date
        self.message = message


class OptionsProgressStore:
    def __init__(
        self,
        path: Path,
        *,
        source: str,
        start_date: date,
        end_date: date,
        scope_profile: str,
    ):
        self.path = path
        self.source = source
        self.start_date = start_date
        self.end_date = end_date
        self.scope_profile = scope_profile
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
            "scope_profile": self.scope_profile,
        }
        if any(meta.get(key) != value for key, value in expected.items()):
            payload = {}
        payload["meta"] = {
            **expected,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        payload["underlyings"] = (
            payload.get("underlyings")
            if isinstance(payload.get("underlyings"), dict)
            else {}
        )
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

    def _ensure_underlying_state(self, underlying_symbol: str) -> Dict[str, object]:
        underlyings = self._payload["underlyings"]
        state = underlyings.get(underlying_symbol)
        if not isinstance(state, dict):
            state = {}
            underlyings[underlying_symbol] = state
        contracts = state.get("contracts")
        if not isinstance(contracts, dict):
            contracts = {}
            state["contracts"] = contracts
        return state

    def mark_chain_loaded(
        self,
        underlying_symbol: str,
        *,
        contract_count: int,
        expiry_count: int,
    ) -> None:
        with self._lock:
            state = self._ensure_underlying_state(underlying_symbol)
            state["contract_count"] = int(contract_count)
            state["expiry_count"] = int(expiry_count)
            state["chain_loaded_at"] = datetime.now().isoformat(timespec="seconds")
            self._write()

    def filter_option_symbols(
        self,
        underlying_symbol: str,
        option_symbols: Sequence[str],
        *,
        deferred_only: bool,
    ) -> List[str]:
        with self._lock:
            state = self._ensure_underlying_state(underlying_symbol)
            contracts = state["contracts"]
            selected: List[str] = []
            for option_symbol in option_symbols:
                contract_state = contracts.get(option_symbol) or {}
                if deferred_only:
                    if contract_state.get("deferred") and not contract_state.get("completed"):
                        selected.append(option_symbol)
                    continue
                if contract_state.get("completed"):
                    continue
                if contract_state.get("deferred"):
                    continue
                selected.append(option_symbol)
            return selected

    def get_underlying_stats(self, underlying_symbol: str) -> Dict[str, int]:
        with self._lock:
            state = (self._payload.get("underlyings") or {}).get(underlying_symbol) or {}
            contracts = state.get("contracts") if isinstance(state.get("contracts"), dict) else {}
            tracked = len(contracts)
            completed = 0
            deferred = 0
            for contract_state in contracts.values():
                if contract_state.get("completed"):
                    completed += 1
                elif contract_state.get("deferred"):
                    deferred += 1
            pending = max(tracked - completed - deferred, 0)
            return {
                "tracked": tracked,
                "completed": completed,
                "deferred": deferred,
                "pending": pending,
                "chain_loaded": 1 if state.get("chain_loaded_at") else 0,
            }

    def mark_contract_completed(
        self,
        underlying_symbol: str,
        option_symbol: str,
        *,
        saved_rows: int,
        first_trade_date: Optional[str],
        last_trade_date: Optional[str],
    ) -> None:
        with self._lock:
            state = self._ensure_underlying_state(underlying_symbol)
            contract_state = state["contracts"].setdefault(option_symbol, {})
            contract_state["completed"] = True
            contract_state["deferred"] = False
            contract_state["saved_rows"] = int(saved_rows)
            contract_state["first_trade_date"] = first_trade_date
            contract_state["last_trade_date"] = last_trade_date
            contract_state["next_start_date"] = (
                self.end_date + timedelta(days=1)
            ).strftime("%Y-%m-%d")
            contract_state.pop("deferred_reason", None)
            contract_state.pop("last_error", None)
            contract_state["updated_at"] = datetime.now().isoformat(timespec="seconds")
            self._write()

    def mark_contract_deferred(
        self,
        underlying_symbol: str,
        option_symbol: str,
        *,
        reason: str,
    ) -> None:
        with self._lock:
            state = self._ensure_underlying_state(underlying_symbol)
            contract_state = state["contracts"].setdefault(option_symbol, {})
            contract_state["completed"] = False
            contract_state["deferred"] = True
            contract_state["deferred_reason"] = str(reason)
            contract_state["updated_at"] = datetime.now().isoformat(timespec="seconds")
            self._write()

    def mark_contract_failed(
        self,
        underlying_symbol: str,
        option_symbol: str,
        *,
        error: str,
    ) -> None:
        with self._lock:
            state = self._ensure_underlying_state(underlying_symbol)
            contract_state = state["contracts"].setdefault(option_symbol, {})
            contract_state["completed"] = False
            contract_state["last_error"] = str(error)
            contract_state["updated_at"] = datetime.now().isoformat(timespec="seconds")
            self._write()

    def seed_completed_contracts(self, rows: Sequence[Dict[str, object]]) -> None:
        if not rows:
            return
        with self._lock:
            for row in rows:
                underlying_symbol = normalize_symbol(row.get("underlying_symbol") or "")
                option_symbol = normalize_symbol(row.get("option_symbol") or "")
                if not underlying_symbol or not option_symbol:
                    continue
                state = self._ensure_underlying_state(underlying_symbol)
                contract_state = state["contracts"].setdefault(option_symbol, {})
                contract_state["completed"] = True
                contract_state["deferred"] = False
                contract_state["saved_rows"] = int(to_int(row.get("saved_rows")) or 0)
                contract_state["first_trade_date"] = str(row.get("first_trade_date") or "") or None
                contract_state["last_trade_date"] = str(row.get("last_trade_date") or "") or None
                contract_state["next_start_date"] = (
                    self.end_date + timedelta(days=1)
                ).strftime("%Y-%m-%d")
                contract_state["seeded_from_db"] = True
                contract_state.pop("deferred_reason", None)
                contract_state.pop("last_error", None)
                contract_state["updated_at"] = datetime.now().isoformat(timespec="seconds")
            self._write()


def db_connection(*, dict_cursor: bool = False, autocommit: bool = False):
    kwargs = dict(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=settings.DB_NAME,
        charset=settings.DB_CHARSET,
        autocommit=autocommit,
    )
    if dict_cursor:
        kwargs["cursorclass"] = pymysql.cursors.DictCursor
    return pymysql.connect(**kwargs)


class LongbridgeRateLimiter:
    def __init__(self, max_requests_per_second: float = 6.0):
        self.min_interval = 1.0 / max(max_requests_per_second, 0.1)
        self._next_allowed_at = 0.0

    def acquire(self) -> None:
        now = time.monotonic()
        if now < self._next_allowed_at:
            time.sleep(self._next_allowed_at - now)
            now = time.monotonic()
        self._next_allowed_at = now + self.min_interval


def normalize_symbol(symbol: str) -> str:
    return str(symbol or "").strip().upper().replace(".", "_").replace("_US", ".US").replace("_HK", ".HK").replace("_SH", ".SH").replace("_SZ", ".SZ")


def to_float(value) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except Exception:
        return None


def to_int(value) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except Exception:
        return None


def enum_name(value) -> Optional[str]:
    if value is None:
        return None
    name = getattr(value, "name", None)
    if name:
        return str(name)
    raw = str(value)
    return raw.split(".")[-1] if raw else None


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

    with db_connection(dict_cursor=True) as conn:
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


def ensure_schema() -> None:
    statements = [
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE_UNDERLYINGS} (
            underlying_symbol VARCHAR(32) NOT NULL PRIMARY KEY,
            underlying_name VARCHAR(255) NULL,
            market VARCHAR(16) NOT NULL DEFAULT 'US',
            is_etf TINYINT(1) NOT NULL DEFAULT 0,
            scope_profile VARCHAR(64) NOT NULL,
            scope_tags TEXT NULL,
            market_cap DECIMAL(24,2) NULL,
            current_price DECIMAL(20,4) NULL,
            source VARCHAR(64) NOT NULL DEFAULT 'longbridge-us-option',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE_CONTRACTS} (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            option_symbol VARCHAR(40) NOT NULL,
            underlying_symbol VARCHAR(32) NOT NULL,
            option_type VARCHAR(16) NULL,
            expiry_date DATE NULL,
            strike_price DECIMAL(20,4) NULL,
            is_standard TINYINT(1) NOT NULL DEFAULT 1,
            contract_multiplier INT NULL,
            contract_size INT NULL,
            contract_type VARCHAR(32) NULL,
            trade_status VARCHAR(32) NULL,
            last_done DECIMAL(20,6) NULL,
            prev_close DECIMAL(20,6) NULL,
            open_price DECIMAL(20,6) NULL,
            high_price DECIMAL(20,6) NULL,
            low_price DECIMAL(20,6) NULL,
            volume BIGINT NULL,
            turnover DECIMAL(24,6) NULL,
            open_interest BIGINT NULL,
            implied_volatility DECIMAL(20,6) NULL,
            historical_volatility DECIMAL(20,6) NULL,
            first_seen_at DATETIME NULL,
            last_seen_at DATETIME NULL,
            last_quote_at DATETIME NULL,
            source VARCHAR(64) NOT NULL DEFAULT 'longbridge-us-option',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_option_symbol (option_symbol),
            KEY idx_underlying_expiry (underlying_symbol, expiry_date),
            KEY idx_trade_status (trade_status)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE_CHAIN_SNAPSHOTS} (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            snapshot_date DATE NOT NULL,
            collected_at DATETIME NOT NULL,
            source_account_id INT NULL,
            underlying_symbol VARCHAR(32) NOT NULL,
            expiry_date DATE NOT NULL,
            strike_price DECIMAL(20,4) NOT NULL,
            call_symbol VARCHAR(40) NULL,
            put_symbol VARCHAR(40) NULL,
            is_standard TINYINT(1) NOT NULL DEFAULT 1,
            source VARCHAR(64) NOT NULL DEFAULT 'longbridge-us-option',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_chain_snapshot (
                snapshot_date,
                underlying_symbol,
                expiry_date,
                strike_price,
                is_standard
            ),
            KEY idx_chain_underlying (underlying_symbol, expiry_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE_QUOTE_SNAPSHOTS} (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            quote_date DATE NOT NULL,
            quoted_at DATETIME NOT NULL,
            source_account_id INT NULL,
            option_symbol VARCHAR(40) NOT NULL,
            underlying_symbol VARCHAR(32) NULL,
            option_type VARCHAR(16) NULL,
            expiry_date DATE NULL,
            strike_price DECIMAL(20,4) NULL,
            trade_status VARCHAR(32) NULL,
            contract_multiplier INT NULL,
            contract_size INT NULL,
            contract_type VARCHAR(32) NULL,
            last_done DECIMAL(20,6) NULL,
            prev_close DECIMAL(20,6) NULL,
            open_price DECIMAL(20,6) NULL,
            high_price DECIMAL(20,6) NULL,
            low_price DECIMAL(20,6) NULL,
            volume BIGINT NULL,
            turnover DECIMAL(24,6) NULL,
            open_interest BIGINT NULL,
            implied_volatility DECIMAL(20,6) NULL,
            historical_volatility DECIMAL(20,6) NULL,
            source VARCHAR(64) NOT NULL DEFAULT 'longbridge-us-option',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_quote_snapshot (quote_date, option_symbol),
            KEY idx_quote_underlying (underlying_symbol, quote_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE_DAILY_PRICES} (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            option_symbol VARCHAR(40) NOT NULL,
            underlying_symbol VARCHAR(32) NOT NULL,
            trade_date DATE NOT NULL,
            open_price DECIMAL(20,6) NULL,
            high_price DECIMAL(20,6) NULL,
            low_price DECIMAL(20,6) NULL,
            close_price DECIMAL(20,6) NULL,
            volume BIGINT NULL,
            turnover DECIMAL(24,6) NULL,
            source VARCHAR(64) NOT NULL DEFAULT 'longbridge-us-option',
            synced_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_option_trade_date (option_symbol, trade_date),
            KEY idx_underlying_trade_date (underlying_symbol, trade_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
    ]
    with db_connection(autocommit=True) as conn:
        with conn.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)


def query_rows(sql: str, params: Optional[Sequence[object]] = None) -> List[Dict[str, object]]:
    with db_connection(dict_cursor=True) as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, tuple(params or ()))
            return list(cursor.fetchall() or [])


def build_default_underlyings(
    *,
    top_market_cap_limit: int,
    top_dow_limit: int,
) -> List[UnderlyingCandidate]:
    selected: Dict[str, UnderlyingCandidate] = {}

    def _upsert(
        symbol: str,
        name: str,
        *,
        is_etf: bool,
        market_cap: Optional[float],
        current_price: Optional[float],
        tag: str,
    ) -> None:
        normalized = normalize_symbol(symbol)
        if not normalized:
            return
        current = selected.get(normalized)
        if not current:
            selected[normalized] = UnderlyingCandidate(
                symbol=normalized,
                name=name or normalized,
                is_etf=is_etf,
                market_cap=market_cap,
                current_price=current_price,
                tags=[tag],
            )
            return
        if tag not in current.tags:
            current.tags.append(tag)
        if not current.name and name:
            current.name = name
        if current.market_cap is None and market_cap is not None:
            current.market_cap = market_cap
        if current.current_price is None and current_price is not None:
            current.current_price = current_price
        current.is_etf = current.is_etf or is_etf

    broad_placeholders = ", ".join(["%s"] * len(DEFAULT_BROAD_ETFS))
    for row in query_rows(
        f"""
        SELECT symbol, COALESCE(etf_name, symbol) AS name, market_cap, current_price
        FROM us_etf
        WHERE is_active = 1 AND symbol IN ({broad_placeholders})
        ORDER BY FIELD(symbol, {broad_placeholders})
        """,
        [*DEFAULT_BROAD_ETFS, *DEFAULT_BROAD_ETFS],
    ):
        _upsert(
            row["symbol"],
            str(row.get("name") or row.get("symbol") or ""),
            is_etf=True,
            market_cap=to_float(row.get("market_cap")),
            current_price=to_float(row.get("current_price")),
            tag="broad_etf",
        )

    exclude_symbols = sorted(DEFAULT_PROXY_EXCLUDES | set(DEFAULT_BROAD_ETFS))
    exclude_placeholders = ", ".join(["%s"] * len(exclude_symbols))
    top_stock_rows = query_rows(
        f"""
        SELECT symbol, COALESCE(company_name, symbol) AS name, market_cap, current_price
        FROM large_cap_stocks
        WHERE market = 'US'
          AND is_active = 1
          AND market_cap IS NOT NULL
          AND symbol LIKE '%%.US'
          AND symbol NOT IN ({exclude_placeholders})
          AND (company_name IS NULL OR company_name NOT LIKE '%%ETF%%')
        ORDER BY market_cap DESC
        LIMIT %s
        """,
        [*exclude_symbols, int(top_market_cap_limit)],
    )
    for row in top_stock_rows:
        _upsert(
            row["symbol"],
            str(row.get("name") or row.get("symbol") or ""),
            is_etf=False,
            market_cap=to_float(row.get("market_cap")),
            current_price=to_float(row.get("current_price")),
            tag="mega_cap_proxy",
        )

    dow_placeholders = ", ".join(["%s"] * len(DEFAULT_DOW_30))
    for row in query_rows(
        f"""
        SELECT symbol, COALESCE(company_name, symbol) AS name, market_cap, current_price
        FROM large_cap_stocks
        WHERE market = 'US'
          AND is_active = 1
          AND symbol IN ({dow_placeholders})
        ORDER BY current_price DESC, market_cap DESC
        LIMIT %s
        """,
        [*DEFAULT_DOW_30, int(top_dow_limit)],
    ):
        _upsert(
            row["symbol"],
            str(row.get("name") or row.get("symbol") or ""),
            is_etf=False,
            market_cap=to_float(row.get("market_cap")),
            current_price=to_float(row.get("current_price")),
            tag="dow_price_weight_top20",
        )

    return sorted(
        selected.values(),
        key=lambda item: (
            0 if item.is_etf else 1,
            -float(item.market_cap or 0),
            item.symbol,
        ),
    )


def load_manual_underlyings(symbols: Sequence[str]) -> List[UnderlyingCandidate]:
    unique_symbols = []
    for item in symbols:
        normalized = normalize_symbol(item)
        if normalized and normalized not in unique_symbols:
            unique_symbols.append(normalized)
    if not unique_symbols:
        return []

    placeholders = ", ".join(["%s"] * len(unique_symbols))
    rows = query_rows(
        f"""
        SELECT symbol, COALESCE(company_name, symbol) AS name, market_cap, current_price, 0 AS is_etf
        FROM large_cap_stocks
        WHERE symbol IN ({placeholders})
        UNION ALL
        SELECT symbol, COALESCE(etf_name, symbol) AS name, market_cap, current_price, 1 AS is_etf
        FROM us_etf
        WHERE symbol IN ({placeholders})
        """,
        [*unique_symbols, *unique_symbols],
    )
    row_map = {normalize_symbol(row.get("symbol") or ""): row for row in rows}

    results: List[UnderlyingCandidate] = []
    for symbol in unique_symbols:
        row = row_map.get(symbol) or {}
        results.append(
            UnderlyingCandidate(
                symbol=symbol,
                name=str(row.get("name") or symbol),
                is_etf=bool(to_int(row.get("is_etf")) or 0),
                market_cap=to_float(row.get("market_cap")),
                current_price=to_float(row.get("current_price")),
                tags=["manual"],
            )
        )
    return results


def chunked(values: Sequence[str], size: int) -> List[List[str]]:
    size = max(1, int(size or 1))
    return [list(values[index:index + size]) for index in range(0, len(values), size)]


def split_underlyings(items: Sequence[UnderlyingCandidate], shard_count: int) -> List[List[UnderlyingCandidate]]:
    shard_count = max(1, int(shard_count or 1))
    shards: List[List[UnderlyingCandidate]] = [[] for _ in range(shard_count)]
    for index, item in enumerate(items):
        shards[index % shard_count].append(item)
    return shards


class LongbridgeUsOptionsWorker:
    def __init__(
        self,
        account: LongbridgeAccount,
        *,
        source: str,
        start_date: date,
        end_date: date,
        rate_limit_per_second: float,
        quote_batch_size: int,
        replace_range: bool,
        skip_history: bool,
        limit_expiries_per_underlying: int,
        limit_option_symbols: int,
        progress_store: Optional[OptionsProgressStore],
        defer_on_minute_limit: bool,
        deferred_only: bool,
    ):
        self.account = account
        self.source = source
        self.start_date = start_date
        self.end_date = end_date
        self.replace_range = replace_range
        self.skip_history = skip_history
        self.limit_expiries_per_underlying = max(0, int(limit_expiries_per_underlying or 0))
        self.limit_option_symbols = max(0, int(limit_option_symbols or 0))
        self.quote_batch_size = max(1, min(int(quote_batch_size or 50), 200))
        self.progress_store = progress_store
        self.defer_on_minute_limit = defer_on_minute_limit
        self.deferred_only = deferred_only
        self.rate_limiter = LongbridgeRateLimiter(rate_limit_per_second)
        self.quote_context = self._build_quote_context()

    def _build_quote_context(self) -> QuoteContext:
        return build_quote_context(user_id=self.account.user_id)

    def _run_with_retry(self, action_name: str, callback, *, max_retries: int = 8):
        last_error: Optional[Exception] = None
        for attempt in range(1, max_retries + 1):
            try:
                self.rate_limiter.acquire()
                return callback()
            except Exception as exc:
                last_error = exc
                message = str(exc)
                message_lower = message.lower()
                if "301603" in message or "symbol not found" in message_lower:
                    raise RuntimeError(f"{action_name} 不可查询: {exc}") from exc
                if (
                    "301607" in message
                    or "count out of limit" in message_lower
                    or "within one minute" in message_lower
                ):
                    if action_name.startswith("期权 quote 批次") and self.defer_on_minute_limit:
                        raise RuntimeError(f"{action_name} 命中分钟限流，先跳过当前快照批次") from exc
                    if "历史 K 线" in action_name and self.defer_on_minute_limit:
                        raise DeferredOptionHistoryError(
                            action_name.split(" 历史 K 线", 1)[0],
                            self.start_date,
                            self.end_date,
                            f"{action_name} 命中分钟限流，占位后补",
                        ) from exc
                    wait_seconds = 65 + (attempt - 1) * 5
                    print(
                        f"[account={self.account.id}] {action_name} 命中分钟限流，"
                        f"等待 {wait_seconds:.0f}s 后重试",
                        flush=True,
                    )
                    time.sleep(wait_seconds)
                    continue
                if "301606" in message or "rate" in message_lower or "limit" in message_lower:
                    wait_seconds = 2.0 * attempt
                    time.sleep(wait_seconds)
                    continue
                if attempt < max_retries:
                    time.sleep(1.5 * attempt)
                    continue
                raise RuntimeError(f"{action_name} 获取失败: {exc}") from exc
        raise RuntimeError(f"{action_name} 获取失败: {last_error}")

    def sync_underlying(self, underlying: UnderlyingCandidate, *, scope_profile: str) -> UnderlyingSyncResult:
        self._save_underlying(underlying, scope_profile=scope_profile)
        request_count = 0
        expiry_dates = self._fetch_expiry_dates(underlying.symbol)
        request_count += 1
        if self.limit_expiries_per_underlying:
            expiry_dates = expiry_dates[:self.limit_expiries_per_underlying]

        snapshot_date = date.today()
        collected_at = datetime.now()
        contract_map: Dict[str, ContractSeed] = {}
        chain_rows: List[tuple] = []

        for expiry in expiry_dates:
            items = self._fetch_option_chain(underlying.symbol, expiry)
            request_count += 1
            if not items:
                continue
            for item in items:
                strike_price = to_float(getattr(item, "price", None))
                is_standard = bool(getattr(item, "standard", True))
                call_symbol = normalize_symbol(getattr(item, "call_symbol", "") or "")
                put_symbol = normalize_symbol(getattr(item, "put_symbol", "") or "")
                chain_rows.append(
                    (
                        snapshot_date,
                        collected_at,
                        self.account.id,
                        underlying.symbol,
                        expiry,
                        strike_price or 0,
                        call_symbol or None,
                        put_symbol or None,
                        1 if is_standard else 0,
                        self.source,
                    )
                )
                if call_symbol:
                    contract_map[call_symbol] = ContractSeed(
                        option_symbol=call_symbol,
                        underlying_symbol=underlying.symbol,
                        expiry_date=expiry,
                        strike_price=strike_price,
                        option_type="Call",
                        is_standard=is_standard,
                    )
                if put_symbol:
                    contract_map[put_symbol] = ContractSeed(
                        option_symbol=put_symbol,
                        underlying_symbol=underlying.symbol,
                        expiry_date=expiry,
                        strike_price=strike_price,
                        option_type="Put",
                        is_standard=is_standard,
                    )

        self._save_chain_snapshots(chain_rows)

        option_symbols = sorted(contract_map.keys())
        if self.limit_option_symbols:
            option_symbols = option_symbols[:self.limit_option_symbols]
            contract_map = {symbol: contract_map[symbol] for symbol in option_symbols}
        if self.progress_store:
            self.progress_store.mark_chain_loaded(
                underlying.symbol,
                contract_count=len(option_symbols),
                expiry_count=len(expiry_dates),
            )
            option_symbols = self.progress_store.filter_option_symbols(
                underlying.symbol,
                option_symbols,
                deferred_only=self.deferred_only,
            )

        quotes: List[object] = []
        quote_count = 0
        if option_symbols and not self.deferred_only:
            try:
                quotes = self._fetch_option_quotes(option_symbols)
                quote_count = len(quotes)
                request_count += len(chunked(option_symbols, self.quote_batch_size))
                self._save_quote_snapshots(quotes)
            except Exception as exc:
                print(
                    f"[account={self.account.id}] {underlying.symbol} quote 快照失败，"
                    f"继续落合约和 K 线: {exc}",
                    flush=True,
                )
        self._save_contracts(contract_map, quotes)

        saved_price_rows = 0
        history_symbols_done = 0
        history_symbols_failed = 0
        history_symbols_deferred = 0
        if not self.skip_history:
            for index, option_symbol in enumerate(option_symbols, start=1):
                print(
                    f"[account={self.account.id}] {underlying.symbol} "
                    f"{index}/{len(option_symbols)} 回补 {option_symbol} "
                    f"{self.start_date} -> {self.end_date}",
                    flush=True,
                )
                try:
                    candles = self._fetch_option_history(option_symbol)
                    request_count += 1
                    if self.replace_range:
                        self._delete_history_range(option_symbol, self.start_date, self.end_date)
                    seed = contract_map[option_symbol]
                    saved_rows = self._save_daily_prices(
                        option_symbol,
                        seed.underlying_symbol,
                        candles,
                    )
                    saved_price_rows += saved_rows
                    history_symbols_done += 1
                    first_trade_date = None
                    last_trade_date = None
                    if candles:
                        first_trade = getattr(candles[0], "timestamp", None)
                        last_trade = getattr(candles[-1], "timestamp", None)
                        if first_trade:
                            first_trade_date = getattr(
                                first_trade,
                                "date",
                                lambda: first_trade,
                            )().strftime("%Y-%m-%d")
                        if last_trade:
                            last_trade_date = getattr(
                                last_trade,
                                "date",
                                lambda: last_trade,
                            )().strftime("%Y-%m-%d")
                    if self.progress_store:
                        self.progress_store.mark_contract_completed(
                            underlying.symbol,
                            option_symbol,
                            saved_rows=saved_rows,
                            first_trade_date=first_trade_date,
                            last_trade_date=last_trade_date,
                        )
                except DeferredOptionHistoryError as exc:
                    history_symbols_deferred += 1
                    if self.progress_store:
                        self.progress_store.mark_contract_deferred(
                            underlying.symbol,
                            option_symbol,
                            reason=exc.message,
                        )
                    print(
                        f"[account={self.account.id}] {underlying.symbol} "
                        f"占位延后 {option_symbol}: {exc.message}",
                        flush=True,
                    )
                except Exception as exc:
                    history_symbols_failed += 1
                    if self.progress_store:
                        self.progress_store.mark_contract_failed(
                            underlying.symbol,
                            option_symbol,
                            error=str(exc),
                        )
                    print(
                        f"[account={self.account.id}] {underlying.symbol} "
                        f"失败 {option_symbol}: {exc}",
                        flush=True,
                    )

        return UnderlyingSyncResult(
            underlying_symbol=underlying.symbol,
            expiry_count=len(expiry_dates),
            contract_count=len(option_symbols),
            quote_count=quote_count,
            saved_price_rows=saved_price_rows,
            history_symbols_done=history_symbols_done,
            history_symbols_failed=history_symbols_failed,
            history_symbols_deferred=history_symbols_deferred,
            request_count=request_count,
        )

    def _fetch_expiry_dates(self, underlying_symbol: str) -> List[date]:
        expiries = self._run_with_retry(
            f"{underlying_symbol} 到期日列表",
            lambda: self.quote_context.option_chain_expiry_date_list(underlying_symbol) or [],
        )
        return sorted(expiries)

    def _fetch_option_chain(self, underlying_symbol: str, expiry: date):
        return self._run_with_retry(
            f"{underlying_symbol} {expiry} 期权链",
            lambda: self.quote_context.option_chain_info_by_date(underlying_symbol, expiry) or [],
        )

    def _fetch_option_quotes(self, option_symbols: Sequence[str]):
        quote_rows = []
        for symbol_batch in chunked(option_symbols, self.quote_batch_size):
            batch_quotes = self._run_with_retry(
                f"期权 quote 批次 {symbol_batch[0]}..{symbol_batch[-1]}",
                lambda batch=list(symbol_batch): self.quote_context.option_quote(batch) or [],
            )
            quote_rows.extend(batch_quotes)
        return quote_rows

    def _fetch_option_history(self, option_symbol: str):
        return self._run_with_retry(
            f"{option_symbol} 历史 K 线",
            lambda: self.quote_context.history_candlesticks_by_date(
                symbol=option_symbol,
                period=Period.Day,
                adjust_type=AdjustType.NoAdjust,
                start=self.start_date,
                end=self.end_date,
            ) or [],
        )

    def _save_underlying(self, underlying: UnderlyingCandidate, *, scope_profile: str) -> None:
        sql = f"""
        INSERT INTO {TABLE_UNDERLYINGS} (
            underlying_symbol, underlying_name, market, is_etf,
            scope_profile, scope_tags, market_cap, current_price, source
        )
        VALUES (%s, %s, 'US', %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            underlying_name = VALUES(underlying_name),
            is_etf = VALUES(is_etf),
            scope_profile = VALUES(scope_profile),
            scope_tags = VALUES(scope_tags),
            market_cap = VALUES(market_cap),
            current_price = VALUES(current_price),
            source = VALUES(source),
            updated_at = CURRENT_TIMESTAMP
        """
        with db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    sql,
                    (
                        underlying.symbol,
                        underlying.name,
                        1 if underlying.is_etf else 0,
                        scope_profile,
                        json.dumps(sorted(set(underlying.tags)), ensure_ascii=False),
                        underlying.market_cap,
                        underlying.current_price,
                        self.source,
                    ),
                )
            conn.commit()

    def _save_chain_snapshots(self, rows: Sequence[tuple]) -> None:
        if not rows:
            return
        sql = f"""
        INSERT INTO {TABLE_CHAIN_SNAPSHOTS} (
            snapshot_date, collected_at, source_account_id, underlying_symbol,
            expiry_date, strike_price, call_symbol, put_symbol, is_standard, source
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            collected_at = VALUES(collected_at),
            source_account_id = VALUES(source_account_id),
            call_symbol = VALUES(call_symbol),
            put_symbol = VALUES(put_symbol),
            source = VALUES(source)
        """
        with db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.executemany(sql, rows)
            conn.commit()

    def _save_quote_snapshots(self, quotes: Sequence[object]) -> None:
        if not quotes:
            return
        sql = f"""
        INSERT INTO {TABLE_QUOTE_SNAPSHOTS} (
            quote_date, quoted_at, source_account_id, option_symbol, underlying_symbol,
            option_type, expiry_date, strike_price, trade_status, contract_multiplier,
            contract_size, contract_type, last_done, prev_close, open_price,
            high_price, low_price, volume, turnover, open_interest,
            implied_volatility, historical_volatility, source
        )
        VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s
        )
        ON DUPLICATE KEY UPDATE
            quoted_at = VALUES(quoted_at),
            source_account_id = VALUES(source_account_id),
            underlying_symbol = VALUES(underlying_symbol),
            option_type = VALUES(option_type),
            expiry_date = VALUES(expiry_date),
            strike_price = VALUES(strike_price),
            trade_status = VALUES(trade_status),
            contract_multiplier = VALUES(contract_multiplier),
            contract_size = VALUES(contract_size),
            contract_type = VALUES(contract_type),
            last_done = VALUES(last_done),
            prev_close = VALUES(prev_close),
            open_price = VALUES(open_price),
            high_price = VALUES(high_price),
            low_price = VALUES(low_price),
            volume = VALUES(volume),
            turnover = VALUES(turnover),
            open_interest = VALUES(open_interest),
            implied_volatility = VALUES(implied_volatility),
            historical_volatility = VALUES(historical_volatility),
            source = VALUES(source)
        """
        rows = []
        for quote in quotes:
            quoted_at = getattr(quote, "timestamp", None) or datetime.now()
            quote_date = getattr(quoted_at, "date", lambda: date.today())()
            rows.append(
                (
                    quote_date,
                    quoted_at,
                    self.account.id,
                    normalize_symbol(getattr(quote, "symbol", "")),
                    normalize_symbol(getattr(quote, "underlying_symbol", "")),
                    enum_name(getattr(quote, "direction", None)),
                    getattr(quote, "expiry_date", None),
                    to_float(getattr(quote, "strike_price", None)),
                    enum_name(getattr(quote, "trade_status", None)),
                    to_int(getattr(quote, "contract_multiplier", None)),
                    to_int(getattr(quote, "contract_size", None)),
                    enum_name(getattr(quote, "contract_type", None)),
                    to_float(getattr(quote, "last_done", None)),
                    to_float(getattr(quote, "prev_close", None)),
                    to_float(getattr(quote, "open", None)),
                    to_float(getattr(quote, "high", None)),
                    to_float(getattr(quote, "low", None)),
                    to_int(getattr(quote, "volume", None)),
                    to_float(getattr(quote, "turnover", None)),
                    to_int(getattr(quote, "open_interest", None)),
                    to_float(getattr(quote, "implied_volatility", None)),
                    to_float(getattr(quote, "historical_volatility", None)),
                    self.source,
                )
            )
        with db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.executemany(sql, rows)
            conn.commit()

    def _save_contracts(self, contract_map: Dict[str, ContractSeed], quotes: Sequence[object]) -> None:
        quote_map = {
            normalize_symbol(getattr(quote, "symbol", "") or ""): quote
            for quote in quotes
        }
        now = datetime.now()
        sql = f"""
        INSERT INTO {TABLE_CONTRACTS} (
            option_symbol, underlying_symbol, option_type, expiry_date, strike_price,
            is_standard, contract_multiplier, contract_size, contract_type, trade_status,
            last_done, prev_close, open_price, high_price, low_price, volume,
            turnover, open_interest, implied_volatility, historical_volatility,
            first_seen_at, last_seen_at, last_quote_at, source
        )
        VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s
        )
        ON DUPLICATE KEY UPDATE
            underlying_symbol = VALUES(underlying_symbol),
            option_type = VALUES(option_type),
            expiry_date = VALUES(expiry_date),
            strike_price = VALUES(strike_price),
            is_standard = VALUES(is_standard),
            contract_multiplier = VALUES(contract_multiplier),
            contract_size = VALUES(contract_size),
            contract_type = VALUES(contract_type),
            trade_status = VALUES(trade_status),
            last_done = VALUES(last_done),
            prev_close = VALUES(prev_close),
            open_price = VALUES(open_price),
            high_price = VALUES(high_price),
            low_price = VALUES(low_price),
            volume = VALUES(volume),
            turnover = VALUES(turnover),
            open_interest = VALUES(open_interest),
            implied_volatility = VALUES(implied_volatility),
            historical_volatility = VALUES(historical_volatility),
            first_seen_at = IF(first_seen_at IS NULL OR first_seen_at > VALUES(first_seen_at), VALUES(first_seen_at), first_seen_at),
            last_seen_at = VALUES(last_seen_at),
            last_quote_at = VALUES(last_quote_at),
            source = VALUES(source),
            updated_at = CURRENT_TIMESTAMP
        """
        rows = []
        for option_symbol, seed in contract_map.items():
            quote = quote_map.get(option_symbol)
            quoted_at = getattr(quote, "timestamp", None) if quote else None
            rows.append(
                (
                    option_symbol,
                    seed.underlying_symbol,
                    enum_name(getattr(quote, "direction", None)) if quote else seed.option_type,
                    getattr(quote, "expiry_date", None) if quote else seed.expiry_date,
                    to_float(getattr(quote, "strike_price", None)) if quote else seed.strike_price,
                    1 if seed.is_standard else 0,
                    to_int(getattr(quote, "contract_multiplier", None)) if quote else None,
                    to_int(getattr(quote, "contract_size", None)) if quote else None,
                    enum_name(getattr(quote, "contract_type", None)) if quote else None,
                    enum_name(getattr(quote, "trade_status", None)) if quote else None,
                    to_float(getattr(quote, "last_done", None)) if quote else None,
                    to_float(getattr(quote, "prev_close", None)) if quote else None,
                    to_float(getattr(quote, "open", None)) if quote else None,
                    to_float(getattr(quote, "high", None)) if quote else None,
                    to_float(getattr(quote, "low", None)) if quote else None,
                    to_int(getattr(quote, "volume", None)) if quote else None,
                    to_float(getattr(quote, "turnover", None)) if quote else None,
                    to_int(getattr(quote, "open_interest", None)) if quote else None,
                    to_float(getattr(quote, "implied_volatility", None)) if quote else None,
                    to_float(getattr(quote, "historical_volatility", None)) if quote else None,
                    now,
                    now,
                    quoted_at,
                    self.source,
                )
            )
        with db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.executemany(sql, rows)
            conn.commit()

    def _delete_history_range(self, option_symbol: str, start_date: date, end_date: date) -> None:
        sql = f"""
        DELETE FROM {TABLE_DAILY_PRICES}
        WHERE option_symbol = %s AND trade_date BETWEEN %s AND %s
        """
        with db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, (option_symbol, start_date, end_date))
            conn.commit()

    def _save_daily_prices(self, option_symbol: str, underlying_symbol: str, candles: Sequence[object]) -> int:
        rows = []
        for candle in candles or []:
            trade_date = getattr(candle, "timestamp", None)
            trade_day = getattr(trade_date, "date", lambda: trade_date)()
            if not trade_day:
                continue
            rows.append(
                (
                    option_symbol,
                    underlying_symbol,
                    trade_day,
                    to_float(getattr(candle, "open", None)),
                    to_float(getattr(candle, "high", None)),
                    to_float(getattr(candle, "low", None)),
                    to_float(getattr(candle, "close", None)),
                    to_int(getattr(candle, "volume", None)),
                    to_float(getattr(candle, "turnover", None)),
                    self.source,
                )
            )
        if not rows:
            return 0
        sql = f"""
        INSERT INTO {TABLE_DAILY_PRICES} (
            option_symbol, underlying_symbol, trade_date, open_price, high_price,
            low_price, close_price, volume, turnover, source
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            underlying_symbol = VALUES(underlying_symbol),
            open_price = VALUES(open_price),
            high_price = VALUES(high_price),
            low_price = VALUES(low_price),
            close_price = VALUES(close_price),
            volume = VALUES(volume),
            turnover = VALUES(turnover),
            source = VALUES(source),
            synced_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        """
        with db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.executemany(sql, rows)
            conn.commit()
        return len(rows)


def run_batch(
    accounts: Sequence[LongbridgeAccount],
    underlyings: Sequence[UnderlyingCandidate],
    *,
    scope_profile: str,
    start_date: date,
    end_date: date,
    rate_limit_per_second: float,
    quote_batch_size: int,
    replace_range: bool,
    skip_history: bool,
    limit_expiries_per_underlying: int,
    limit_option_symbols: int,
    progress_store: Optional[OptionsProgressStore],
    defer_on_minute_limit: bool,
    deferred_only: bool,
) -> List[UnderlyingSyncResult]:
    if not accounts:
        raise RuntimeError("未找到可用的长桥账户")
    if not underlyings:
        return []

    shards = split_underlyings(underlyings, len(accounts))
    results: List[UnderlyingSyncResult] = []

    def _worker(account: LongbridgeAccount, account_underlyings: Sequence[UnderlyingCandidate]) -> List[UnderlyingSyncResult]:
        worker = LongbridgeUsOptionsWorker(
            account,
            source=f"longbridge-us-option-{scope_profile}",
            start_date=start_date,
            end_date=end_date,
            rate_limit_per_second=rate_limit_per_second,
            quote_batch_size=quote_batch_size,
            replace_range=replace_range,
            skip_history=skip_history,
            limit_expiries_per_underlying=limit_expiries_per_underlying,
            limit_option_symbols=limit_option_symbols,
            progress_store=progress_store,
            defer_on_minute_limit=defer_on_minute_limit,
            deferred_only=deferred_only,
        )
        worker_results: List[UnderlyingSyncResult] = []
        total = len(account_underlyings)
        for index, underlying in enumerate(account_underlyings, start=1):
            print(
                f"[account={account.id}] {index}/{total} 处理 {underlying.symbol} "
                f"tags={','.join(underlying.tags)}",
                flush=True,
            )
            try:
                result = worker.sync_underlying(underlying, scope_profile=scope_profile)
                print(
                    f"[account={account.id}] 完成 {underlying.symbol} "
                    f"expiries={result.expiry_count} contracts={result.contract_count} "
                    f"quotes={result.quote_count} price_rows={result.saved_price_rows} "
                    f"history_ok={result.history_symbols_done} "
                    f"history_deferred={result.history_symbols_deferred} "
                    f"history_fail={result.history_symbols_failed}",
                    flush=True,
                )
                worker_results.append(result)
            except Exception as exc:
                print(f"[account={account.id}] 失败 {underlying.symbol}: {exc}", flush=True)
        return worker_results

    with ThreadPoolExecutor(max_workers=min(len(accounts), 5)) as executor:
        futures = [
            executor.submit(_worker, account, shard)
            for account, shard in zip(accounts, shards)
            if shard
        ]
        for future in as_completed(futures):
            results.extend(future.result())
    results.sort(key=lambda item: item.underlying_symbol)
    return results


def parse_date(raw: str) -> date:
    return datetime.strptime(str(raw).strip(), "%Y-%m-%d").date()


def default_progress_path(scope_profile: str, start_date: date, end_date: date) -> Path:
    slug = "".join(ch if ch.isalnum() else "_" for ch in str(scope_profile or "options"))
    slug = slug.strip("_").lower() or "options"
    return RUNTIME_DIR / f"us_options_resume_{slug}_{start_date:%Y%m%d}_{end_date:%Y%m%d}.json"


def seed_progress_from_existing_prices(
    progress_store: OptionsProgressStore,
    *,
    source: str,
) -> None:
    rows = query_rows(
        f"""
        SELECT option_symbol, underlying_symbol,
               COUNT(*) AS saved_rows,
               MIN(trade_date) AS first_trade_date,
               MAX(trade_date) AS last_trade_date
        FROM {TABLE_DAILY_PRICES}
        WHERE source = %s
        GROUP BY option_symbol, underlying_symbol
        """,
        [source],
    )
    progress_store.seed_completed_contracts(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="使用长桥 OpenAPI 构建独立的美股期权数据表")
    parser.add_argument("--symbols", type=str, default="", help="手工指定标的，例如 SPY.US,QQQ.US,AAPL.US")
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
    parser.add_argument(
        "--scope-profile",
        type=str,
        default="major-us-index-proxy",
        help="作用域标识，会写入 source/profile 字段",
    )
    parser.add_argument("--top-market-cap-limit", type=int, default=20, help="市值 proxy 标的数量，默认 20")
    parser.add_argument("--top-dow-limit", type=int, default=20, help="道指 price-weight proxy 数量，默认 20")
    parser.add_argument("--limit-underlyings", type=int, default=0, help="只处理前 N 个标的，0 表示不限制")
    parser.add_argument("--limit-expiries-per-underlying", type=int, default=0, help="每个标的只取前 N 个到期日，0 表示不限制")
    parser.add_argument("--limit-option-symbols", type=int, default=0, help="每个标的只处理前 N 个期权合约，0 表示不限制")
    parser.add_argument("--quote-batch-size", type=int, default=20, help="单次期权 quote 批量数，默认 20")
    parser.add_argument("--replace-range", action="store_true", help="写入前先删除期权日线目标区间")
    parser.add_argument("--skip-history", action="store_true", help="只抓期权链和快照，不回补期权日 K")
    parser.add_argument("--preview-only", action="store_true", help="只打印将要处理的标的，不真正调用 API")
    parser.add_argument("--progress-file", type=str, default="", help="期权合约断点文件路径")
    parser.add_argument("--reset-progress", action="store_true", help="启动前清空期权断点文件")
    parser.add_argument("--defer-on-minute-limit", action="store_true", help="命中分钟限流时先标记 deferred，后续单独补跑")
    parser.add_argument("--deferred-only", action="store_true", help="只处理 progress 中已 deferred 的期权合约")
    parser.add_argument(
        "--deferred-rate-limit-per-second",
        type=float,
        default=0.8,
        help="二次补跑 deferred 期权合约时每个账户每秒请求上限，默认 0.8 次",
    )
    parser.add_argument(
        "--disable-deferred-second-pass",
        action="store_true",
        help="默认主队列跑完后会低速补一轮 deferred 合约；加上此参数可关闭",
    )
    parser.add_argument(
        "--rate-limit-per-second",
        type=float,
        default=6.0,
        help="每个长桥账户每秒请求上限，默认 6 次，低于官方上限保守运行",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ensure_schema()

    start_date = parse_date(args.start_date)
    end_date = min(parse_date(args.end_date), date.today())
    if end_date < start_date:
        raise SystemExit("end-date 不能早于 start-date")

    progress_path = Path(args.progress_file) if str(args.progress_file or "").strip() else default_progress_path(
        args.scope_profile,
        start_date,
        end_date,
    )
    if args.reset_progress and progress_path.exists():
        progress_path.unlink()
    progress_store = OptionsProgressStore(
        progress_path,
        source=f"longbridge-us-option-{args.scope_profile}",
        start_date=start_date,
        end_date=end_date,
        scope_profile=args.scope_profile,
    )
    if not args.reset_progress:
        seed_progress_from_existing_prices(
            progress_store,
            source=f"longbridge-us-option-{args.scope_profile}",
        )

    account_ids = [int(item) for item in str(args.account_ids or "").split(",") if item.strip()]
    db_accounts = load_longbridge_accounts(account_ids)
    file_accounts = load_accounts_from_file(Path(args.accounts_file))
    accounts = combine_accounts(db_accounts, file_accounts, args.account_mode)
    if not accounts:
        raise SystemExit("未找到可用的长桥账户")

    manual_symbols = [item.strip() for item in str(args.symbols or "").split(",") if item.strip()]
    underlyings = load_manual_underlyings(manual_symbols) if manual_symbols else build_default_underlyings(
        top_market_cap_limit=args.top_market_cap_limit,
        top_dow_limit=args.top_dow_limit,
    )
    if args.limit_underlyings:
        underlyings = underlyings[: int(args.limit_underlyings)]

    if not underlyings:
        raise SystemExit("未找到任何可处理的美股期权标的")

    all_underlyings = list(underlyings)
    pending_underlyings: List[UnderlyingCandidate] = []
    deferred_underlyings: List[UnderlyingCandidate] = []
    completed_underlyings: List[UnderlyingCandidate] = []
    for item in all_underlyings:
        stats = progress_store.get_underlying_stats(item.symbol)
        if args.deferred_only:
            if stats["deferred"] > 0:
                pending_underlyings.append(item)
            continue
        if stats["tracked"] == 0 and not stats["chain_loaded"]:
            pending_underlyings.append(item)
        elif stats["pending"] > 0:
            pending_underlyings.append(item)
        elif stats["deferred"] > 0:
            deferred_underlyings.append(item)
        else:
            completed_underlyings.append(item)
    underlyings = pending_underlyings

    print(
        "注意: 当前长桥接口可枚举的是“当前仍可发现的期权链”和“少量近期已到期链”。"
        "更早已失效、当前链里已经不存在的 2020~2025 老合约，"
        "实测无法再通过 option_chain_info_by_date 追回符号。",
        flush=True,
    )
    print(
        f"准备同步美股期权，标的数={len(underlyings)}，账户数={len(accounts)}，"
        f"区间={start_date}~{end_date}，scope={args.scope_profile}",
        flush=True,
    )
    print(f"progress_file={progress_path}", flush=True)
    print(
        f"主队列 underlyings_pending={len(pending_underlyings)} "
        f"deferred_only={len(deferred_underlyings)} "
        f"completed_skipped={len(completed_underlyings)}",
        flush=True,
    )
    for item in underlyings:
        print(
            f" - {item.symbol:<12} etf={int(item.is_etf)} "
            f"tags={','.join(item.tags)} name={item.name}",
            flush=True,
        )

    if args.preview_only:
        return 0

    started_at = time.perf_counter()
    results = run_batch(
        accounts,
        underlyings,
        scope_profile=args.scope_profile,
        start_date=start_date,
        end_date=end_date,
        rate_limit_per_second=args.rate_limit_per_second,
        quote_batch_size=args.quote_batch_size,
        replace_range=args.replace_range,
        skip_history=args.skip_history,
        limit_expiries_per_underlying=args.limit_expiries_per_underlying,
        limit_option_symbols=args.limit_option_symbols,
        progress_store=progress_store,
        defer_on_minute_limit=args.defer_on_minute_limit,
        deferred_only=args.deferred_only,
    )

    if (
        not args.deferred_only
        and not args.skip_history
        and args.defer_on_minute_limit
        and not args.disable_deferred_second_pass
    ):
        deferred_underlyings = [
            item for item in all_underlyings
            if progress_store.get_underlying_stats(item.symbol)["deferred"] > 0
        ]
        if deferred_underlyings:
            print(
                f"开始低速补跑 deferred 期权合约，标的数={len(deferred_underlyings)}，"
                f"rate_limit_per_second={float(args.deferred_rate_limit_per_second):.2f}",
                flush=True,
            )
            deferred_results = run_batch(
                accounts,
                deferred_underlyings,
                scope_profile=args.scope_profile,
                start_date=start_date,
                end_date=end_date,
                rate_limit_per_second=float(args.deferred_rate_limit_per_second),
                quote_batch_size=args.quote_batch_size,
                replace_range=args.replace_range,
                skip_history=args.skip_history,
                limit_expiries_per_underlying=args.limit_expiries_per_underlying,
                limit_option_symbols=args.limit_option_symbols,
                progress_store=progress_store,
                defer_on_minute_limit=False,
                deferred_only=True,
            )
            results.extend(deferred_results)

    elapsed = round(time.perf_counter() - started_at, 2)
    total_contracts = sum(item.contract_count for item in results)
    total_quotes = sum(item.quote_count for item in results)
    total_price_rows = sum(item.saved_price_rows for item in results)
    total_history_done = sum(item.history_symbols_done for item in results)
    total_history_failed = sum(item.history_symbols_failed for item in results)
    total_history_deferred = sum(item.history_symbols_deferred for item in results)
    total_requests = sum(item.request_count for item in results)

    print("同步完成", flush=True)
    print(f"underlyings={len({item.underlying_symbol for item in results})}", flush=True)
    print(f"contracts={total_contracts}", flush=True)
    print(f"quotes={total_quotes}", flush=True)
    print(f"price_rows={total_price_rows}", flush=True)
    print(f"history_symbols_done={total_history_done}", flush=True)
    print(f"history_symbols_deferred={total_history_deferred}", flush=True)
    print(f"history_symbols_failed={total_history_failed}", flush=True)
    print(f"requests={total_requests}", flush=True)
    print(f"elapsed_seconds={elapsed}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
