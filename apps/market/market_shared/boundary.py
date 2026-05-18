from __future__ import annotations

from typing import Any, Dict, List

from .legacy_loader import data_routes


def iter_stock_pool_tables(market: str) -> List[Dict[str, str]]:
    return list(data_routes()._iter_stock_pool_tables(market))  # noqa: SLF001


def build_stock_pool_stats(user_id: int, group_id: str = "") -> Dict[str, Any]:
    return data_routes()._build_stock_pool_stats(user_id=user_id, group_id=group_id)  # noqa: SLF001


def resolve_stock_pool_table(market: str, asset_type: str = "stock") -> Dict[str, str]:
    return data_routes()._resolve_stock_pool_table(market, asset_type)  # noqa: SLF001


def fetch_stock_pool_rows(
    table_config: Dict[str, str],
    user_id: int,
    *,
    search: str = "",
    group_id: str = "",
) -> List[Dict[str, Any]]:
    return data_routes()._fetch_stock_pool_rows(  # noqa: SLF001
        table_config,
        user_id,
        search=search,
        group_id=group_id,
    )


def normalize_market_symbol(symbol: str) -> str:
    return data_routes()._normalize_market_symbol(symbol)  # noqa: SLF001
