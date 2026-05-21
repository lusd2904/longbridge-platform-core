from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class OrderSubmitRequest(BaseModel):
    symbol: str
    action: str
    quantity: int = Field(..., gt=0)
    account_id: int
    price: Optional[float] = Field(default=None, gt=0)
    order_type: str = "LIMIT"
    time_in_force: str = "DAY"
    source: Optional[str] = None
    strategy_context: Dict[str, Any] = Field(default_factory=dict)


class OrderCancelRequest(BaseModel):
    order_id: str
    account_id: int


@dataclass
class AuthUser:
    user_id: int
    username: str
    role: str
