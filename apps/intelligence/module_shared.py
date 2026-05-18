from __future__ import annotations

from apps.intelligence.intelligence_shared import (
    build_market_snapshot,
    build_real_indicator_context,
    detect_market,
    extract_position_quote_fallback,
    get_quote_from_broker,
    get_quotes_from_broker,
)
from core.account.DataPersistence import AIAnalysisHistory, get_persistence_manager
from core.analysis.AiConsultant import AiConsultant
from core.analysis.DailySymbolTrendScanService import DailySymbolTrendScanService
from core.analysis.FinanceBriefingService import FinanceBriefingService
from core.analysis.HistoricalMarketDataService import HistoricalMarketDataService
from core.analysis.QuantTradingService import QuantTradingService
from core.analysis.RecommendationService import RecommendationService
from core.analysis.StrategyMonitorService import StrategyMonitorService
from core.analysis.ai_analyst import AIAnalyst
from apps.runtime_shared.legacy_runtime import legacy_boundary_status
from apps.runtime_shared.app import create_service_app
from apps.runtime_shared.auth import get_current_session
from apps.runtime_shared.bootstrap import bootstrap_runtime, service_port
from apps.runtime_shared.health import build_dependency_status, build_health_payload, summarize_status
from utils.DbUtil import DbUtil
from utils.cache import AICache
from utils.redis_client import redis_client

__all__ = [
    "AIAnalysisHistory",
    "AICache",
    "AIAnalyst",
    "AiConsultant",
    "DailySymbolTrendScanService",
    "DbUtil",
    "FinanceBriefingService",
    "HistoricalMarketDataService",
    "QuantTradingService",
    "RecommendationService",
    "StrategyMonitorService",
    "bootstrap_runtime",
    "build_dependency_status",
    "build_health_payload",
    "build_market_snapshot",
    "build_real_indicator_context",
    "create_service_app",
    "detect_market",
    "extract_position_quote_fallback",
    "get_current_session",
    "get_persistence_manager",
    "get_quote_from_broker",
    "get_quotes_from_broker",
    "legacy_boundary_status",
    "redis_client",
    "service_port",
    "summarize_status",
]
