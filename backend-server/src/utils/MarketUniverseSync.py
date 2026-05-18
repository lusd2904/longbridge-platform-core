"""
全市场基础行情同步工具。

用途：
1. 把美股、港股、A 股股票与 ETF 基础行情批量写入数据库。
2. 为股票池、图表页、推荐页提供本地行情底库。
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import json
import logging
import os
import re
import requests
import subprocess
import sys
import time
from typing import Dict, Iterable, List, Sequence

import pandas as pd

from utils.DbUtil import DbUtil, get_db_connection

logger = logging.getLogger(__name__)


class MarketUniverseSync:
    STOCK_MARKET_TABLES = {
        'US': {'table': 'large_cap_stocks', 'name_field': 'company_name', 'market': 'US'},
        'HK': {'table': 'hk_stocks', 'name_field': 'name', 'market': 'HK'},
        'CN': {'table': 'cn_stocks', 'name_field': 'name', 'market': 'CN'}
    }

    ETF_MARKET_TABLES = {
        'US': {'table': 'us_etf', 'name_field': 'etf_name', 'market': 'US'},
        'HK': {'table': 'hk_etf', 'name_field': 'etf_name', 'market': 'HK'},
        'CN': {'table': 'cn_etf', 'name_field': 'etf_name', 'market': 'CN'}
    }

    CREATE_SQL = {
        'large_cap_stocks': """
            CREATE TABLE IF NOT EXISTS large_cap_stocks (
                id INT AUTO_INCREMENT PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL UNIQUE,
                company_name VARCHAR(100) DEFAULT NULL,
                market VARCHAR(10) DEFAULT 'US',
                sector VARCHAR(80) DEFAULT NULL,
                current_price DECIMAL(20, 4) DEFAULT NULL,
                change_percent DECIMAL(12, 4) DEFAULT NULL,
                volume BIGINT DEFAULT NULL,
                market_cap DECIMAL(24, 2) DEFAULT NULL,
                pe_ratio DECIMAL(20, 4) DEFAULT NULL,
                user_id INT DEFAULT 1,
                group_id INT DEFAULT NULL,
                broker_account_id INT DEFAULT NULL,
                is_active TINYINT(1) DEFAULT 1,
                remark VARCHAR(255) DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_symbol (symbol),
                INDEX idx_market (market),
                INDEX idx_is_active (is_active)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        'cn_stocks': """
            CREATE TABLE IF NOT EXISTS cn_stocks (
                id INT AUTO_INCREMENT PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL UNIQUE,
                name VARCHAR(100) DEFAULT NULL,
                market VARCHAR(10) DEFAULT 'CN',
                sector VARCHAR(80) DEFAULT NULL,
                current_price DECIMAL(20, 4) DEFAULT NULL,
                change_percent DECIMAL(12, 4) DEFAULT NULL,
                volume BIGINT DEFAULT NULL,
                market_cap DECIMAL(24, 2) DEFAULT NULL,
                pe_ratio DECIMAL(20, 4) DEFAULT NULL,
                user_id INT DEFAULT 1,
                group_id INT DEFAULT NULL,
                broker_account_id INT DEFAULT NULL,
                is_active TINYINT(1) DEFAULT 1,
                remark VARCHAR(255) DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_symbol (symbol),
                INDEX idx_market (market),
                INDEX idx_is_active (is_active)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        'hk_stocks': """
            CREATE TABLE IF NOT EXISTS hk_stocks (
                id INT AUTO_INCREMENT PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL UNIQUE,
                name VARCHAR(100) DEFAULT NULL,
                name_en VARCHAR(100) DEFAULT NULL,
                market VARCHAR(10) DEFAULT 'HK',
                sector VARCHAR(80) DEFAULT NULL,
                current_price DECIMAL(20, 4) DEFAULT NULL,
                change_percent DECIMAL(12, 4) DEFAULT NULL,
                volume BIGINT DEFAULT NULL,
                market_cap DECIMAL(24, 2) DEFAULT NULL,
                pe_ratio DECIMAL(20, 4) DEFAULT NULL,
                user_id INT DEFAULT 1,
                group_id INT DEFAULT NULL,
                broker_account_id INT DEFAULT NULL,
                is_active TINYINT(1) DEFAULT 1,
                remark VARCHAR(255) DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_symbol (symbol),
                INDEX idx_market (market),
                INDEX idx_is_active (is_active)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        'us_etf': """
            CREATE TABLE IF NOT EXISTS us_etf (
                id INT AUTO_INCREMENT PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL UNIQUE,
                etf_name VARCHAR(120) DEFAULT NULL,
                market VARCHAR(10) DEFAULT 'US',
                category VARCHAR(80) DEFAULT NULL,
                current_price DECIMAL(20, 4) DEFAULT NULL,
                change_percent DECIMAL(12, 4) DEFAULT NULL,
                volume BIGINT DEFAULT NULL,
                market_cap DECIMAL(24, 2) DEFAULT NULL,
                pe_ratio DECIMAL(20, 4) DEFAULT NULL,
                user_id INT DEFAULT 1,
                group_id INT DEFAULT NULL,
                broker_account_id INT DEFAULT NULL,
                is_active TINYINT(1) DEFAULT 1,
                remark VARCHAR(255) DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_symbol (symbol),
                INDEX idx_market (market),
                INDEX idx_is_active (is_active)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        'cn_etf': """
            CREATE TABLE IF NOT EXISTS cn_etf (
                id INT AUTO_INCREMENT PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL UNIQUE,
                etf_name VARCHAR(120) DEFAULT NULL,
                market VARCHAR(10) DEFAULT 'CN',
                category VARCHAR(80) DEFAULT NULL,
                current_price DECIMAL(20, 4) DEFAULT NULL,
                change_percent DECIMAL(12, 4) DEFAULT NULL,
                volume BIGINT DEFAULT NULL,
                market_cap DECIMAL(24, 2) DEFAULT NULL,
                pe_ratio DECIMAL(20, 4) DEFAULT NULL,
                user_id INT DEFAULT 1,
                group_id INT DEFAULT NULL,
                broker_account_id INT DEFAULT NULL,
                is_active TINYINT(1) DEFAULT 1,
                remark VARCHAR(255) DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_symbol (symbol),
                INDEX idx_market (market),
                INDEX idx_is_active (is_active)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        'hk_etf': """
            CREATE TABLE IF NOT EXISTS hk_etf (
                id INT AUTO_INCREMENT PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL UNIQUE,
                etf_name VARCHAR(120) DEFAULT NULL,
                market VARCHAR(10) DEFAULT 'HK',
                category VARCHAR(80) DEFAULT NULL,
                current_price DECIMAL(20, 4) DEFAULT NULL,
                change_percent DECIMAL(12, 4) DEFAULT NULL,
                volume BIGINT DEFAULT NULL,
                market_cap DECIMAL(24, 2) DEFAULT NULL,
                pe_ratio DECIMAL(20, 4) DEFAULT NULL,
                user_id INT DEFAULT 1,
                group_id INT DEFAULT NULL,
                broker_account_id INT DEFAULT NULL,
                is_active TINYINT(1) DEFAULT 1,
                remark VARCHAR(255) DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_symbol (symbol),
                INDEX idx_market (market),
                INDEX idx_is_active (is_active)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    }

    REQUIRED_COLUMNS = {
        'large_cap_stocks': {
            'company_name': "VARCHAR(100) DEFAULT NULL",
            'market': "VARCHAR(10) DEFAULT 'US'",
            'sector': "VARCHAR(80) DEFAULT NULL",
            'current_price': "DECIMAL(20, 4) DEFAULT NULL",
            'change_percent': "DECIMAL(12, 4) DEFAULT NULL",
            'volume': "BIGINT DEFAULT NULL",
            'market_cap': "DECIMAL(24, 2) DEFAULT NULL",
            'pe_ratio': "DECIMAL(20, 4) DEFAULT NULL",
            'user_id': "INT DEFAULT 1",
            'group_id': "INT DEFAULT NULL",
            'broker_account_id': "INT DEFAULT NULL",
            'is_active': "TINYINT(1) DEFAULT 1",
            'remark': "VARCHAR(255) DEFAULT NULL",
            'updated_at': "TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"
        },
        'cn_stocks': {
            'name': "VARCHAR(100) DEFAULT NULL",
            'market': "VARCHAR(10) DEFAULT 'CN'",
            'sector': "VARCHAR(80) DEFAULT NULL",
            'current_price': "DECIMAL(20, 4) DEFAULT NULL",
            'change_percent': "DECIMAL(12, 4) DEFAULT NULL",
            'volume': "BIGINT DEFAULT NULL",
            'market_cap': "DECIMAL(24, 2) DEFAULT NULL",
            'pe_ratio': "DECIMAL(20, 4) DEFAULT NULL",
            'user_id': "INT DEFAULT 1",
            'group_id': "INT DEFAULT NULL",
            'broker_account_id': "INT DEFAULT NULL",
            'is_active': "TINYINT(1) DEFAULT 1",
            'remark': "VARCHAR(255) DEFAULT NULL",
            'updated_at': "TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"
        },
        'hk_stocks': {
            'name': "VARCHAR(100) DEFAULT NULL",
            'name_en': "VARCHAR(100) DEFAULT NULL",
            'market': "VARCHAR(10) DEFAULT 'HK'",
            'sector': "VARCHAR(80) DEFAULT NULL",
            'current_price': "DECIMAL(20, 4) DEFAULT NULL",
            'change_percent': "DECIMAL(12, 4) DEFAULT NULL",
            'volume': "BIGINT DEFAULT NULL",
            'market_cap': "DECIMAL(24, 2) DEFAULT NULL",
            'pe_ratio': "DECIMAL(20, 4) DEFAULT NULL",
            'user_id': "INT DEFAULT 1",
            'group_id': "INT DEFAULT NULL",
            'broker_account_id': "INT DEFAULT NULL",
            'is_active': "TINYINT(1) DEFAULT 1",
            'remark': "VARCHAR(255) DEFAULT NULL",
            'updated_at': "TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"
        },
        'us_etf': {
            'etf_name': "VARCHAR(120) DEFAULT NULL",
            'market': "VARCHAR(10) DEFAULT 'US'",
            'category': "VARCHAR(80) DEFAULT NULL",
            'current_price': "DECIMAL(20, 4) DEFAULT NULL",
            'change_percent': "DECIMAL(12, 4) DEFAULT NULL",
            'volume': "BIGINT DEFAULT NULL",
            'market_cap': "DECIMAL(24, 2) DEFAULT NULL",
            'pe_ratio': "DECIMAL(20, 4) DEFAULT NULL",
            'user_id': "INT DEFAULT 1",
            'group_id': "INT DEFAULT NULL",
            'broker_account_id': "INT DEFAULT NULL",
            'is_active': "TINYINT(1) DEFAULT 1",
            'remark': "VARCHAR(255) DEFAULT NULL",
            'updated_at': "TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"
        },
        'cn_etf': {
            'etf_name': "VARCHAR(120) DEFAULT NULL",
            'market': "VARCHAR(10) DEFAULT 'CN'",
            'category': "VARCHAR(80) DEFAULT NULL",
            'current_price': "DECIMAL(20, 4) DEFAULT NULL",
            'change_percent': "DECIMAL(12, 4) DEFAULT NULL",
            'volume': "BIGINT DEFAULT NULL",
            'market_cap': "DECIMAL(24, 2) DEFAULT NULL",
            'pe_ratio': "DECIMAL(20, 4) DEFAULT NULL",
            'user_id': "INT DEFAULT 1",
            'group_id': "INT DEFAULT NULL",
            'broker_account_id': "INT DEFAULT NULL",
            'is_active': "TINYINT(1) DEFAULT 1",
            'remark': "VARCHAR(255) DEFAULT NULL",
            'updated_at': "TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"
        },
        'hk_etf': {
            'etf_name': "VARCHAR(120) DEFAULT NULL",
            'market': "VARCHAR(10) DEFAULT 'HK'",
            'category': "VARCHAR(80) DEFAULT NULL",
            'current_price': "DECIMAL(20, 4) DEFAULT NULL",
            'change_percent': "DECIMAL(12, 4) DEFAULT NULL",
            'volume': "BIGINT DEFAULT NULL",
            'market_cap': "DECIMAL(24, 2) DEFAULT NULL",
            'pe_ratio': "DECIMAL(20, 4) DEFAULT NULL",
            'user_id': "INT DEFAULT 1",
            'group_id': "INT DEFAULT NULL",
            'broker_account_id': "INT DEFAULT NULL",
            'is_active': "TINYINT(1) DEFAULT 1",
            'remark': "VARCHAR(255) DEFAULT NULL",
            'updated_at': "TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"
        }
    }

    ETF_KEYWORDS = {
        'US': [
            ' ETF', 'ETF ', 'TRUST', 'FUND', 'ISHARES', 'SPDR', 'VANGUARD',
            'PROSHARES', 'INVESCO', 'DIREXION', 'GLOBAL X', 'SHARES'
        ],
        'HK': [
            'ETF', '盈富基金', '恒生', '南方', 'GX', '华夏', '安硕', '博时'
        ]
    }

    PROXY_ENV_KEYS = [
        'ALL_PROXY', 'all_proxy',
        'HTTP_PROXY', 'http_proxy',
        'HTTPS_PROXY', 'https_proxy',
        'SOCKS_PROXY', 'socks_proxy'
    ]
    SKSHARE_DEFAULT_BASE_URL = 'http://127.0.0.1:18081'

    @classmethod
    def sync_markets(cls, markets: Sequence[str] | None = None, user_id: int = 1) -> Dict[str, object]:
        normalized_markets = cls._normalize_markets(markets)
        cls.ensure_schema()

        started_at = time.time()
        result = {
            'markets': {},
            'total_saved': 0,
            'started_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        for market in normalized_markets:
            market_result = cls.sync_market(market, user_id=user_id)
            result['markets'][market] = market_result
            result['total_saved'] += int(market_result.get('saved', 0))

        result['duration_seconds'] = round(time.time() - started_at, 2)
        result['warnings'] = [
            warning
            for market_result in result['markets'].values()
            for warning in market_result.get('warnings', [])
        ]
        result['warning_count'] = len(result['warnings'])
        result['partial_failure'] = bool(result['warnings'])
        return result

    @classmethod
    def sync_market(cls, market: str, user_id: int = 1) -> Dict[str, object]:
        normalized_market = cls._normalize_markets([market])[0]

        stock_df = cls._fetch_dataframe(normalized_market, 'stock')
        stock_rows = cls._normalize_dataframe(normalized_market, stock_df, user_id=user_id, asset_type='stock')
        stock_reused = len(stock_rows) if stock_df.attrs.get('source') == 'database' else 0
        stock_saved = cls._upsert_new_rows(
            cls.STOCK_MARKET_TABLES[normalized_market],
            stock_rows,
            source=stock_df.attrs.get('source', 'unknown')
        )

        etf_df = cls._fetch_dataframe(normalized_market, 'etf')
        etf_rows = cls._normalize_dataframe(normalized_market, etf_df, user_id=user_id, asset_type='etf')
        etf_reused = len(etf_rows) if etf_df.attrs.get('source') == 'database' else 0
        etf_saved = cls._upsert_new_rows(
            cls.ETF_MARKET_TABLES[normalized_market],
            etf_rows,
            source=etf_df.attrs.get('source', 'unknown')
        )
        warnings = []
        for asset_label, dataframe in (('stocks', stock_df), ('etfs', etf_df)):
            warning = dataframe.attrs.get('warning')
            if warning:
                warnings.append(f"{normalized_market} {asset_label}: {warning}")

        return {
            'market': normalized_market,
            'stock_table': cls.STOCK_MARKET_TABLES[normalized_market]['table'],
            'etf_table': cls.ETF_MARKET_TABLES[normalized_market]['table'],
            'fetched': {
                'stocks': int(len(stock_df.index)),
                'etfs': int(len(etf_df.index))
            },
            'normalized': {
                'stocks': len(stock_rows),
                'etfs': len(etf_rows)
            },
            'stocks_saved': stock_saved,
            'etfs_saved': etf_saved,
            'stocks_reused': stock_reused,
            'etfs_reused': etf_reused,
            'saved': stock_saved + etf_saved,
            'reused': stock_reused + etf_reused,
            'available': stock_saved + etf_saved + stock_reused + etf_reused,
            'sources': {
                'stocks': stock_df.attrs.get('source', 'unknown'),
                'etfs': etf_df.attrs.get('source', 'unknown')
            },
            'warnings': warnings
        }

    @classmethod
    def ensure_schema(cls) -> None:
        for table, create_sql in cls.CREATE_SQL.items():
            DbUtil.execute_sql(create_sql)
            cls._ensure_columns(table, cls.REQUIRED_COLUMNS[table])

    @classmethod
    def _ensure_columns(cls, table_name: str, columns: Dict[str, str]) -> None:
        existing_columns = {row[0] for row in DbUtil.query_all(f"SHOW COLUMNS FROM {table_name}") or []}
        for column_name, definition in columns.items():
            if column_name in existing_columns:
                continue
            DbUtil.execute_sql(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")

    @classmethod
    def _fetch_dataframe(cls, market: str, asset_type: str) -> pd.DataFrame:
        errors = []
        for provider_name, provider in (
            ('skshare', cls._fetch_dataframe_from_skshare),
            ('database', cls._fetch_dataframe_from_existing_table),
            ('akshare', cls._fetch_dataframe_from_akshare_subprocess),
        ):
            try:
                dataframe = provider(market, asset_type)
                if dataframe is not None and not dataframe.empty:
                    dataframe.attrs['source'] = provider_name
                    if errors:
                        dataframe.attrs['warning'] = cls._format_fetch_warning(errors)
                    return dataframe
                errors.append(f'{provider_name}: 返回空数据')
            except Exception as exc:
                logger.warning("市场底库同步数据源失败: %s %s %s", market, asset_type, exc)
                errors.append(f'{provider_name}: {cls._safe_error_text(exc)}')

        dataframe = pd.DataFrame()
        dataframe.attrs['source'] = 'unavailable'
        dataframe.attrs['warning'] = cls._format_fetch_warning(errors)
        return dataframe

    @classmethod
    def _fetch_dataframe_from_skshare(cls, market: str, asset_type: str) -> pd.DataFrame:
        session = requests.Session()
        session.trust_env = False
        interface = cls._akshare_interface_name(market, asset_type)
        last_error = None

        for base_url in cls._skshare_base_urls():
            url = f"{base_url.rstrip('/')}/api/public/{interface}"
            try:
                response = session.get(url, timeout=cls._market_universe_skshare_timeout())
                if response.status_code >= 400:
                    last_error = RuntimeError(f"HTTP {response.status_code}: {response.text[:160]}")
                    continue

                payload = response.json()
                if isinstance(payload, dict):
                    payload = payload.get('data') or payload.get('rows') or payload.get('items') or []
                dataframe = pd.DataFrame(payload or [])
                if not dataframe.empty:
                    return dataframe
                last_error = RuntimeError('返回空数据')
            except Exception as exc:
                last_error = exc
                continue

        if last_error:
            raise RuntimeError(f"skshare {interface} 请求失败: {cls._safe_error_text(last_error)}") from last_error
        raise RuntimeError(f"skshare {interface} 未配置可用地址")

    @classmethod
    def _fetch_dataframe_from_akshare_subprocess(cls, market: str, asset_type: str) -> pd.DataFrame:
        fetch_script = """
import json
import sys
import akshare as ak

market = sys.argv[1]
asset_type = sys.argv[2]
interface = sys.argv[3]
frame = getattr(ak, interface)()

print(frame.to_json(orient='records', force_ascii=False))
""".strip()

        clean_env = dict(os.environ)
        for key in cls.PROXY_ENV_KEYS:
            clean_env.pop(key, None)
        clean_env['NO_PROXY'] = '*'
        clean_env['no_proxy'] = '*'

        result = subprocess.run(
            [sys.executable, '-c', fetch_script, market, asset_type, cls._akshare_interface_name(market, asset_type)],
            env=clean_env,
            check=True,
            capture_output=True,
            text=True,
            timeout=600
        )
        payload = result.stdout.strip()
        dataframe = pd.DataFrame(json.loads(payload)) if payload else pd.DataFrame()

        if dataframe is None or dataframe.empty:
            raise RuntimeError(f'{market} {asset_type} 返回空数据')
        return dataframe

    @classmethod
    def _fetch_dataframe_from_existing_table(cls, market: str, asset_type: str) -> pd.DataFrame:
        table_config = (cls.ETF_MARKET_TABLES if asset_type == 'etf' else cls.STOCK_MARKET_TABLES)[market]
        table_name = table_config['table']
        name_field = table_config['name_field']
        category_field = 'category' if name_field == 'etf_name' else 'sector'
        rows = DbUtil.fetch_all_primary(
            f"""
            SELECT
                symbol AS symbol,
                {name_field} AS name,
                current_price AS price,
                change_percent AS change_percent,
                volume AS volume,
                market_cap AS market_cap,
                pe_ratio AS pe_ratio,
                {category_field} AS sector
            FROM {table_name}
            WHERE is_active = 1
            ORDER BY updated_at DESC, id DESC
            LIMIT 20000
            """
        ) or []
        return pd.DataFrame(rows)

    @classmethod
    def _akshare_interface_name(cls, market: str, asset_type: str) -> str:
        if asset_type == 'etf' and market == 'CN':
            return 'fund_etf_spot_em'
        if market == 'US':
            return 'stock_us_spot_em'
        if market == 'HK':
            return 'stock_hk_spot_em'
        return 'stock_zh_a_spot_em'

    @classmethod
    def _skshare_base_urls(cls) -> List[str]:
        configured = (
            os.getenv('SKSHARE_BASE_URL')
            or os.getenv('REF_SKSHARE_BASE_URL')
            or cls.SKSHARE_DEFAULT_BASE_URL
        )
        candidates = []
        for item in str(configured or '').split(','):
            base_url = item.strip().rstrip('/')
            if base_url and base_url not in candidates:
                candidates.append(base_url)
        return candidates

    @staticmethod
    def _skshare_timeout() -> int:
        raw = os.getenv('SKSHARE_TIMEOUT') or os.getenv('REF_SKSHARE_TIMEOUT') or 45
        try:
            return max(3, min(int(raw), 180))
        except (TypeError, ValueError):
            return 45

    @classmethod
    def _market_universe_skshare_timeout(cls) -> int:
        raw = (
            os.getenv('MARKET_UNIVERSE_SKSHARE_TIMEOUT')
            or os.getenv('REF_MARKET_UNIVERSE_SKSHARE_TIMEOUT')
        )
        if raw:
            try:
                return max(3, min(int(raw), 30))
            except (TypeError, ValueError):
                pass
        return min(cls._skshare_timeout(), 8)

    @staticmethod
    def _safe_error_text(error: Exception) -> str:
        if isinstance(error, subprocess.TimeoutExpired):
            return '本地 AkShare 请求超时'
        if isinstance(error, subprocess.CalledProcessError):
            stderr = str(error.stderr or error.output or '').strip()
            if 'Traceback ' in stderr:
                return f'本地 AkShare 进程退出码 {error.returncode}'
            if stderr:
                return stderr.replace('\n', ' ')[:220]
            return f'本地 AkShare 进程退出码 {error.returncode}'

        text = str(error).replace('\n', ' ').strip()
        return text[:220] if text else error.__class__.__name__

    @classmethod
    def _format_fetch_warning(cls, errors: List[str]) -> str:
        if not errors:
            return ''
        return '外部数据源不可用，已使用可用降级数据；' + '；'.join(errors[-2:])

    @classmethod
    def _normalize_dataframe(
        cls,
        market: str,
        dataframe: pd.DataFrame,
        user_id: int = 1,
        asset_type: str = 'stock'
    ) -> List[Dict[str, object]]:
        rows: List[Dict[str, object]] = []
        sync_mark = f'universe_sync:{asset_type}:{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'

        for record in dataframe.to_dict('records'):
            symbol = cls._normalize_symbol(market, cls._pick(record, '代码', 'symbol', 'Symbol', '代码 '))
            if not symbol:
                continue

            name = cls._clean_text(cls._pick(record, '名称', 'name', 'Name'))
            if not name:
                name = symbol

            if asset_type == 'stock':
                if market in {'US', 'HK'} and cls._looks_like_etf(name, market):
                    continue
                if market == 'CN' and cls._is_cn_etf_symbol(symbol):
                    continue
            else:
                if market in {'US', 'HK'} and not cls._looks_like_etf(name, market):
                    continue

            price = cls._as_float(cls._pick(record, '最新价', '现价', 'price', 'Price'))
            change_percent = cls._as_float(cls._pick(record, '涨跌幅', 'change_percent', '涨跌幅%'))
            volume = cls._as_int(cls._pick(record, '成交量', 'volume', '成交量(股)'))
            market_cap = cls._as_float(cls._pick(record, '总市值', 'market_cap', '成交额'))
            pe_ratio = cls._as_float(cls._pick(record, '市盈率', '市盈率-动态', 'pe_ratio', 'PE'))
            sector = cls._clean_text(cls._pick(record, '所属行业', '行业', 'sector'))
            category = cls._detect_etf_category(name, symbol)

            rows.append({
                'symbol': symbol,
                'name': name,
                'market': market,
                'sector': sector if asset_type == 'stock' else category,
                'current_price': price,
                'change_percent': change_percent,
                'volume': volume,
                'market_cap': market_cap,
                'pe_ratio': pe_ratio,
                'user_id': user_id,
                'is_active': 1,
                'remark': sync_mark
            })

        deduped = {}
        for row in rows:
            deduped[row['symbol']] = row
        return list(deduped.values())

    @classmethod
    def _upsert_rows(cls, table_config: Dict[str, str], rows: List[Dict[str, object]]) -> int:
        if not rows:
            return 0

        table_name = table_config['table']
        name_field = table_config['name_field']
        category_field = 'sector' if name_field != 'etf_name' else 'category'
        columns = [
            'symbol',
            name_field,
            'market',
            category_field,
            'current_price',
            'change_percent',
            'volume',
            'market_cap',
            'pe_ratio',
            'user_id',
            'is_active',
            'remark'
        ]

        placeholders = ', '.join(['%s'] * len(columns))
        update_clause = ', '.join([
            f"{column} = VALUES({column})"
            for column in columns
            if column != 'symbol'
        ])
        sql = f"""
            INSERT INTO {table_name} ({', '.join(columns)})
            VALUES ({placeholders})
            ON DUPLICATE KEY UPDATE
            {update_clause},
            updated_at = CURRENT_TIMESTAMP
        """

        values = []
        for row in rows:
            values.append((
                row['symbol'],
                row['name'],
                row['market'],
                row['sector'],
                row['current_price'],
                row['change_percent'],
                row['volume'],
                row['market_cap'],
                row['pe_ratio'],
                row['user_id'],
                row['is_active'],
                row['remark']
            ))

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                for batch in cls._chunked(values, 500):
                    cursor.executemany(sql, batch)

        return len(rows)

    @classmethod
    def _upsert_new_rows(cls, table_config: Dict[str, str], rows: List[Dict[str, object]], source: str) -> int:
        if not rows or source == 'database':
            return 0
        return cls._upsert_rows(table_config, rows)

    @classmethod
    def _normalize_markets(cls, markets: Sequence[str] | None) -> List[str]:
        if not markets:
            return ['US', 'HK', 'CN']

        normalized = []
        for market in markets:
            key = str(market or '').strip().upper()
            if key not in cls.STOCK_MARKET_TABLES:
                raise ValueError(f'不支持的市场: {market}')
            if key not in normalized:
                normalized.append(key)
        return normalized

    @classmethod
    def _normalize_symbol(cls, market: str, raw_symbol) -> str:
        raw = cls._clean_text(raw_symbol).upper()
        if not raw:
            return ''

        if market == 'US':
            match = re.match(r'^\d+\.(.+)$', raw)
            symbol = match.group(1) if match else raw
            if symbol.endswith('.US'):
                return symbol
            return f'{symbol}.US'

        if market == 'HK':
            if raw.endswith('.HK'):
                return raw
            digits = ''.join(re.findall(r'\d+', raw))
            return f'{digits.zfill(5)}.HK' if digits else ''

        if raw.endswith(('.SH', '.SZ', '.BJ')):
            return raw
        digits = ''.join(re.findall(r'\d+', raw))
        if len(digits) != 6:
            return ''
        if digits.startswith(('5', '6', '9')):
            suffix = 'SH'
        elif digits.startswith(('4', '8')):
            suffix = 'BJ'
        else:
            suffix = 'SZ'
        return f'{digits}.{suffix}'

    @classmethod
    def _looks_like_etf(cls, name: str, market: str) -> bool:
        text = cls._clean_text(name).upper()
        if not text:
            return False
        keywords = cls.ETF_KEYWORDS.get(market, [])
        return any(keyword.upper() in text for keyword in keywords)

    @staticmethod
    def _is_cn_etf_symbol(symbol: str) -> bool:
        code = symbol.split('.')[0]
        return code.startswith(('15', '16', '50', '51', '56', '58', '59'))

    @staticmethod
    def _detect_etf_category(name: str, symbol: str) -> str:
        text = f"{name} {symbol}".upper()
        if any(keyword in text for keyword in ['VIX', 'VOLATILITY', '波动']):
            return 'volatility'
        if any(keyword in text for keyword in ['BOND', '债', '国债', '中短债']):
            return 'bond'
        if any(keyword in text for keyword in ['GOLD', '黄金', 'SILVER', 'OIL', '原油', 'COMMODITY', '商品']):
            return 'commodity'
        if any(keyword in text for keyword in ['DIVIDEND', '红利', '高股息']):
            return 'dividend'
        if any(keyword in text for keyword in ['LEVERAGED', 'ULTRA', '2X', '3X', '反向', '杠杆', 'INVERSE']):
            return 'leveraged'
        if any(keyword in text for keyword in ['TECH', '科技', 'SEMICONDUCTOR', '芯片', '互联网']):
            return 'theme'
        return 'index'

    @staticmethod
    def _pick(record: Dict[str, object], *keys: str):
        for key in keys:
            if key not in record:
                continue
            value = record.get(key)
            if MarketUniverseSync._is_empty(value):
                continue
            return value
        return None

    @staticmethod
    def _is_empty(value) -> bool:
        if value is None:
            return True
        if isinstance(value, str) and not value.strip():
            return True
        try:
            return bool(pd.isna(value))
        except TypeError:
            return False

    @staticmethod
    def _clean_text(value) -> str:
        if MarketUniverseSync._is_empty(value):
            return ''
        return str(value).strip()

    @staticmethod
    def _as_float(value):
        if MarketUniverseSync._is_empty(value):
            return None
        try:
            if isinstance(value, str):
                value = value.replace(',', '').replace('%', '').strip()
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _as_int(value):
        number = MarketUniverseSync._as_float(value)
        if number is None:
            return None
        return int(number)

    @staticmethod
    def _chunked(items: List[tuple], size: int) -> Iterable[List[tuple]]:
        for index in range(0, len(items), size):
            yield items[index:index + size]

    @classmethod
    @contextmanager
    def _proxy_env_suppressed(cls):
        snapshot = {key: os.environ.pop(key, None) for key in cls.PROXY_ENV_KEYS}
        try:
            yield
        finally:
            for key, value in snapshot.items():
                if value:
                    os.environ[key] = value
