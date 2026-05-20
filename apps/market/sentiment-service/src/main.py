from __future__ import annotations

import json
import os
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from fastapi import Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

REFACTOR_ROOT = Path(__file__).resolve().parents[4]
if str(REFACTOR_ROOT) not in sys.path:
    sys.path.insert(0, str(REFACTOR_ROOT))

from apps.market.module_shared import (
    DailySymbolTrendScanService,
    HistoricalMarketDataService,
    SymbolContentCacheService,
    build_alert,
    build_dependency_status,
    build_health_payload,
    create_service_app,
    get_current_session,
    get_persistence_manager,
    summarize_status,
)
from config.Config import AppConfig
from core.analysis.FinanceBriefingService import FinanceBriefingService
from core.analysis.RecommendationService import RecommendationService
from apps.intelligence.module_shared import build_market_snapshot


SENTIMENT_SIGNAL_WORDS = {
    "positive": [
        "beat",
        "bullish",
        "growth",
        "rebound",
        "upgrade",
        "breakout",
        "strong",
        "surge",
        "利好",
        "增长",
        "反弹",
        "看多",
        "上调",
        "突破",
        "强势",
    ],
    "negative": [
        "downgrade",
        "miss",
        "lawsuit",
        "fraud",
        "probe",
        "investigation",
        "warning",
        "selloff",
        "risk",
        "利空",
        "下调",
        "诉讼",
        "调查",
        "警告",
        "跳水",
        "风险",
    ],
}

RISK_KEYWORD_BUCKETS = {
    "监管": ["regulation", "sec", "antitrust", "监管", "审查", "问询"],
    "盈利": ["earnings", "guidance", "miss", "profit", "财报", "盈利", "指引"],
    "流动性": ["liquidity", "funding", "debt", "现金流", "融资", "债务"],
    "波动": ["selloff", "volatility", "drawdown", "波动", "回撤", "跳水"],
    "事件": ["lawsuit", "hack", "outage", "诉讼", "中断", "事故"],
}

MARKETS = ("US", "CN", "HK")

GITHUB_ADOPTION_CANDIDATES = [
    {
        "name": "FinNLP",
        "repo": "AI4Finance-Foundation/FinNLP",
        "url": "https://github.com/AI4Finance-Foundation/FinNLP",
        "license": "MIT",
        "role": "collector",
        "fit": "金融新闻、公告、社媒数据接入参考，中文来源覆盖更好",
        "adoption": "reference-adapter",
        "risk": "不直接 vendor，先按现有 sentiment-service contract 自研采集适配",
    },
    {
        "name": "FinBERT",
        "repo": "ProsusAI/finBERT",
        "url": "https://github.com/ProsusAI/finBERT",
        "license": "Apache-2.0",
        "role": "sentiment-model",
        "fit": "英文金融新闻正/负/中性轻量分类",
        "adoption": "optional-model",
        "risk": "MVP 不新增模型依赖，先保留为可选离线增强",
    },
    {
        "name": "FinABSA",
        "repo": "guijinSON/FinABSA",
        "url": "https://github.com/guijinSON/FinABSA",
        "license": "Apache-2.0",
        "role": "aspect-sentiment",
        "fit": "实体/方面级情绪，可补标的局部舆情",
        "adoption": "optional-model",
        "risk": "活跃度较低，仅作为 aspect-level 参考",
    },
    {
        "name": "FinGPT",
        "repo": "AI4Finance-Foundation/FinGPT",
        "url": "https://github.com/AI4Finance-Foundation/FinGPT",
        "license": "MIT",
        "role": "financial-llm",
        "fit": "中文金融 LLM 和任务数据集参考",
        "adoption": "reference-model-layer",
        "risk": "当前平台已复用 sub2api/gpt-5.4/gpt-5.5，不先引入新模型栈",
    },
    {
        "name": "AINewsTracker",
        "repo": "AlgoETS/AINewsTracker",
        "url": "https://github.com/AlgoETS/AINewsTracker",
        "license": "MIT",
        "role": "service-reference",
        "fit": "FastAPI 金融新闻情绪服务边界参考",
        "adoption": "reference-architecture",
        "risk": "非中文金融优先，不直接复制实现",
    },
    {
        "name": "TickerPulse AI / BettaFish",
        "repo": "multiple GPL reference projects",
        "url": "https://github.com/amitpatole/tickerpulse-ai",
        "license": "GPL family",
        "role": "architecture-only",
        "fit": "多源舆情和多 Agent 信息架构参考",
        "adoption": "do-not-vendor",
        "risk": "GPL 许可证与重型全栈耦合，不进入生产代码",
    },
]


@dataclass
class SentimentItem:
    symbol: str
    market: str
    score: float
    label: str
    confidence: float
    heat: float
    trend_direction: str
    trend_strength: float
    risk_level: str
    risk_keywords: List[str]
    driver_headlines: List[str]
    quant_fields: Dict[str, Any]
    recommendation_ref: Optional[Dict[str, Any]]
    latest_analysis_ref: Optional[Dict[str, Any]]


bootstrap_app = create_service_app(
    title="Refactor V2 Sentiment Service",
    version="0.2.0",
    description="Read-only sentiment aggregation service for news, discussion and quant consumption.",
)
app: FastAPI = bootstrap_app

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _service_port() -> int:
    return int(os.getenv("REF_SENTIMENT_SERVICE_PORT", "8106"))


def _normalize_market(value: Optional[str]) -> Optional[str]:
    normalized = str(value or "").strip().upper()
    return normalized if normalized in MARKETS else None


def _normalize_symbol(value: str) -> str:
    return HistoricalMarketDataService.normalize_symbol(value)


def _parse_json_like(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _payload_of(item: Dict[str, Any]) -> Dict[str, Any]:
    payload = item.get("payload")
    if payload is None:
        payload = item.get("payload_json")
    return _parse_json_like(payload)


def _coerce_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    for candidate in (text, text.replace("Z", "+00:00"), text.replace(" ", "T")):
        try:
            return datetime.fromisoformat(candidate)
        except Exception:
            continue
    return None


def _format_datetime(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if isinstance(value, datetime) else None


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _recent_hours_weight(value: Optional[datetime], *, horizon_hours: int = 72) -> float:
    if not value:
        return 0.2
    age_seconds = max((datetime.now(value.tzinfo) - value).total_seconds(), 0.0)
    horizon_seconds = max(horizon_hours, 1) * 3600
    ratio = max(0.0, 1.0 - min(age_seconds / horizon_seconds, 1.0))
    return round(0.2 + ratio * 0.8, 4)


def _tokenize_text(*parts: Any) -> str:
    return " ".join(str(part or "").strip().lower() for part in parts if str(part or "").strip())


def _match_keywords(text: str, candidates: Iterable[str]) -> List[str]:
    lowered = str(text or "").lower()
    return [keyword for keyword in candidates if keyword and keyword.lower() in lowered]


def _risk_keywords_from_text(text: str) -> List[str]:
    matched: List[str] = []
    for label, candidates in RISK_KEYWORD_BUCKETS.items():
        if _match_keywords(text, candidates):
            matched.append(label)
    return matched


def _score_content_item(item: Dict[str, Any]) -> Dict[str, Any]:
    headline = str(item.get("headline") or item.get("title") or "").strip()
    summary = str(item.get("summary") or item.get("description") or "").strip()
    source_text = _tokenize_text(headline, summary)
    positive_hits = _match_keywords(source_text, SENTIMENT_SIGNAL_WORDS["positive"])
    negative_hits = _match_keywords(source_text, SENTIMENT_SIGNAL_WORDS["negative"])
    signal_score = (len(positive_hits) - len(negative_hits)) / max(len(positive_hits) + len(negative_hits), 1)
    generated_at = _coerce_datetime(
        item.get("generatedAt")
        or item.get("published_at")
        or item.get("publishedAt")
        or item.get("time")
    )
    recency_weight = _recent_hours_weight(generated_at)
    weighted_score = max(-1.0, min(1.0, signal_score * recency_weight))
    return {
        "headline": headline,
        "summary": summary,
        "generatedAt": _format_datetime(generated_at),
        "sourceName": item.get("sourceName") or item.get("source_name") or "system",
        "sourceType": item.get("briefingType") or item.get("content_type") or item.get("type") or "news",
        "weight": recency_weight,
        "score": weighted_score,
        "positiveHits": positive_hits,
        "negativeHits": negative_hits,
        "riskKeywords": _risk_keywords_from_text(source_text),
        "symbol": str(_payload_of(item).get("symbol") or item.get("symbol") or "").strip().upper(),
        "market": str(item.get("market") or "").strip().upper(),
        "url": item.get("sourceLink") or item.get("source_link") or item.get("url"),
    }


def _load_symbol_content(symbol: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for content_type in ("news", "topics", "announcements"):
        rows.extend(SymbolContentCacheService.get_cached(symbol=symbol, content_type=content_type, limit=8))
    return rows


def _build_analysis_reference(raw_history: Any) -> Optional[Dict[str, Any]]:
    if not raw_history:
        return None
    history_dict = raw_history.to_dict() if hasattr(raw_history, "to_dict") else dict(raw_history)
    indicators = _parse_json_like(history_dict.get("indicators"))
    raw_sentiment_text = " ".join(
        [
            str(history_dict.get("llama_decision") or ""),
            str(history_dict.get("llama_analysis") or ""),
            str(history_dict.get("gemma_analysis") or ""),
            str(history_dict.get("deepseek_analysis") or ""),
        ]
    ).strip()
    risk_keywords = _risk_keywords_from_text(raw_sentiment_text)
    return {
        "analysisTime": history_dict.get("analysis_time"),
        "finalDecision": history_dict.get("final_decision"),
        "finalConfidence": _safe_float(history_dict.get("final_confidence")),
        "sentimentNarrative": str(history_dict.get("llama_analysis") or "")[:480],
        "riskKeywords": risk_keywords,
        "indicatorKeys": sorted(indicators.keys())[:12],
    }


def _build_quant_fields(
    *,
    item_scores: List[Dict[str, Any]],
    trend_scan: Optional[Dict[str, Any]],
    analysis_ref: Optional[Dict[str, Any]],
    recommendation_ref: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    score_values = [entry.get("score", 0.0) for entry in item_scores]
    mean_score = sum(score_values) / len(score_values) if score_values else 0.0
    negative_ratio = (
        len([value for value in score_values if value < -0.1]) / len(score_values)
        if score_values
        else 0.0
    )
    positive_ratio = (
        len([value for value in score_values if value > 0.1]) / len(score_values)
        if score_values
        else 0.0
    )
    confidence = analysis_ref.get("finalConfidence") if analysis_ref else 0.0
    ai_bias = (
        "bullish"
        if str(analysis_ref.get("finalDecision") or "").find("买") >= 0
        else "bearish"
        if str(analysis_ref.get("finalDecision") or "").find("卖") >= 0
        else "neutral"
    ) if analysis_ref else "neutral"
    trend_direction = str(trend_scan.get("trendDirection") or trend_scan.get("trend_direction") or "sideways") if trend_scan else "sideways"
    trend_strength = _safe_float(trend_scan.get("trendStrength") or trend_scan.get("trend_strength")) if trend_scan else 0.0
    technical_score = _safe_float(trend_scan.get("technicalScore") or trend_scan.get("technical_score")) if trend_scan else 0.0
    expected_return = _safe_float(recommendation_ref.get("expectedReturn")) if recommendation_ref else 0.0
    return {
        "sentiment_score": round(mean_score, 4),
        "positive_ratio": round(positive_ratio, 4),
        "negative_ratio": round(negative_ratio, 4),
        "heat_score": round(min(len(item_scores) / 8, 1.0), 4),
        "trend_direction": trend_direction,
        "trend_strength": round(trend_strength, 4),
        "technical_score": round(technical_score, 2),
        "ai_confidence": round(_safe_float(confidence), 2),
        "ai_bias": ai_bias,
        "expected_return": round(expected_return, 4),
        "recommended": bool(recommendation_ref),
    }


def _sentiment_label(score: float) -> str:
    if score >= 0.35:
        return "positive"
    if score <= -0.35:
        return "negative"
    return "neutral"


def _heat_from_items(items: List[Dict[str, Any]], trend_scan: Optional[Dict[str, Any]]) -> float:
    item_weight = sum(_safe_float(entry.get("weight"), 0.0) for entry in items)
    technical_score = _safe_float(
        (trend_scan or {}).get("technicalScore") or (trend_scan or {}).get("technical_score"),
        0.0,
    )
    raw = min(item_weight / 4.0, 1.0) * 0.6 + min(technical_score / 100.0, 1.0) * 0.4
    return round(raw, 4)


def _build_recommendation_map(user_id: int) -> Dict[str, Dict[str, Any]]:
    mapping: Dict[str, Dict[str, Any]] = {}
    for profile in ("growth", "value", "dividend", "momentum"):
        payload = RecommendationService.get_latest(profile=profile, user_id=user_id) or {}
        for item in payload.get("items") or []:
            symbol = _normalize_symbol(item.get("symbol") or "")
            if not symbol:
                continue
            existing = mapping.get(symbol)
            ai_score = _safe_float(item.get("ai_score") or item.get("aiScore"))
            if existing and ai_score <= _safe_float(existing.get("aiScore")):
                continue
            mapping[symbol] = {
                "profile": profile,
                "profileLabel": payload.get("profile_label") or profile,
                "symbol": symbol,
                "name": item.get("name") or symbol,
                "market": item.get("market"),
                "aiScore": ai_score,
                "confidence": _safe_float(item.get("confidence")),
                "expectedReturn": _safe_float(item.get("expected_return") or item.get("expectedReturn")),
                "thesis": str(item.get("thesis") or "")[:320],
            }
    return mapping


def _build_symbol_sentiment(
    symbol: str,
    user_id: int,
    recommendation_map: Optional[Dict[str, Dict[str, Any]]] = None,
) -> SentimentItem:
    normalized_symbol = _normalize_symbol(symbol)
    market = HistoricalMarketDataService.detect_market(normalized_symbol).upper()
    finance_items = [
        entry for entry in FinanceBriefingService.get_latest(limit=40, market=market)
        if str(_payload_of(entry).get("symbol") or "").strip().upper() == normalized_symbol
    ]
    cache_items = _load_symbol_content(normalized_symbol)
    scored_items = [_score_content_item(entry) for entry in [*finance_items, *cache_items]]

    trend_scan = DailySymbolTrendScanService.get_latest_for_symbol(normalized_symbol)
    persistence = get_persistence_manager()
    latest_history = persistence.get_latest_ai_analysis(normalized_symbol, user_id=user_id)
    analysis_ref = _build_analysis_reference(latest_history)
    recommendation_ref = (recommendation_map or _build_recommendation_map(user_id)).get(normalized_symbol)

    if trend_scan:
        trend_text = _tokenize_text(trend_scan.get("headline"), trend_scan.get("summary"), trend_scan.get("analysisText"))
        scored_items.append(
            {
                "headline": str(trend_scan.get("headline") or f"{normalized_symbol} 趋势扫描"),
                "summary": str(trend_scan.get("summary") or ""),
                "generatedAt": trend_scan.get("analysisDate") or trend_scan.get("analysis_date"),
                "sourceName": "trend-scan",
                "sourceType": "trend-scan",
                "weight": 0.8,
                "score": (
                    0.6
                    if str(trend_scan.get("trendDirection") or "").lower() in {"up", "bullish"}
                    else -0.6
                    if str(trend_scan.get("trendDirection") or "").lower() in {"down", "bearish"}
                    else 0.0
                ),
                "positiveHits": _match_keywords(trend_text, SENTIMENT_SIGNAL_WORDS["positive"]),
                "negativeHits": _match_keywords(trend_text, SENTIMENT_SIGNAL_WORDS["negative"]),
                "riskKeywords": _risk_keywords_from_text(trend_text),
                "symbol": normalized_symbol,
                "market": market,
                "url": None,
            }
        )

    score_values = [entry.get("score", 0.0) for entry in scored_items]
    score = round(sum(score_values) / len(score_values), 4) if score_values else 0.0
    confidence = round(
        min(
            0.35
            + len(scored_items) * 0.07
            + (0.18 if analysis_ref else 0.0)
            + (0.15 if trend_scan else 0.0),
            0.96,
        ),
        4,
    )
    risk_keywords = sorted({keyword for item in scored_items for keyword in item.get("riskKeywords", [])})
    driver_headlines = [item.get("headline") for item in scored_items if item.get("headline")][:4]
    heat = _heat_from_items(scored_items, trend_scan)
    quant_fields = _build_quant_fields(
        item_scores=scored_items,
        trend_scan=trend_scan,
        analysis_ref=analysis_ref,
        recommendation_ref=recommendation_ref,
    )
    trend_direction = str((trend_scan or {}).get("trendDirection") or (trend_scan or {}).get("trend_direction") or "sideways")
    trend_strength = _safe_float((trend_scan or {}).get("trendStrength") or (trend_scan or {}).get("trend_strength"))
    risk_level = str((trend_scan or {}).get("riskLevel") or (trend_scan or {}).get("risk_level") or ("high" if len(risk_keywords) >= 2 else "medium" if risk_keywords else "low"))
    return SentimentItem(
        symbol=normalized_symbol,
        market=market,
        score=score,
        label=_sentiment_label(score),
        confidence=confidence,
        heat=heat,
        trend_direction=trend_direction,
        trend_strength=round(trend_strength, 4),
        risk_level=risk_level,
        risk_keywords=risk_keywords,
        driver_headlines=driver_headlines,
        quant_fields=quant_fields,
        recommendation_ref=recommendation_ref,
        latest_analysis_ref=analysis_ref,
    )


def _market_watchlist(market: str) -> List[str]:
    return {
        "US": ["NVDA.US", "AAPL.US", "MSFT.US", "TSLA.US"],
        "CN": ["600519.SH", "300750.SZ", "601318.SH", "000858.SZ"],
        "HK": ["0700.HK", "9988.HK", "1810.HK", "3690.HK"],
    }.get(market, [])


def _build_market_summary(
    market: str,
    user_id: int,
    recommendation_map: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    symbols = _market_watchlist(market)
    active_recommendation_map = recommendation_map or _build_recommendation_map(user_id)
    items = [_build_symbol_sentiment(symbol, user_id, active_recommendation_map) for symbol in symbols]
    score_values = [item.score for item in items]
    avg_score = round(sum(score_values) / len(score_values), 4) if score_values else 0.0
    positive_count = len([item for item in items if item.label == "positive"])
    negative_count = len([item for item in items if item.label == "negative"])
    risk_counts = Counter(keyword for item in items for keyword in item.risk_keywords)
    top_risks = [keyword for keyword, _ in risk_counts.most_common(4)]
    return {
        "market": market,
        "sentimentScore": avg_score,
        "sentimentLabel": _sentiment_label(avg_score),
        "positiveCount": positive_count,
        "negativeCount": negative_count,
        "heat": round(sum(item.heat for item in items) / len(items), 4) if items else 0.0,
        "topRiskKeywords": top_risks,
        "leaders": [asdict(item) for item in sorted(items, key=lambda item: item.heat, reverse=True)[:3]],
    }


def _build_risk_word_cloud(items: List[SentimentItem]) -> List[Dict[str, Any]]:
    counts = Counter(keyword for item in items for keyword in item.risk_keywords)
    return [
        {"keyword": keyword, "count": count}
        for keyword, count in counts.most_common(8)
    ]


def _build_ai_config_contract() -> Dict[str, Any]:
    return {
        "provider": AppConfig.get("AI_PROVIDER"),
        "baseUrl": AppConfig.get("AI_BASE_URL"),
        "chatCompletionsUrl": AppConfig.get("AI_URL"),
        "apiStyle": AppConfig.get("AI_API_STYLE"),
        "models": {
            "default": AppConfig.get("AI_MODEL"),
            "scanPulse": AppConfig.get("AI_MODEL_SCAN_PULSE"),
            "scanFast": AppConfig.get("AI_MODEL_SCAN_FAST"),
            "scanRisk": AppConfig.get("AI_MODEL_SCAN_RISK"),
            "scanFinal": AppConfig.get("AI_MODEL_SCAN_FINAL"),
            "trendBatch": AppConfig.get("AI_MODEL_TREND_BATCH"),
            "recommendBrief": AppConfig.get("AI_MODEL_RECOMMEND_BRIEF"),
            "recommendSummary": AppConfig.get("AI_MODEL_RECOMMEND_SUMMARY"),
        },
        "source": "LONGBRIDGE_AI_*",
        "note": "舆情 AI 能力必须复用现有 sub2api / OpenAI-compatible 配置，不新增独立密钥体系。",
    }


def _build_github_adoption_contract() -> Dict[str, Any]:
    return {
        "decision": "native-contract-first",
        "recommendedStack": ["FinNLP collectors", "FinBERT/FinABSA optional scoring", "sub2api gpt-5.4/gpt-5.5 synthesis"],
        "sourcePolicy": "MIT/Apache reference only; GPL projects are architecture references and must not be vendored",
        "aiModelPolicy": "reuse LONGBRIDGE_AI_* / sub2api; no new AI key, model registry, or frontend-visible secret",
        "quantPolicy": "sentiment output is read-only evidence for quant review; it must not submit orders, cancel orders, mutate positions, or trigger strategy execution",
        "candidates": GITHUB_ADOPTION_CANDIDATES,
        "doc": "docs/sentiment-center-github-adoption-plan.md",
    }


def _build_page_contract(user_id: int) -> Dict[str, Any]:
    recommendation_map = _build_recommendation_map(user_id)
    market_summaries = [_build_market_summary(market, user_id, recommendation_map) for market in MARKETS]
    leader_symbols = []
    for summary in market_summaries:
        leader_symbols.extend(summary.get("leaders") or [])
    top_items = [
        _build_symbol_sentiment(entry["symbol"], user_id, recommendation_map)
        for entry in sorted(leader_symbols, key=lambda entry: (_safe_float(entry.get("heat")), _safe_float(entry.get("score"))), reverse=True)[:6]
    ]
    return {
        "capabilities": {
            "sentimentMetrics": True,
            "symbolLinkage": True,
            "riskKeywords": True,
            "quantContract": True,
            "aiEvidence": True,
            "orderWriteEnabled": False,
        },
        "marketSummaries": market_summaries,
        "topSymbols": [asdict(item) for item in top_items],
        "riskWordCloud": _build_risk_word_cloud(top_items),
        "aiConfig": _build_ai_config_contract(),
        "githubAdoption": _build_github_adoption_contract(),
        "linkedRoutes": {
            "aiAnalysis": "/ai-analysis",
            "recommendations": "/recommendations",
            "strategy": "/strategy",
            "financeNews": "/finance-news",
        },
        "generatedAt": datetime.now().isoformat(),
    }


@app.get("/health")
async def health():
    deps = {
        "finance-briefings": build_dependency_status("finance-briefings", "ok", detail="复用 analysis read model 资讯聚合"),
        "trend-scans": build_dependency_status("trend-scans", "ok", detail="复用逐股趋势扫描 read model"),
        "recommendations": build_dependency_status("recommendations", "ok", detail="复用推荐结果做舆情联动"),
        "ai-config": build_dependency_status("ai-config", "ok", detail="复用 LONGBRIDGE_AI_* / sub2api 配置"),
    }
    return build_health_payload(
        service="sentiment-service",
        version=app.version,
        port=_service_port(),
        status=summarize_status(deps.values()),
        deps=deps,
        alerts=[
            build_alert("sentiment-readonly", "info", "舆情服务当前只提供只读聚合与结构化 contract，不包含采集写入或交易动作"),
        ],
        capabilities=["sentiment-dashboard", "quant-contract", "ai-config-inheritance"],
        extra={"mode": "read-only-aggregator"},
    )


@app.get("/api/v1/sentiment/config")
async def get_config():
    return {
        "enabled": True,
        "mode": "read-only-aggregator",
        "reservedPort": _service_port(),
        "reservedPrefix": "/api/v1/sentiment",
        "aiConfig": _build_ai_config_contract(),
    }


@app.get("/api/v1/sentiment/bootstrap")
async def bootstrap_sentiment(session: dict = Depends(get_current_session)):
    user_id = _safe_int(session.get("user_id"), 1)
    return {
        "success": True,
        "data": _build_page_contract(user_id),
    }


@app.get("/api/v1/sentiment/overview")
async def get_sentiment_overview(
    market: Optional[str] = Query(default=None),
    session: dict = Depends(get_current_session),
):
    user_id = _safe_int(session.get("user_id"), 1)
    payload = _build_page_contract(user_id)
    selected_market = _normalize_market(market)
    if selected_market:
        payload["marketSummaries"] = [item for item in payload["marketSummaries"] if item.get("market") == selected_market]
        payload["topSymbols"] = [item for item in payload["topSymbols"] if item.get("market") == selected_market]
    return {
        "success": True,
        "data": payload,
        "meta": {
            "market": selected_market or "ALL",
            "snapshotAt": payload.get("generatedAt"),
            "sources": {
                "briefings": "finance_briefings",
                "trendScans": "symbol_ai_trend_scans",
                "recommendations": "recommendation_runs/recommendation_items",
                "aiHistory": "ai_analysis_history",
                "contentCache": "symbol_content_cache",
            },
        },
    }


@app.get("/api/v1/sentiment/symbol/{symbol}")
async def get_symbol_sentiment(
    symbol: str,
    session: dict = Depends(get_current_session),
):
    user_id = _safe_int(session.get("user_id"), 1)
    item = _build_symbol_sentiment(symbol, user_id)
    cache_items = [_score_content_item(entry) for entry in _load_symbol_content(item.symbol)]
    finance_items = [
        _score_content_item(entry)
        for entry in FinanceBriefingService.get_latest(limit=30, market=item.market)
        if str(_payload_of(entry).get("symbol") or "").strip().upper() == item.symbol
    ]
    evidence_items = sorted(
        [*finance_items, *cache_items],
        key=lambda entry: (_safe_float(entry.get("weight")), _format_datetime(_coerce_datetime(entry.get("generatedAt"))) or ""),
        reverse=True,
    )[:10]
    market_snapshot = build_market_snapshot(focus_symbol=item.symbol, user_id=user_id)
    return {
        "success": True,
        "data": {
            **asdict(item),
            "evidence": evidence_items,
            "marketSnapshot": market_snapshot,
            "linkedRoutes": {
                "aiAnalysis": f"/ai-analysis?symbol={item.symbol}&market={item.market}",
                "recommendations": "/recommendations",
                "strategy": "/strategy",
                "financeNews": f"/finance-news?symbol={item.symbol}&market={item.market}",
            },
        },
        "meta": {
            "symbol": item.symbol,
            "market": item.market,
            "snapshotAt": datetime.now().isoformat(),
        },
    }


@app.get("/api/v1/sentiment/universe")
async def get_universe_sentiment(
    market: Optional[str] = Query(default=None),
    limit: int = Query(default=12, ge=1, le=24),
    session: dict = Depends(get_current_session),
):
    user_id = _safe_int(session.get("user_id"), 1)
    selected_market = _normalize_market(market)
    markets = [selected_market] if selected_market else list(MARKETS)
    rows: List[SentimentItem] = []
    recommendation_map = _build_recommendation_map(user_id)
    for market_code in markets:
        rows.extend(_build_symbol_sentiment(symbol, user_id, recommendation_map) for symbol in _market_watchlist(market_code))
    sorted_rows = sorted(rows, key=lambda item: (item.heat, abs(item.score), item.confidence), reverse=True)[:limit]
    return {
        "success": True,
        "data": [asdict(item) for item in sorted_rows],
        "meta": {
            "market": selected_market or "ALL",
            "count": len(sorted_rows),
            "snapshotAt": datetime.now().isoformat(),
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=_service_port(),
        reload=False,
    )
