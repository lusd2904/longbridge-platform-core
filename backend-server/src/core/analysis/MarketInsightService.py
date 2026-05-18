import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

import pytz

from core.broker.BrokerInterface import get_broker_manager
from utils.DbUtil import DbUtil

logger = logging.getLogger(__name__)


class MarketInsightService:
    MARKET_LABELS = {
        'US': '美股',
        'CN': 'A股',
        'HK': '港股'
    }

    BENCHMARKS = {
        'US': [
            {"symbol": "SPY.US", "name": "标普500", "role": "index", "weight": 1.0},
            {"symbol": "QQQ.US", "name": "纳指100", "role": "growth", "weight": 1.1},
            {"symbol": "DIA.US", "name": "道琼斯", "role": "value", "weight": 0.9},
            {"symbol": "UVIX.US", "name": "波动率", "role": "volatility", "weight": -1.0},
            {"symbol": "GLD.US", "name": "黄金", "role": "defensive", "weight": -0.45},
            {"symbol": "USO.US", "name": "原油", "role": "commodity", "weight": 0.3}
        ],
        'CN': [
            {"symbol": "510300.SH", "name": "沪深300ETF", "role": "index", "weight": 1.0},
            {"symbol": "510050.SH", "name": "上证50ETF", "role": "value", "weight": 0.9},
            {"symbol": "159915.SZ", "name": "创业板ETF", "role": "growth", "weight": 1.1},
            {"symbol": "518880.SH", "name": "黄金ETF", "role": "defensive", "weight": -0.35}
        ],
        'HK': [
            {"symbol": "2800.HK", "name": "恒生ETF", "role": "index", "weight": 1.0},
            {"symbol": "2822.HK", "name": "中国企业ETF", "role": "china", "weight": 1.0},
            {"symbol": "3033.HK", "name": "恒生科技ETF", "role": "growth", "weight": 1.1},
            {"symbol": "2840.HK", "name": "黄金ETF", "role": "defensive", "weight": -0.35}
        ]
    }

    FALLBACK_TABLES = {
        'US': ['us_etf', 'large_cap_stocks'],
        'CN': ['cn_etf', 'cn_stocks'],
        'HK': ['hk_etf', 'hk_stocks']
    }

    @classmethod
    def ensure_schema(cls):
        DbUtil.execute_sql(
            """
            CREATE TABLE IF NOT EXISTS market_insight_snapshots (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                market VARCHAR(10) NOT NULL,
                status VARCHAR(32) DEFAULT NULL,
                status_text VARCHAR(32) DEFAULT NULL,
                market_score DECIMAL(12, 4) DEFAULT 0,
                regime VARCHAR(32) DEFAULT NULL,
                headline VARCHAR(160) DEFAULT NULL,
                summary TEXT,
                benchmarks_json LONGTEXT,
                source VARCHAR(32) DEFAULT 'scheduler',
                generated_at DATETIME NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_market_generated (market, generated_at),
                INDEX idx_generated (generated_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )

    @classmethod
    def refresh_all_markets(cls, user_id: int = 1, source: str = 'scheduler') -> Dict[str, object]:
        cls.ensure_schema()
        payload = []
        generated_at = datetime.now()

        for market in ['US', 'CN', 'HK']:
            insight = cls.build_market_insight(market, user_id=user_id, generated_at=generated_at)
            cls._save_snapshot(insight, source=source)
            payload.append(insight)

        cls._prune_history()
        return {
            'generated_at': generated_at.strftime('%Y-%m-%d %H:%M:%S'),
            'markets': payload
        }

    @classmethod
    def get_latest_snapshots(cls, user_id: int = 1) -> List[Dict[str, object]]:
        cls.ensure_schema()
        latest_generated_at_row = DbUtil.fetch_one(
            """
            SELECT generated_at
            FROM market_insight_snapshots
            ORDER BY generated_at DESC, id DESC
            LIMIT 1
            """
        ) or {}
        latest_generated_at = latest_generated_at_row.get('generated_at')
        if latest_generated_at:
            snapshots = cls.get_snapshots_by_generated_at(latest_generated_at)
            if snapshots:
                return snapshots

        generated = cls.refresh_all_markets(user_id=user_id, source='bootstrap')
        return generated.get('markets', [])

    @classmethod
    def get_snapshots_by_generated_at(cls, generated_at, market: str = '') -> List[Dict[str, object]]:
        cls.ensure_schema()
        normalized_market = str(market or '').strip().upper()
        sql = """
            SELECT market, status, status_text, market_score, regime, headline, summary, benchmarks_json, generated_at
            FROM market_insight_snapshots
            WHERE generated_at = %s
        """
        params: List[object] = [generated_at]
        if normalized_market:
            sql += " AND market = %s"
            params.append(normalized_market)
        sql += " ORDER BY FIELD(market, 'US', 'CN', 'HK'), id ASC"
        rows = DbUtil.fetch_all(sql, tuple(params)) or []
        return [cls._serialize_snapshot_row(row) for row in rows]

    @classmethod
    def list_snapshot_points(cls, market: str = '', limit: int = 24) -> List[Dict[str, object]]:
        cls.ensure_schema()
        normalized_market = str(market or '').strip().upper()
        sql = """
            SELECT generated_at, COUNT(*) AS market_count, MIN(source) AS source
            FROM market_insight_snapshots
        """
        params: List[object] = []
        if normalized_market:
            sql += " WHERE market = %s"
            params.append(normalized_market)
        sql += """
            GROUP BY generated_at
            ORDER BY generated_at DESC
            LIMIT %s
        """
        params.append(max(1, min(int(limit or 24), 120)))
        rows = DbUtil.fetch_all(sql, tuple(params)) or []
        return [
            {
                'generatedAt': row.get('generated_at').strftime('%Y-%m-%d %H:%M:%S') if row.get('generated_at') else None,
                'marketCount': int(row.get('market_count') or 0),
                'source': row.get('source') or 'scheduler'
            }
            for row in rows
        ]

    @classmethod
    def build_market_insight(cls, market: str, user_id: int = 1, generated_at: Optional[datetime] = None) -> Dict[str, object]:
        market = (market or 'US').upper()
        snapshot_time = generated_at or datetime.now()
        status = cls._get_market_status(market)
        benchmarks = cls._build_benchmark_payload(market, user_id=user_id)
        market_score = cls._calculate_market_score(benchmarks)
        regime = cls._resolve_regime(market_score)
        headline = cls._compose_headline(market, status, regime)
        summary = cls._compose_summary(market, status, regime, benchmarks, market_score)

        return {
            'market': market,
            'marketLabel': cls.MARKET_LABELS.get(market, market),
            'status': status['status'],
            'statusText': status['status_text'],
            'marketScore': round(market_score, 2),
            'regime': regime,
            'headline': headline,
            'summary': summary,
            'benchmarks': benchmarks,
            'generatedAt': snapshot_time.strftime('%Y-%m-%d %H:%M:%S')
        }

    @classmethod
    def _build_benchmark_payload(cls, market: str, user_id: int = 1) -> List[Dict[str, object]]:
        config = cls.BENCHMARKS.get(market, [])
        symbols = [item['symbol'] for item in config]
        quotes = cls._fetch_quotes(symbols, user_id=user_id)

        payload = []
        for item in config:
            quote = quotes.get(item['symbol']) or {}
            payload.append({
                'symbol': item['symbol'],
                'name': item['name'],
                'role': item['role'],
                'price': float(quote.get('price', 0) or 0),
                'changePercent': float(quote.get('changePercent', 0) or 0),
                'volume': int(quote.get('volume', 0) or 0)
            })
        return payload

    @classmethod
    def _fetch_quotes(cls, symbols: List[str], user_id: int = 1) -> Dict[str, Dict[str, object]]:
        manager = get_broker_manager()
        accounts = manager.list_accounts(user_id=user_id) or manager.list_accounts(user_id=1)

        for account in accounts:
            owner_user_id = user_id if manager.account_belongs_to_user(account.get('id'), user_id) else 1
            broker = manager.get_broker(account.get('id'), user_id=owner_user_id)
            if not broker:
                continue

            try:
                if not broker.is_connected and not broker.connect():
                    continue

                raw_quotes = broker.get_quote(symbols) or {}
                quotes = {}
                for symbol in symbols:
                    quote = raw_quotes.get(symbol)
                    if not quote:
                        continue
                    quotes[symbol] = cls._normalize_quote(quote)

                if quotes:
                    return quotes
            except Exception as exc:
                logger.warning('获取市场分析行情失败: account=%s error=%s', account.get('id'), exc)

        return cls._fetch_quotes_from_database(symbols)

    @classmethod
    def _fetch_quotes_from_database(cls, symbols: List[str]) -> Dict[str, Dict[str, object]]:
        quote_map: Dict[str, Dict[str, object]] = {}
        grouped_symbols = {'US': [], 'CN': [], 'HK': []}

        for symbol in symbols:
            if symbol.endswith('.HK'):
                grouped_symbols['HK'].append(symbol)
            elif symbol.endswith('.SH') or symbol.endswith('.SZ'):
                grouped_symbols['CN'].append(symbol)
            else:
                grouped_symbols['US'].append(symbol)

        for market, market_symbols in grouped_symbols.items():
            if not market_symbols:
                continue

            placeholders = ', '.join(['%s'] * len(market_symbols))
            params = tuple(market_symbols)
            for table_name in cls.FALLBACK_TABLES[market]:
                rows = DbUtil.query_all(
                    f"""
                    SELECT symbol, current_price, change_percent, volume
                    FROM {table_name}
                    WHERE symbol IN ({placeholders})
                    """,
                    params
                )
                for row in rows or []:
                    quote_map[row[0]] = {
                        'price': float(row[1] or 0),
                        'changePercent': float(row[2] or 0),
                        'volume': int(row[3] or 0)
                    }

        return quote_map

    @staticmethod
    def _normalize_quote(quote) -> Dict[str, object]:
        if hasattr(quote, 'last_price'):
            return {
                'price': float(getattr(quote, 'last_price', 0) or 0),
                'changePercent': float(getattr(quote, 'change_percent', 0) or 0),
                'volume': int(getattr(quote, 'volume', 0) or 0)
            }

        return {
            'price': float(quote.get('last_price', quote.get('price', 0)) or 0),
            'changePercent': float(quote.get('change_percent', quote.get('changePercent', 0)) or 0),
            'volume': int(quote.get('volume', 0) or 0)
        }

    @classmethod
    def _calculate_market_score(cls, benchmarks: List[Dict[str, object]]) -> float:
        weighted_total = 0.0
        weight_total = 0.0

        for item in benchmarks:
            weight = next(
                (config['weight'] for config in cls.BENCHMARKS.get(cls._market_from_symbol(item['symbol']), []) if config['symbol'] == item['symbol']),
                0.0
            )
            weighted_total += float(item.get('changePercent', 0) or 0) * weight
            weight_total += abs(weight)

        return (weighted_total / weight_total) if weight_total else 0.0

    @staticmethod
    def _resolve_regime(score: float) -> str:
        if score >= 1.2:
            return 'risk_on'
        if score <= -1.2:
            return 'risk_off'
        return 'balanced'

    @classmethod
    def _compose_headline(cls, market: str, status: Dict[str, str], regime: str) -> str:
        regime_text = {
            'risk_on': '风险偏好回升',
            'risk_off': '避险情绪升温',
            'balanced': '市场情绪平衡'
        }.get(regime, '市场情绪平衡')
        return f"{cls.MARKET_LABELS.get(market, market)}{status['status_text']}，{regime_text}"

    @classmethod
    def _compose_summary(
        cls,
        market: str,
        status: Dict[str, str],
        regime: str,
        benchmarks: List[Dict[str, object]],
        market_score: float
    ) -> str:
        positives = [item for item in benchmarks if item.get('changePercent', 0) > 0]
        negatives = [item for item in benchmarks if item.get('changePercent', 0) < 0]
        strongest = max(benchmarks, key=lambda item: item.get('changePercent', 0), default=None)
        weakest = min(benchmarks, key=lambda item: item.get('changePercent', 0), default=None)
        regime_text = {
            'risk_on': '风险偏好回升，适合继续跟踪强势方向',
            'risk_off': '避险偏好增强，仓位和节奏都要更克制',
            'balanced': '市场暂时以震荡为主，适合等确认后再扩大动作'
        }.get(regime, '市场情绪中性')

        summary = f"{cls.MARKET_LABELS.get(market, market)}当前{status['status_text']}，综合情绪分数 {market_score:+.2f}。{regime_text}"
        if strongest:
            summary += f" 领涨参考是 {strongest['name']} {strongest['changePercent']:+.2f}%。"
        if weakest and weakest is not strongest:
            summary += f" 偏弱参考是 {weakest['name']} {weakest['changePercent']:+.2f}%。"
        if positives and negatives:
            summary += f" 上涨基准 {len(positives)} 个，下跌基准 {len(negatives)} 个。"
        return summary

    @classmethod
    def _save_snapshot(cls, insight: Dict[str, object], source: str = 'scheduler'):
        DbUtil.execute_sql(
            """
            INSERT INTO market_insight_snapshots (
                market, status, status_text, market_score, regime, headline, summary, benchmarks_json, source, generated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                insight['market'],
                insight['status'],
                insight['statusText'],
                insight['marketScore'],
                insight['regime'],
                insight['headline'],
                insight['summary'],
                json.dumps(insight.get('benchmarks', []), ensure_ascii=False),
                source,
                insight.get('generatedAt') or datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )
        )

    @classmethod
    def _serialize_snapshot_row(cls, row: Dict[str, object]) -> Dict[str, object]:
        market = row.get('market') or 'US'
        return {
            'market': market,
            'marketLabel': cls.MARKET_LABELS.get(market, market),
            'status': row.get('status') or 'closed',
            'statusText': row.get('status_text') or '已休市',
            'marketScore': float(row.get('market_score') or 0),
            'regime': row.get('regime') or 'balanced',
            'headline': row.get('headline') or '',
            'summary': row.get('summary') or '',
            'benchmarks': json.loads(row.get('benchmarks_json') or '[]'),
            'generatedAt': row.get('generated_at').strftime('%Y-%m-%d %H:%M:%S') if row.get('generated_at') else None
        }

    @staticmethod
    def _prune_history():
        DbUtil.execute_sql(
            """
            DELETE FROM market_insight_snapshots
            WHERE generated_at < DATE_SUB(NOW(), INTERVAL 30 DAY)
            """
        )

    @classmethod
    def _get_market_status(cls, market: str) -> Dict[str, str]:
        if market == 'US':
            tz = pytz.timezone('America/New_York')
            now = datetime.now(tz)
            weekday = now.weekday() < 5
            current_minutes = now.hour * 60 + now.minute
            is_open = weekday and (9 * 60 + 30) <= current_minutes < (16 * 60)
        elif market == 'CN':
            tz = pytz.timezone('Asia/Shanghai')
            now = datetime.now(tz)
            weekday = now.weekday() < 5
            current_minutes = now.hour * 60 + now.minute
            is_open = weekday and (
                (9 * 60 + 30) <= current_minutes < (11 * 60 + 30) or
                (13 * 60) <= current_minutes < (15 * 60)
            )
        else:
            tz = pytz.timezone('Asia/Hong_Kong')
            now = datetime.now(tz)
            weekday = now.weekday() < 5
            current_minutes = now.hour * 60 + now.minute
            is_open = weekday and (
                (9 * 60 + 30) <= current_minutes < (12 * 60) or
                (13 * 60) <= current_minutes < (16 * 60)
            )

        return {
            'status': 'open' if is_open else 'closed',
            'status_text': '交易中' if is_open else '已休市'
        }

    @staticmethod
    def _market_from_symbol(symbol: str) -> str:
        if symbol.endswith('.HK'):
            return 'HK'
        if symbol.endswith('.SH') or symbol.endswith('.SZ'):
            return 'CN'
        return 'US'
