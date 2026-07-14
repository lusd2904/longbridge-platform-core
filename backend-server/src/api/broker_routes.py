"""
券商账户管理API路由
"""

from typing import Any

from flask import Blueprint, jsonify, request

from api.auth_routes import login_required
from apps.market.longbridge_cli_runtime import (
    account_channel as cli_account_channel,
)
from apps.market.longbridge_cli_runtime import (
    account_no as cli_account_no,
)
from apps.market.longbridge_cli_runtime import (
    is_paper_account as cli_is_paper_account,
)
from core.account.RiskManager import RiskLevel, get_risk_manager
from core.broker.BrokerInterface import get_broker_manager
from core.broker.LongbridgeAPI import LongbridgeAPI
from core.broker.TigerBrokerAPI import TigerBrokerAPI
from core.platform.PlatformAuditService import PlatformAuditService
from core.platform.TradeAuditService import TradeAuditService
from utils.crypto import decrypt
from utils.DbUtil import DbUtil
from utils.LoggerUtil import get_logger
from utils.rate_limiter import rate_limit

logger = get_logger(__name__)
broker_bp = Blueprint("broker", __name__, url_prefix="/api/broker")


def _mask_and_enrich_account(account: dict[str, Any]) -> dict[str, Any]:
    """统一补齐账户展示字段。"""
    result = dict(account)
    raw_account_id = result.get("account_id")
    masked_account_id = mask_account_id(str(raw_account_id)) if raw_account_id else ""

    if masked_account_id:
        result["account_id"] = masked_account_id

    broker_name = result.get("broker_name") or result.get("broker_type") or "账户"
    result["name"] = result.get("name") or f"{broker_name} - {masked_account_id or result.get('id')}"
    result["display_name"] = result["name"]
    return result


def _mask_secret(value: str, prefix: int = 3, suffix: int = 2, empty_text: str = "") -> str:
    raw = str(value or "").strip()
    if not raw:
        return empty_text
    if len(raw) <= prefix + suffix:
        return "*" * len(raw)
    return f"{raw[:prefix]}{'*' * (len(raw) - prefix - suffix)}{raw[-suffix:]}"


def _get_user_broker_account(account_id: int, user_id: int, broker_type: str | None = None) -> dict[str, Any] | None:
    sql = """
    SELECT *
    FROM broker_accounts
    WHERE id = %s AND user_id = %s AND is_active = 1
    """
    params = [account_id, user_id]
    if broker_type:
        sql += " AND broker_type = %s"
        params.append(broker_type)
    sql += " LIMIT 1"
    return DbUtil.fetch_one(sql, tuple(params))


def _build_masked_config(row: dict[str, Any], broker_type: str) -> dict[str, Any]:
    if broker_type == "longbridge":
        return {
            "auth_mode": "cli",
            "cli_account_channel": cli_account_channel(),
            "cli_account_no": cli_account_no(),
            "has_cli_auth": cli_is_paper_account(),
        }

    if broker_type == "tiger":
        tiger_id = decrypt(row.get("tiger_id") or "")
        account = decrypt(row.get("tiger_account") or "")
        license_value = decrypt(row.get("tiger_license") or "")
        return {
            "tiger_id_masked": _mask_secret(tiger_id, prefix=3, suffix=2),
            "account_masked": _mask_secret(account, prefix=3, suffix=2),
            "license_masked": _mask_secret(license_value, prefix=2, suffix=2),
            "private_key_pk1_masked": "已加密保存" if row.get("tiger_private_key_pk1") else "",
            "private_key_pk8_masked": "已加密保存" if row.get("tiger_private_key_pk8") else "",
            "env": row.get("tiger_env") or "PROD",
            "has_tiger_id": bool(row.get("tiger_id")),
            "has_account": bool(row.get("tiger_account")),
            "has_license": bool(row.get("tiger_license")),
            "has_private_key_pk1": bool(row.get("tiger_private_key_pk1")),
            "has_private_key_pk8": bool(row.get("tiger_private_key_pk8")),
        }

    return {}


def _ensure_default_selection(account_id: int, user_id: int, is_default: bool) -> None:
    manager = get_broker_manager()
    current_default = DbUtil.fetch_one(
        """
        SELECT id
        FROM broker_accounts
        WHERE user_id = %s AND is_active = 1 AND is_default = 1
        LIMIT 1
        """,
        (user_id,),
    )
    if is_default:
        manager.set_default_account(account_id, user_id)
        return

    if current_default:
        return

    fallback = DbUtil.fetch_one(
        """
        SELECT id
        FROM broker_accounts
        WHERE user_id = %s AND is_active = 1
        ORDER BY created_at ASC, id ASC
        LIMIT 1
        """,
        (user_id,),
    )
    if fallback:
        manager.set_default_account(int(fallback.get("id")), user_id)


def _ensure_broker_connected(broker):
    """确保券商实例已经连接。"""
    connection_state = getattr(broker, "is_connected", False)
    if connection_state() if callable(connection_state) else bool(connection_state):
        return True
    return broker.connect()


def _normalize_action(action: Any) -> str:
    value = str(action or "").strip().upper()
    if value in {"BUY", "B"}:
        return "BUY"
    if value in {"SELL", "S"}:
        return "SELL"
    raise ValueError("action 只支持 BUY 或 SELL")


def _normalize_order_type(order_type: Any) -> str:
    value = str(order_type or "LIMIT").strip().upper()
    if value not in {"LIMIT", "MARKET"}:
        raise ValueError("order_type 只支持 LIMIT 或 MARKET")
    return value


def _get_quote_last_price(quote: Any) -> float | None:
    if isinstance(quote, dict):
        value = quote.get("last_price")
    else:
        value = getattr(quote, "last_price", None)
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _infer_broker_type(broker: Any) -> str:
    config = getattr(broker, "config", None)
    if getattr(config, "account_id", None):
        return "longbridge"
    if getattr(config, "tiger_id", None):
        return "tiger"
    class_name = getattr(getattr(broker, "__class__", None), "__name__", "").lower()
    if "longbridge" in class_name:
        return "longbridge"
    if "tiger" in class_name:
        return "tiger"
    return class_name or "unknown"


def _serialize_quote(symbol: str, quote: Any) -> dict[str, Any]:
    if isinstance(quote, dict):
        last_price = float(quote.get("last_price", 0) or 0)
        prev_close = float(quote.get("prev_close", 0) or 0)
        open_price = float(quote.get("open", 0) or 0)
        high = float(quote.get("high", 0) or 0)
        low = float(quote.get("low", 0) or 0)
        volume = int(quote.get("volume", 0) or 0)
        timestamp = quote.get("timestamp")
    else:
        last_price = float(getattr(quote, "last_price", 0) or 0)
        prev_close = float(getattr(quote, "prev_close", 0) or 0)
        open_price = float(getattr(quote, "open", 0) or 0)
        high = float(getattr(quote, "high", 0) or 0)
        low = float(getattr(quote, "low", 0) or 0)
        volume = int(getattr(quote, "volume", 0) or 0)
        timestamp = getattr(quote, "timestamp", None)

    return {
        "symbol": symbol,
        "last_price": last_price,
        "prev_close": prev_close,
        "open": open_price,
        "high": high,
        "low": low,
        "volume": volume,
        "timestamp": timestamp.isoformat() if hasattr(timestamp, "isoformat") else timestamp,
    }


def _load_reference_price(broker, symbol: str, price: float | None) -> tuple[float | None, dict[str, Any]]:
    if price is not None:
        return float(price), {}

    quotes = broker.get_quote([symbol]) or {}
    quote = quotes.get(symbol)
    last_price = _get_quote_last_price(quote)
    return last_price, _serialize_quote(symbol, quote) if quote else {}


def _run_order_risk_check(
    broker, symbol: str, action: str, quantity: int, reference_price: float
) -> tuple[bool, str, RiskLevel]:
    account_info = broker.get_account_info()
    positions = broker.get_positions()
    account_payload = {"total_equity": float(getattr(account_info, "total_equity", 0) or 0)}
    position_payload = [
        {"symbol": getattr(item, "symbol", ""), "market_value": float(getattr(item, "market_value", 0) or 0)}
        for item in positions
    ]
    return get_risk_manager().check_order_risk(
        symbol=symbol,
        side=action,
        quantity=int(quantity),
        price=float(reference_price or 0),
        account_info=account_payload,
        positions=position_payload,
    )


def _audit_trade_event(
    *,
    account_id: int,
    broker_type: str,
    symbol: str,
    action: str,
    order_type: str,
    quantity: int,
    request_price: float | None,
    reference_price: float | None,
    risk_level: str,
    risk_passed: bool,
    status: str,
    message: str,
    order_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    request_id = getattr(request, "request_id", None)
    TradeAuditService.log(
        user_id=request.user_id,
        username=getattr(request, "username", None),
        account_id=account_id,
        broker_type=broker_type,
        symbol=symbol,
        action=action,
        order_type=order_type,
        quantity=quantity,
        request_price=request_price,
        reference_price=reference_price,
        risk_level=risk_level,
        risk_passed=risk_passed,
        status=status,
        message=message,
        order_id=order_id,
        request_id=request_id,
        client_ip=request.remote_addr,
        extra=extra,
    )
    PlatformAuditService.log(
        user_id=request.user_id,
        username=getattr(request, "username", None),
        module="broker",
        operation=status,
        level="warning" if status in {"risk_rejected", "cancel_failed", "submit_failed"} else "info",
        description=message,
        extra={
            "accountId": account_id,
            "brokerType": broker_type,
            "symbol": symbol,
            "action": action,
            "orderType": order_type,
            "quantity": quantity,
            "orderId": order_id,
        },
    )


# ==================== 账户管理 ====================


@broker_bp.route("/accounts", methods=["GET"])
@login_required
def list_accounts():
    """获取券商账户列表"""
    try:
        manager = get_broker_manager()
        accounts = manager.list_accounts(getattr(request, "user_id", 1))
        accounts = [_mask_and_enrich_account(acc) for acc in accounts]

        return jsonify({"success": True, "data": accounts})
    except Exception as e:
        logger.error(f"获取账户列表失败: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@broker_bp.route("/providers", methods=["GET"])
@login_required
def list_broker_providers():
    """获取券商适配器能力清单。"""
    try:
        manager = get_broker_manager()
        return jsonify({"success": True, "data": manager.list_supported_brokers()})
    except Exception as e:
        logger.error(f"获取券商适配器清单失败: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@broker_bp.route("/accounts/<int:account_id>", methods=["GET"])
@login_required
def get_account(account_id: int):
    """获取单个账户详情"""
    try:
        row = _get_user_broker_account(account_id, request.user_id)

        if not row:
            return jsonify({"success": False, "message": "账户不存在"}), 404

        # 转换为字典
        account = {
            "id": row.get("id"),
            "broker_type": row.get("broker_type"),
            "broker_name": row.get("broker_name"),
            "account_id": row.get("account_id"),
            "is_default": row.get("is_default"),
            "is_active": row.get("is_active"),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }

        # 脱敏
        if account.get("account_id"):
            account["account_id"] = mask_account_id(account["account_id"])

        account["config"] = _build_masked_config(row, account["broker_type"])
        if account["broker_type"] == "longbridge":
            complete = bool(account["config"].get("has_cli_auth"))
        elif account["broker_type"] == "tiger":
            complete = all(
                [
                    account["config"].get("has_tiger_id"),
                    account["config"].get("has_account"),
                    account["config"].get("has_license"),
                    account["config"].get("has_private_key_pk1"),
                ]
            )
        else:
            complete = True
        account["credential_status"] = {"complete": complete, "fields": account["config"]}
        account = _mask_and_enrich_account(account)

        return jsonify({"success": True, "data": account})
    except Exception as e:
        logger.error(f"获取账户详情失败: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return jsonify({"success": False, "message": str(e)}), 500


@broker_bp.route("/accounts/default", methods=["GET"])
@login_required
def get_default_account():
    """获取默认券商账户。"""
    try:
        manager = get_broker_manager()
        accounts = manager.list_accounts(getattr(request, "user_id", 1))
        if not accounts:
            return jsonify({"success": False, "message": "暂无券商账户"}), 404

        default_account = next((acc for acc in accounts if acc.get("is_default")), accounts[0])
        return jsonify({"success": True, "data": _mask_and_enrich_account(default_account)})
    except Exception as e:
        logger.error(f"获取默认账户失败: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@broker_bp.route("/accounts/<int:account_id>/default", methods=["POST", "PUT"])
@login_required
def set_default_account(account_id: int):
    """设置默认账户"""
    try:
        manager = get_broker_manager()
        success = manager.set_default_account(account_id, getattr(request, "user_id", 1))

        if success:
            return jsonify({"success": True, "message": "默认账户设置成功"})
        else:
            return jsonify({"success": False, "message": "设置失败"}), 400
    except Exception as e:
        logger.error(f"设置默认账户失败: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@broker_bp.route("/accounts/<int:account_id>", methods=["DELETE"])
@login_required
def delete_account(account_id: int):
    """删除账户（软删除）"""
    try:
        db = DbUtil()
        row = _get_user_broker_account(account_id, request.user_id)
        if not row:
            return jsonify({"success": False, "message": "账户不存在"}), 404

        sql = "UPDATE broker_accounts SET is_active = 0, is_default = 0 WHERE id = %s AND user_id = %s"
        db.execute(sql, (account_id, request.user_id))

        if row.get("is_default"):
            next_account = DbUtil.fetch_one(
                """
                SELECT id
                FROM broker_accounts
                WHERE user_id = %s AND is_active = 1
                ORDER BY created_at ASC, id ASC
                LIMIT 1
                """,
                (request.user_id,),
            )
            if next_account:
                get_broker_manager().set_default_account(int(next_account.get("id")), request.user_id)

        return jsonify({"success": True, "message": "账户已删除"})
    except Exception as e:
        logger.error(f"删除账户失败: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


# ==================== 长桥证券配置 ====================


@broker_bp.route("/longbridge/config", methods=["POST"])
@login_required
def save_longbridge_config():
    """保存长桥证券配置"""
    try:
        data = request.get_json() or {}
        account_row_id = data.get("account_id")
        existing = None
        if account_row_id:
            try:
                account_row_id = int(account_row_id)
            except (TypeError, ValueError):
                return jsonify({"success": False, "message": "account_id 格式错误"}), 400
            existing = _get_user_broker_account(account_row_id, request.user_id, "longbridge")
            if not existing:
                return jsonify({"success": False, "message": "券商账户不存在"}), 404

        config = {"account": str(data.get("account", "")).strip() or cli_account_no()}

        is_default = bool(data.get("is_default", existing.get("is_default") if existing else False))
        account_id = LongbridgeAPI.save_config(
            config, user_id=request.user_id, is_default=is_default, account_row_id=account_row_id
        )
        _ensure_default_selection(account_id, request.user_id, is_default)

        return jsonify(
            {
                "success": True,
                "message": "长桥 CLI 模拟账户配置保存成功",
                "data": {"account_id": account_id, "updated": bool(existing)},
            }
        )
    except Exception as e:
        logger.error(f"保存长桥证券配置失败: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


# ==================== 老虎证券配置 ====================


@broker_bp.route("/tiger/config", methods=["POST"])
@login_required
def save_tiger_config():
    """保存老虎证券配置"""
    try:
        data = request.get_json() or {}
        account_row_id = data.get("account_id")
        existing = None
        if account_row_id:
            try:
                account_row_id = int(account_row_id)
            except (TypeError, ValueError):
                return jsonify({"success": False, "message": "account_id 格式错误"}), 400
            existing = _get_user_broker_account(account_row_id, request.user_id, "tiger")
            if not existing:
                return jsonify({"success": False, "message": "券商账户不存在"}), 404

        required_fields = ["tiger_id", "account", "license", "private_key_pk1"]
        if not existing:
            for field in required_fields:
                if not str(data.get(field, "")).strip():
                    return jsonify({"success": False, "message": f"缺少必填字段: {field}"}), 400

        config = {
            "tiger_id": str(data.get("tiger_id", "")).strip(),
            "account": str(data.get("account", "")).strip(),
            "license": str(data.get("license", "")).strip(),
            "private_key_pk1": str(data.get("private_key_pk1", "")).strip(),
            "private_key_pk8": str(data.get("private_key_pk8", "")).strip(),
            "env": str(data.get("env", existing.get("tiger_env") if existing else "PROD")).strip().upper(),
        }

        is_default = bool(data.get("is_default", existing.get("is_default") if existing else False))
        account_id = TigerBrokerAPI.save_config(
            config, user_id=request.user_id, is_default=is_default, account_row_id=account_row_id
        )
        _ensure_default_selection(account_id, request.user_id, is_default)

        return jsonify(
            {"success": True, "message": "配置保存成功", "data": {"account_id": account_id, "updated": bool(existing)}}
        )
    except Exception as e:
        logger.error(f"保存老虎证券配置失败: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


# ==================== 连接测试 ====================


@broker_bp.route("/accounts/<int:account_id>/test", methods=["POST"])
@login_required
def test_connection(account_id: int):
    """测试券商连接"""
    try:
        logger.info(f"开始测试连接: account_id={account_id}")

        # 直接从数据库获取账户信息创建新的broker实例（避免缓存问题）
        db = DbUtil()
        sql = "SELECT * FROM broker_accounts WHERE id = %s AND user_id = %s AND is_active = 1"
        record = db.fetch_one(sql, (account_id, request.user_id))

        if not record:
            return jsonify({"success": False, "message": "未找到券商账户"}), 404

        broker_type = record.get("broker_type")
        logger.info(f"券商类型: {broker_type}")

        # 根据类型创建对应的broker实例
        if broker_type == "longbridge":
            from core.broker.LongbridgeAPI import LongbridgeAPI

            broker = LongbridgeAPI(account_id)
        elif broker_type == "tiger":
            from core.broker.TigerBrokerAPI import TigerBrokerAPI

            broker = TigerBrokerAPI(account_id)
        else:
            return jsonify({"success": False, "message": f"不支持的券商类型: {broker_type}"}), 400

        # 检查配置是否加载
        if hasattr(broker, "config"):
            logger.info("broker配置已加载")
        else:
            logger.warning("broker没有config属性")

        # 尝试连接
        connected = broker.connect()
        logger.info(f"连接结果: {connected}")

        if connected:
            # 获取账户信息验证
            try:
                account_info = broker.get_account_info()
                logger.info(f"获取到账户信息: {account_info}")
                broker.disconnect()

                return jsonify(
                    {
                        "success": True,
                        "message": "连接成功",
                        "data": {
                            "account_id": account_info.account_id,
                            "currency": account_info.currency,
                            "cash": account_info.cash,
                            "market_value": account_info.market_value,
                            "total_equity": account_info.total_equity,
                            "buying_power": account_info.buying_power,
                        },
                    }
                )
            except Exception as e:
                broker.disconnect()
                logger.error(f"获取账户信息失败: {e}")
                import traceback

                logger.error(traceback.format_exc())
                return jsonify({"success": False, "message": f"连接成功但获取账户信息失败: {e}"}), 400
        else:
            return jsonify({"success": False, "message": "连接失败"}), 400

    except Exception as e:
        logger.error(f"测试连接失败: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return jsonify({"success": False, "message": str(e)}), 500


# ==================== 交易操作 ====================


@broker_bp.route("/accounts/<int:account_id>/positions", methods=["GET"])
@login_required
def get_positions(account_id: int):
    """获取持仓"""
    try:
        manager = get_broker_manager()
        broker = manager.get_broker(account_id, user_id=request.user_id)

        if not broker:
            return jsonify({"success": False, "message": "未找到券商账户"}), 404

        if not _ensure_broker_connected(broker):
            return jsonify({"success": False, "message": "券商连接失败"}), 502

        positions = broker.get_positions()

        # 转换为字典列表
        positions_data = [
            {
                "symbol": p.symbol,
                "name": p.name or p.symbol,
                "quantity": p.quantity,
                "average_cost": p.average_cost,
                "market_price": p.market_price,
                "market_value": p.market_value,
                "unrealized_pnl": p.unrealized_pnl,
                "realized_pnl": p.realized_pnl,
            }
            for p in positions
        ]

        return jsonify({"success": True, "data": positions_data})
    except Exception as e:
        logger.error(f"获取持仓失败: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@broker_bp.route("/accounts/<int:account_id>/account", methods=["GET"])
@login_required
def get_account_info(account_id: int):
    """获取账户信息"""
    try:
        manager = get_broker_manager()
        broker = manager.get_broker(account_id, user_id=request.user_id)

        if not broker:
            return jsonify({"success": False, "message": "未找到券商账户"}), 404

        if not _ensure_broker_connected(broker):
            return jsonify({"success": False, "message": "券商连接失败"}), 502

        account_info = broker.get_account_info()

        return jsonify(
            {
                "success": True,
                "data": {
                    "account_id": account_info.account_id,
                    "currency": account_info.currency,
                    "cash": account_info.cash,
                    "market_value": account_info.market_value,
                    "total_equity": account_info.total_equity,
                    "buying_power": account_info.buying_power,
                    "maintenance_margin": account_info.maintenance_margin,
                },
            }
        )
    except Exception as e:
        logger.error(f"获取账户信息失败: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@broker_bp.route("/accounts/<int:account_id>/orders", methods=["GET"])
@login_required
def get_orders(account_id: int):
    """获取订单列表"""
    try:
        status = request.args.get("status")

        manager = get_broker_manager()
        broker = manager.get_broker(account_id, user_id=request.user_id)

        if not broker:
            return jsonify({"success": False, "message": "未找到券商账户"}), 404

        if not _ensure_broker_connected(broker):
            return jsonify({"success": False, "message": "券商连接失败"}), 502

        orders = broker.get_orders(status)

        # 转换为字典列表
        orders_data = [
            {
                "order_id": o.order_id,
                "symbol": o.symbol,
                "action": o.action,
                "order_type": o.order_type,
                "quantity": o.quantity,
                "filled_quantity": o.filled_quantity,
                "price": o.price,
                "status": o.status,
                "create_time": o.create_time.isoformat() if o.create_time else None,
            }
            for o in orders
        ]

        return jsonify({"success": True, "data": orders_data})
    except Exception as e:
        logger.error(f"获取订单列表失败: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@broker_bp.route("/accounts/<int:account_id>/orders", methods=["POST"])
@login_required
@rate_limit(
    key_func=lambda: f"trade-submit:{getattr(request, 'user_id', 'anonymous')}:{request.view_args.get('account_id', 'default')}",
    limit=10,
    window=60,
)
def place_order(account_id: int):
    """下单"""
    try:
        data = request.get_json(silent=True) or {}

        # 验证必填字段
        required_fields = ["symbol", "action", "quantity"]
        for field in required_fields:
            if field not in data:
                return jsonify({"success": False, "message": f"缺少必填字段: {field}"}), 400

        manager = get_broker_manager()
        broker = manager.get_broker(account_id, user_id=request.user_id)

        if not broker:
            return jsonify({"success": False, "message": "未找到券商账户"}), 404

        if not _ensure_broker_connected(broker):
            return jsonify({"success": False, "message": "券商连接失败"}), 502

        symbol = str(data.get("symbol", "")).strip().upper()
        action = _normalize_action(data.get("action"))
        order_type = _normalize_order_type(data.get("order_type", "LIMIT"))
        quantity = int(float(data.get("quantity") or 0))
        request_price = float(data.get("price")) if data.get("price") not in (None, "") else None
        time_in_force = str(data.get("time_in_force", "DAY") or "DAY").strip().upper()

        if not symbol:
            return jsonify({"success": False, "message": "symbol 不能为空"}), 400
        if quantity <= 0:
            return jsonify({"success": False, "message": "quantity 必须大于 0"}), 400
        if order_type == "LIMIT" and request_price is None:
            return jsonify({"success": False, "message": "限价单必须提供 price"}), 400

        reference_price, quote_snapshot = _load_reference_price(broker, symbol, request_price)
        if reference_price is None or reference_price <= 0:
            return jsonify({"success": False, "message": "无法获取有效参考价格，请稍后再试"}), 502

        risk_allowed, risk_message, risk_level = _run_order_risk_check(
            broker, symbol=symbol, action=action, quantity=quantity, reference_price=reference_price
        )

        broker_type = _infer_broker_type(broker)
        if not risk_allowed:
            _audit_trade_event(
                account_id=account_id,
                broker_type=broker_type,
                symbol=symbol,
                action=action,
                order_type=order_type,
                quantity=quantity,
                request_price=request_price,
                reference_price=reference_price,
                risk_level=risk_level.value,
                risk_passed=False,
                status="risk_rejected",
                message=f"交易风控拒绝: {risk_message}",
                extra={"quote": quote_snapshot},
            )
            return jsonify({"success": False, "message": risk_message, "risk_level": risk_level.value}), 422

        result = broker.place_order(
            symbol=symbol,
            action=action,
            quantity=quantity,
            order_type=order_type,
            price=request_price,
            time_in_force=time_in_force,
        )
        _audit_trade_event(
            account_id=account_id,
            broker_type=broker_type,
            symbol=symbol,
            action=action,
            order_type=order_type,
            quantity=quantity,
            request_price=request_price,
            reference_price=reference_price,
            risk_level=risk_level.value,
            risk_passed=True,
            status="submitted",
            message="人工交易订单已提交",
            order_id=result.get("order_id"),
            extra={"quote": quote_snapshot, "response": result},
        )

        return jsonify({"success": True, "message": "下单成功", "data": result})
    except ValueError as e:
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception as e:
        logger.error(f"下单失败: {e}")
        try:
            _audit_trade_event(
                account_id=account_id,
                broker_type="unknown",
                symbol=str((request.get_json(silent=True) or {}).get("symbol", "")).strip().upper(),
                action=str((request.get_json(silent=True) or {}).get("action", "")).strip().upper(),
                order_type=str((request.get_json(silent=True) or {}).get("order_type", "LIMIT")).strip().upper(),
                quantity=int(float((request.get_json(silent=True) or {}).get("quantity") or 0)),
                request_price=float((request.get_json(silent=True) or {}).get("price"))
                if (request.get_json(silent=True) or {}).get("price") not in (None, "")
                else None,
                reference_price=None,
                risk_level="unknown",
                risk_passed=False,
                status="submit_failed",
                message=f"人工交易提交失败: {e}",
            )
        except Exception:
            pass
        return jsonify({"success": False, "message": str(e)}), 500


@broker_bp.route("/accounts/<int:account_id>/orders/<order_id>", methods=["DELETE"])
@login_required
@rate_limit(
    key_func=lambda: f"trade-cancel:{getattr(request, 'user_id', 'anonymous')}:{request.view_args.get('account_id', 'default')}",
    limit=10,
    window=60,
)
def cancel_order(account_id: int, order_id: str):
    """撤单"""
    try:
        manager = get_broker_manager()
        broker = manager.get_broker(account_id, user_id=request.user_id)

        if not broker:
            return jsonify({"success": False, "message": "未找到券商账户"}), 404

        if not _ensure_broker_connected(broker):
            return jsonify({"success": False, "message": "券商连接失败"}), 502

        success = broker.cancel_order(order_id)
        broker_type = _infer_broker_type(broker)

        if success:
            _audit_trade_event(
                account_id=account_id,
                broker_type=broker_type,
                symbol="",
                action="CANCEL",
                order_type="CANCEL",
                quantity=0,
                request_price=None,
                reference_price=None,
                risk_level="low",
                risk_passed=True,
                status="cancelled",
                message=f"人工撤单成功: {order_id}",
                order_id=order_id,
            )
            return jsonify({"success": True, "message": "撤单成功"})
        else:
            _audit_trade_event(
                account_id=account_id,
                broker_type=broker_type,
                symbol="",
                action="CANCEL",
                order_type="CANCEL",
                quantity=0,
                request_price=None,
                reference_price=None,
                risk_level="medium",
                risk_passed=False,
                status="cancel_failed",
                message=f"人工撤单失败: {order_id}",
                order_id=order_id,
            )
            return jsonify({"success": False, "message": "撤单失败"}), 400
    except Exception as e:
        logger.error(f"撤单失败: {e}")
        try:
            _audit_trade_event(
                account_id=account_id,
                broker_type="unknown",
                symbol="",
                action="CANCEL",
                order_type="CANCEL",
                quantity=0,
                request_price=None,
                reference_price=None,
                risk_level="unknown",
                risk_passed=False,
                status="cancel_failed",
                message=f"人工撤单异常: {e}",
                order_id=order_id,
            )
        except Exception:
            pass
        return jsonify({"success": False, "message": str(e)}), 500


# ==================== 行情接口 ====================


@broker_bp.route("/quotes", methods=["POST"])
@login_required
@rate_limit(key_func=lambda: f"broker-quotes:{getattr(request, 'user_id', 'anonymous')}", limit=30, window=60)
def get_quotes():
    """获取行情"""
    try:
        data = request.get_json(silent=True) or {}
        symbols = data.get("symbols", [])
        account_id = data.get("account_id")

        if not symbols:
            return jsonify({"success": False, "message": "股票代码列表不能为空"}), 400

        manager = get_broker_manager()
        broker = manager.get_broker(account_id, user_id=request.user_id)

        if not broker:
            return jsonify({"success": False, "message": "未找到券商账户"}), 404

        if not _ensure_broker_connected(broker):
            return jsonify({"success": False, "message": "券商连接失败"}), 502

        quotes = broker.get_quote(symbols)

        # 转换为字典
        quotes_data = {symbol: _serialize_quote(symbol, q) for symbol, q in quotes.items()}

        return jsonify({"success": True, "data": quotes_data})
    except Exception as e:
        logger.error(f"获取行情失败: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


# ==================== 工具函数 ====================


def mask_account_id(account_id: str) -> str:
    """脱敏处理账户ID"""
    account_id = str(account_id or "")
    if len(account_id) <= 4:
        return "*" * len(account_id)
    return account_id[:2] + "*" * (len(account_id) - 4) + account_id[-2:]
