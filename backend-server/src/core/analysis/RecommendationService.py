import json
import math
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Dict, List, Optional

from config.Config import AppConfig
from core.analysis.ai_analyst import AIAnalyst
from utils.DbUtil import DbUtil


class RecommendationService:
    PROFILE_MAP = {
        'growth': '成长型',
        'value': '价值型',
        'dividend': '稳健收益型',
        'momentum': '动量型'
    }

    _schema_ready = False
    _lock = threading.Lock()

    @classmethod
    def ensure_schema(cls):
        if cls._schema_ready:
            return

        with cls._lock:
            if cls._schema_ready:
                return

            from utils.MarketUniverseSync import MarketUniverseSync
            MarketUniverseSync.ensure_schema()

            DbUtil.execute_sql("""
                CREATE TABLE IF NOT EXISTS recommendation_runs (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL DEFAULT 1,
                    profile VARCHAR(32) NOT NULL,
                    summary TEXT,
                    stats_json JSON,
                    candidate_count INT DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_user_profile_created (user_id, profile, created_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            DbUtil.execute_sql("""
                CREATE TABLE IF NOT EXISTS recommendation_items (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    run_id INT NOT NULL,
                    symbol VARCHAR(20) NOT NULL,
                    name VARCHAR(120) DEFAULT NULL,
                    market VARCHAR(10) DEFAULT NULL,
                    asset_type VARCHAR(20) DEFAULT 'stock',
                    profile VARCHAR(32) NOT NULL,
                    score DECIMAL(10, 2) DEFAULT 0,
                    ai_score DECIMAL(10, 2) DEFAULT 0,
                    expected_return DECIMAL(10, 2) DEFAULT 0,
                    risk_level INT DEFAULT 3,
                    confidence INT DEFAULT 0,
                    thesis TEXT,
                    catalysts_json JSON,
                    risks_json JSON,
                    meta_json JSON,
                    is_top_pick TINYINT(1) DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_run_id (run_id),
                    INDEX idx_symbol_profile (symbol, profile)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)

            cls._schema_ready = True

    @classmethod
    def get_latest(cls, profile: str = 'growth', user_id: int = 1) -> Optional[Dict]:
        cls.ensure_schema()
        profile = profile if profile in cls.PROFILE_MAP else 'growth'

        run = DbUtil.fetch_one(
            """
            SELECT id, profile, summary, stats_json, candidate_count, created_at
            FROM recommendation_runs
            WHERE user_id = %s AND profile = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (user_id, profile)
        )
        if not run:
            return None

        items = DbUtil.fetch_all(
            """
            SELECT symbol, name, market, asset_type, score, ai_score, expected_return,
                   risk_level, confidence, thesis, catalysts_json, risks_json, meta_json, is_top_pick
            FROM recommendation_items
            WHERE run_id = %s
            ORDER BY is_top_pick DESC, ai_score DESC, score DESC
            """,
            (run['id'],)
        )

        stats = cls._json_load(run.get('stats_json')) or {}
        return {
            'profile': run['profile'],
            'profile_label': cls.PROFILE_MAP.get(run['profile'], run['profile']),
            'summary': run.get('summary') or '',
            'stats': stats,
            'items': [cls._normalize_item(item) for item in items],
            'generated_at': run['created_at'].strftime('%Y-%m-%d %H:%M:%S') if run.get('created_at') else None,
            'candidate_count': int(run.get('candidate_count') or 0)
        }

    @classmethod
    def refresh(cls, profile: str = 'growth', user_id: int = 1, force: bool = False) -> Dict:
        cls.ensure_schema()
        profile = profile if profile in cls.PROFILE_MAP else 'growth'

        if not force:
            latest = cls.get_latest(profile, user_id=user_id)
            if latest and cls._minutes_since(latest.get('generated_at')) < cls._refresh_interval_minutes():
                return latest

        candidates = cls._collect_candidates(profile)
        if not candidates:
            generated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            empty_result = {
                'profile': profile,
                'profile_label': cls.PROFILE_MAP.get(profile, profile),
                'summary': '当前暂无可用推荐，请先同步市场与 ETF 全量数据。',
                'stats': cls._build_stats([]),
                'items': [],
                'generated_at': generated_at,
                'candidate_count': 0
            }
            cls._save_run(user_id, profile, empty_result['summary'], empty_result['stats'], [])
            return empty_result

        enriched_items = cls._enrich_with_ai(profile, candidates[:12], user_id=user_id)
        summary = cls._generate_summary(profile, enriched_items, user_id=user_id)
        stats = cls._build_stats(enriched_items)
        generated_at = datetime.now()

        run_id = cls._save_run(user_id, profile, summary, stats, enriched_items)

        return {
            'run_id': run_id,
            'profile': profile,
            'profile_label': cls.PROFILE_MAP.get(profile, profile),
            'summary': summary,
            'stats': stats,
            'items': enriched_items,
            'generated_at': generated_at.strftime('%Y-%m-%d %H:%M:%S'),
            'candidate_count': len(enriched_items)
        }

    @classmethod
    def refresh_all_profiles(cls, user_id: int = 1):
        for profile in cls.PROFILE_MAP:
            try:
                cls.refresh(profile=profile, user_id=user_id, force=True)
            except Exception:
                continue

    @classmethod
    def _collect_candidates(cls, profile: str) -> List[Dict]:
        sources = [
            ('US', 'large_cap_stocks', 'company_name', 'stock', 22),
            ('CN', 'cn_stocks', 'name', 'stock', 22),
            ('HK', 'hk_stocks', 'name', 'stock', 22),
            ('US', 'us_etf', 'etf_name', 'etf', 14),
            ('CN', 'cn_etf', 'etf_name', 'etf', 14),
            ('HK', 'hk_etf', 'etf_name', 'etf', 14)
        ]

        rows: List[Dict] = []
        for market, table, name_field, asset_type, limit in sources:
            rows.extend(cls._query_market_table(market, table, name_field, asset_type, profile, limit))

        deduped: Dict[str, Dict] = {}
        for item in rows:
            existing = deduped.get(item['symbol'])
            if not existing or item['score'] > existing['score']:
                deduped[item['symbol']] = item

        return sorted(deduped.values(), key=lambda item: (item['score'], item['market_cap']), reverse=True)

    @classmethod
    def _query_market_table(
        cls,
        market: str,
        table: str,
        name_field: str,
        asset_type: str,
        profile: str,
        limit: int
    ) -> List[Dict]:
        exists = DbUtil.query_one(
            "SELECT 1 FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = %s",
            (table,)
        )
        if not exists:
            return []

        order_by = cls._profile_order_by(profile)
        rows = DbUtil.fetch_all(
            f"""
            SELECT symbol, {name_field} AS name, market,
                   current_price, change_percent, volume, market_cap, pe_ratio
            FROM {table}
            WHERE is_active = 1
            ORDER BY {order_by}
            LIMIT %s
            """,
            (limit,)
        ) or []

        normalized = []
        for row in rows:
            normalized.append(cls._score_candidate({
                'symbol': row.get('symbol'),
                'name': row.get('name') or row.get('symbol'),
                'market': row.get('market') or market,
                'asset_type': asset_type,
                'price': float(row.get('current_price') or 0),
                'change_percent': float(row.get('change_percent') or 0),
                'volume': float(row.get('volume') or 0),
                'market_cap': float(row.get('market_cap') or 0),
                'pe': float(row.get('pe_ratio') or 0) if row.get('pe_ratio') is not None else None
            }, profile))

        return normalized

    @classmethod
    def _profile_order_by(cls, profile: str) -> str:
        if profile == 'growth':
            return "market_cap DESC, change_percent DESC"
        if profile == 'value':
            return "CASE WHEN pe_ratio > 0 THEN pe_ratio ELSE 999999 END ASC, market_cap DESC"
        if profile == 'dividend':
            return "market_cap DESC, volume DESC"
        return "change_percent DESC, volume DESC"

    @classmethod
    def _score_candidate(cls, candidate: Dict, profile: str) -> Dict:
        market_cap = candidate.get('market_cap') or 0
        volume = candidate.get('volume') or 0
        change = candidate.get('change_percent') or 0
        pe = candidate.get('pe') if candidate.get('pe') is not None else 0

        size_score = min(25, math.log10(max(market_cap, 1)) * 2.2)
        liquidity_score = min(20, math.log10(max(volume, 1)) * 2.8)
        momentum_score = max(0, min(30, change * 2.4 + 15))
        value_score = 18 if pe and 0 < pe < 20 else 10 if pe and pe < 35 else 6
        stability_score = 14 if candidate.get('asset_type') == 'etf' else 8

        profile_boost = {
            'growth': momentum_score * 0.55 + size_score * 0.25 + liquidity_score * 0.20,
            'value': value_score * 2.2 + size_score * 0.35 + liquidity_score * 0.15,
            'dividend': stability_score * 2.1 + size_score * 0.4 + value_score * 0.6,
            'momentum': momentum_score * 0.7 + liquidity_score * 0.2 + size_score * 0.1
        }
        base_score = profile_boost.get(profile, 50)
        candidate['score'] = round(min(99, base_score), 2)
        candidate['expected_return'] = round(max(4, min(28, 6 + abs(change) * 1.6 + candidate['score'] * 0.12)), 2)
        candidate['risk_level'] = max(1, min(5, int(round(2 + abs(change) / 2.6 + (0 if candidate['asset_type'] == 'etf' else 0.8)))))
        candidate['confidence'] = int(max(58, min(96, 55 + candidate['score'] * 0.35)))
        return candidate

    @classmethod
    def _enrich_with_ai(cls, profile: str, candidates: List[Dict], user_id: int = 1) -> List[Dict]:
        if not candidates:
            return []

        enriched = []
        with ThreadPoolExecutor(max_workers=4) as executor:
            future_map = {
                executor.submit(cls._ai_enrich_candidate, profile, candidate, user_id): candidate
                for candidate in candidates
            }
            for future in as_completed(future_map):
                try:
                    enriched.append(future.result())
                except Exception:
                    enriched.append(future_map[future])

        enriched.sort(key=lambda item: (item.get('ai_score', 0), item.get('score', 0)), reverse=True)
        for index, item in enumerate(enriched):
            item['is_top_pick'] = index < 3
        return enriched

    @classmethod
    def _ai_enrich_candidate(cls, profile: str, candidate: Dict, user_id: int = 1) -> Dict:
        prompt = f"""你是量化投研助理，请对下面的标的输出极简推荐结论。

必须按以下格式返回：
推荐摘要: ...
核心催化: 1)... 2)... 3)...
主要风险: 1)... 2)...
综合评分: 0-100
置信度: 0-100

标的: {candidate['name']} ({candidate['symbol']})
市场: {candidate['market']}
类型: {candidate['asset_type']}
推荐风格: {cls.PROFILE_MAP.get(profile, profile)}
当前价: {candidate.get('price', 0):.2f}
涨跌幅: {candidate.get('change_percent', 0):+.2f}%
成交量: {candidate.get('volume', 0):.0f}
市值: {candidate.get('market_cap', 0):.0f}
PE: {candidate.get('pe') if candidate.get('pe') is not None else 'N/A'}
量化基础分: {candidate['score']}
预估收益: {candidate['expected_return']}%
风险等级: {candidate['risk_level']}
"""
        text = AIAnalyst.get_decision(None, prompt, task='recommend_brief', user_id=user_id)
        usable = cls._is_usable_ai_text(text)
        summary = cls._extract_field(text, '推荐摘要') if usable else ''
        catalysts = cls._extract_list(text, '核心催化') if usable else []
        risks = cls._extract_list(text, '主要风险') if usable else []
        ai_score = cls._extract_number(text, '综合评分', candidate['score']) if usable else candidate['score']
        confidence = int(cls._extract_number(text, '置信度', candidate['confidence'])) if usable else candidate['confidence']

        candidate.update({
            'thesis': summary,
            'catalysts': catalysts[:3],
            'risks': risks[:2],
            'ai_score': round((candidate['score'] * 0.55) + (float(ai_score) * 0.45), 2) if usable else round(candidate['score'], 2),
            'confidence': max(candidate['confidence'], min(98, confidence)) if usable else int(candidate['confidence']),
            'ai_generated': usable,
            'horizon': '中线' if profile in {'growth', 'value'} else '短线' if profile == 'momentum' else '稳健'
        })
        return candidate

    @classmethod
    def _generate_summary(cls, profile: str, items: List[Dict], user_id: int = 1) -> str:
        if not items:
            return '当前暂无可用推荐，请先同步市场数据。'

        top_items = items[:6]
        lines = []
        for item in top_items:
            lines.append(
                f"- {item['symbol']} {item['market']} {item['asset_type']} | "
                f"AI评分 {item['ai_score']:.2f} | 预期收益 {item['expected_return']:.2f}% | 风险 {item['risk_level']}/5"
            )

        prompt = f"""请基于以下候选池，输出一段 120 字以内的投资组合建议，强调仓位节奏、市场分布和 ETF/股票搭配。

策略风格: {cls.PROFILE_MAP.get(profile, profile)}
候选列表:
{chr(10).join(lines)}
"""
        text = AIAnalyst.get_decision(None, prompt, task='recommend_summary', user_id=user_id)
        normalized = (text or '').strip()
        if not cls._is_usable_ai_text(normalized):
            return 'AI 组合摘要当前不可用，以下列表仅包含真实量化筛选结果与市场快照。'
        return normalized

    @classmethod
    def _build_stats(cls, items: List[Dict]) -> Dict:
        if not items:
            return {
                'total': 0,
                'top_picks': 0,
                'avg_return': 0,
                'avg_score': 0,
                'risk_alerts': 0,
                'markets': {},
                'assets': {},
                'next_refresh_minutes': cls._refresh_interval_minutes()
            }

        total = len(items)
        avg_return = round(sum(item['expected_return'] for item in items) / total, 2)
        avg_score = round(sum(item.get('ai_score', item['score']) for item in items) / total, 2)
        markets: Dict[str, int] = {}
        assets: Dict[str, int] = {}
        for item in items:
            markets[item['market']] = markets.get(item['market'], 0) + 1
            assets[item['asset_type']] = assets.get(item['asset_type'], 0) + 1

        return {
            'total': total,
            'top_picks': len([item for item in items if item.get('is_top_pick')]),
            'avg_return': avg_return,
            'avg_score': avg_score,
            'risk_alerts': len([item for item in items if item.get('risk_level', 0) >= 4]),
            'markets': markets,
            'assets': assets,
            'next_refresh_minutes': cls._refresh_interval_minutes()
        }

    @classmethod
    def _save_run(cls, user_id: int, profile: str, summary: str, stats: Dict, items: List[Dict]) -> int:
        DbUtil.execute_sql(
            """
            INSERT INTO recommendation_runs (user_id, profile, summary, stats_json, candidate_count)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (user_id, profile, summary, json.dumps(stats, ensure_ascii=False), len(items))
        )
        run_row = DbUtil.query_one("SELECT LAST_INSERT_ID()")
        run_id = int(run_row[0]) if run_row else 0

        for item in items:
            DbUtil.execute_sql(
                """
                INSERT INTO recommendation_items (
                    run_id, symbol, name, market, asset_type, profile, score, ai_score,
                    expected_return, risk_level, confidence, thesis, catalysts_json,
                    risks_json, meta_json, is_top_pick
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    run_id,
                    item['symbol'],
                    item['name'],
                    item['market'],
                    item['asset_type'],
                    profile,
                    item['score'],
                    item.get('ai_score', item['score']),
                    item['expected_return'],
                    item['risk_level'],
                    item['confidence'],
                    item.get('thesis', ''),
                    json.dumps(item.get('catalysts', []), ensure_ascii=False),
                    json.dumps(item.get('risks', []), ensure_ascii=False),
                    json.dumps({
                        'price': item.get('price'),
                        'change_percent': item.get('change_percent'),
                        'market_cap': item.get('market_cap'),
                        'volume': item.get('volume'),
                        'horizon': item.get('horizon')
                    }, ensure_ascii=False),
                    int(bool(item.get('is_top_pick')))
                )
            )

        return run_id

    @classmethod
    def _normalize_item(cls, row: Dict) -> Dict:
        catalysts = cls._json_load(row.get('catalysts_json')) or []
        risks = cls._json_load(row.get('risks_json')) or []
        meta = cls._json_load(row.get('meta_json')) or {}
        return {
            'symbol': row.get('symbol'),
            'name': row.get('name') or row.get('symbol'),
            'market': row.get('market'),
            'assetType': row.get('asset_type') or 'stock',
            'score': float(row.get('score') or 0),
            'aiScore': float(row.get('ai_score') or 0),
            'expectedReturn': float(row.get('expected_return') or 0),
            'riskLevel': int(row.get('risk_level') or 3),
            'confidence': int(row.get('confidence') or 0),
            'aiGenerated': bool(row.get('thesis')),
            'thesis': row.get('thesis') or '',
            'reasons': catalysts,
            'risks': risks,
            'isTopPick': bool(row.get('is_top_pick')),
            'price': float(meta.get('price') or 0),
            'changePercent': float(meta.get('change_percent') or 0),
            'marketCap': float(meta.get('market_cap') or 0),
            'volume': float(meta.get('volume') or 0),
            'horizon': meta.get('horizon') or '中线'
        }

    @staticmethod
    def _extract_field(text: str, label: str) -> str:
        for line in (text or '').splitlines():
            normalized = line.replace('：', ':')
            if label in normalized and ':' in normalized:
                return normalized.split(':', 1)[-1].strip()
        return ''

    @staticmethod
    def _extract_list(text: str, label: str) -> List[str]:
        target = RecommendationService._extract_field(text, label)
        if not target:
            return []

        normalized = target.replace('；', ';')
        parts = [part.strip(" 1234567890).、") for part in normalized.split(';') if part.strip()]
        if len(parts) <= 1:
            parts = [part.strip(" 1234567890).、") for part in normalized.split(')') if part.strip()]
        return [part for part in parts if part]

    @staticmethod
    def _extract_number(text: str, label: str, default: float) -> float:
        value = RecommendationService._extract_field(text, label)
        try:
            return float(str(value).replace('%', '').strip())
        except (TypeError, ValueError):
            return float(default)

    @staticmethod
    def _is_usable_ai_text(text: str) -> bool:
        normalized = str(text or '').strip()
        if not normalized:
            return False
        if normalized.upper().startswith('ERROR'):
            return False
        matched_labels = sum(1 for marker in ['推荐摘要', '核心催化', '主要风险', '综合评分', '置信度'] if marker in normalized)
        if matched_labels < 3:
            return False
        lowered = normalized.lower()
        if 'the user' in lowered or 'must' in lowered or 'format' in lowered:
            return False
        return True

    @staticmethod
    def _refresh_interval_minutes() -> int:
        return max(15, int(AppConfig.get('RECOMMENDATION_REFRESH_INTERVAL', default=1800) or 1800) // 60)

    @staticmethod
    def _minutes_since(timestamp: Optional[str]) -> int:
        if not timestamp:
            return 999999
        try:
            dt = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
            return int((datetime.now() - dt).total_seconds() // 60)
        except ValueError:
            return 999999

    @staticmethod
    def _json_load(value):
        if not value:
            return None
        if isinstance(value, (list, dict)):
            return value
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return None
