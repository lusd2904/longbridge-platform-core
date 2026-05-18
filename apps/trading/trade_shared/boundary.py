from __future__ import annotations

from typing import Any, Dict, Optional

from .legacy_loader import broker_routes


def get_user_broker_account(account_id: int, user_id: int, broker_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
    return broker_routes()._get_user_broker_account(account_id, user_id, broker_type)  # noqa: SLF001


def build_masked_broker_config(row: Dict[str, Any], broker_type: str) -> Dict[str, Any]:
    return broker_routes()._build_masked_config(row, broker_type)  # noqa: SLF001


def ensure_default_selection(account_id: int, user_id: int, is_default: bool) -> None:
    broker_routes()._ensure_default_selection(account_id, user_id, is_default)  # noqa: SLF001


def enrich_broker_account(account: Dict[str, Any]) -> Dict[str, Any]:
    return broker_routes()._mask_and_enrich_account(account)  # noqa: SLF001


def mask_account_id(account_id: str) -> str:
    return broker_routes().mask_account_id(account_id)
