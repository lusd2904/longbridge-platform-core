"""
交易相关API路由
提供买入、卖出、获取真实持仓和订单等功能
支持多账户
"""
from flask import Blueprint, request, jsonify
import requests
from config.settings import settings
from shared.longbridge import (
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForceType,
    build_quote_context,
    build_trade_context,
)
from utils.DbUtil import DbUtil
from utils.crypto import decrypt
from datetime import datetime
import os
from api.auth_routes import login_required

# 屏蔽代理干扰
os.environ['http_proxy'] = ''
os.environ['https_proxy'] = ''

trade_bp = Blueprint('trade', __name__)


def _proxy_trade_service(path, method='GET', payload=None, params=None):
    """将交易请求转发到 FastAPI trade-service。"""
    base_url = str(settings.TRADE_SERVICE_URL or '').rstrip('/')
    if not settings.TRADE_SERVICE_ENABLED or not base_url:
        return None

    headers = {}
    authorization = request.headers.get('Authorization')
    if authorization:
        headers['Authorization'] = authorization
    request_id = request.headers.get('X-Request-ID')
    if request_id:
        headers['X-Request-ID'] = request_id

    try:
        session = requests.Session()
        session.trust_env = False
        response = session.request(
            method=method.upper(),
            url=f"{base_url}{path}",
            headers=headers,
            json=payload,
            params=params,
            timeout=max(3, int(settings.TRADE_SERVICE_TIMEOUT or 30))
        )
    except requests.RequestException as exc:
        return jsonify({
            "success": False,
            "error": f"trade-service 不可用: {exc}"
        }), 502

    try:
        body = response.json()
    except ValueError:
        body = {
            "success": response.ok,
            "error": response.text or "trade-service 返回了非 JSON 响应"
        }

    return jsonify(body), response.status_code


def _resolve_default_account_id(user_id):
    """获取当前用户默认账户ID。"""
    db = DbUtil()
    row = db.fetch_one(
        """
        SELECT id
        FROM broker_accounts
        WHERE user_id = %s AND is_active = 1 AND is_default = 1
        ORDER BY id ASC
        LIMIT 1
        """,
        (user_id,)
    )
    if row:
        return row.get('id')

    row = db.fetch_one(
        """
        SELECT id
        FROM broker_accounts
        WHERE user_id = %s AND is_active = 1
        ORDER BY id ASC
        LIMIT 1
        """,
        (user_id,)
    )
    return row.get('id') if row else None


def get_account_config(account_id, user_id=None):
    """从数据库获取账户配置"""
    try:
        db = DbUtil()
        if user_id is not None:
            sql = """
                SELECT id, broker_type, account_id,
                       tiger_id, tiger_account, tiger_license, tiger_private_key_pk1, tiger_private_key_pk8
                FROM broker_accounts
                WHERE id = %s AND user_id = %s AND is_active = 1
            """
            row = db.fetch_one(sql, (account_id, user_id))
        else:
            sql = """
                SELECT id, broker_type, account_id,
                       tiger_id, tiger_account, tiger_license, tiger_private_key_pk1, tiger_private_key_pk8
                FROM broker_accounts
                WHERE id = %s AND is_active = 1
            """
            row = db.fetch_one(sql, (account_id,))

        if not row:
            return None

        broker_type = row.get('broker_type')
        account_id_val = row.get('account_id', '')
        broker_name = {'longbridge': '长桥', 'tiger': '老虎', 'interactive_brokers': '盈透'}.get(broker_type, broker_type)

        config = {
            'id': row.get('id'),
            'broker_type': broker_type,
            'account_id': account_id_val,
            'account_name': f"{broker_name} - {account_id_val}"
        }

        if broker_type == 'tiger':
            config['tiger_id'] = decrypt(row.get('tiger_id', ''))
            config['tiger_account'] = decrypt(row.get('tiger_account', ''))
            config['tiger_license'] = decrypt(row.get('tiger_license', ''))
            config['tiger_private_key_pk1'] = decrypt(row.get('tiger_private_key_pk1', ''))
            config['tiger_private_key_pk8'] = decrypt(row.get('tiger_private_key_pk8', ''))

        return config
    except Exception as e:
        print(f"❌ [TradeAPI] 获取账户配置失败: {e}")
        import traceback
        print(traceback.format_exc())
        return None


def get_trade_context_for_account(account_id, user_id=None):
    """获取指定账户的交易上下文"""
    try:
        config = get_account_config(account_id, user_id=user_id)
        if not config:
            print(f"❌ [TradeAPI] 未找到账户配置: {account_id}")
            return None, None, None
        
        broker_type = config.get('broker_type')
        
        if broker_type == 'longbridge':
            return build_trade_context(user_id=user_id or 1), build_quote_context(user_id=user_id or 1), config
        elif broker_type == 'tiger':
            # 老虎证券使用TigerBrokerAPI
            from core.broker.TigerBrokerAPI import TigerBrokerAPI
            api = TigerBrokerAPI(account_id)
            if api.connect():
                return api, None, config
            return None, None, None
        else:
            print(f"❌ [TradeAPI] 不支持的券商类型: {broker_type}")
            return None, None, None
            
    except Exception as e:
        print(f"❌ [TradeAPI] 初始化交易上下文失败: {e}")
        import traceback
        print(traceback.format_exc())
        return None, None, None


def _unpack(obj):
    """安全转换 SDK 包装对象"""
    if obj is None:
        return 0.0
    val = getattr(obj, 'value', obj)
    try:
        return float(val)
    except:
        return 0.0


def _get_order_status(status):
    """转换订单状态为中文"""
    if status is None:
        return "未知"

    # 将枚举转换为字符串并提取名称
    status_str = str(status)
    # 处理 "OrderStatus.Canceled" -> "Canceled"
    if '.' in status_str:
        status_name = status_str.split('.')[-1]
    else:
        status_name = status_str

    status_map = {
        'Unknown': "未知",
        'NotReported': "未报",
        'ReplacedNotReported': "换单未报",
        'ProtectedNotReported': "保价未报",
        'VarietiesNotReported': "竞价未报",
        'Filled': "已成交",
        'WaitToNew': "待提交",
        'New': "已提交待报",
        'WaitToReplace': "待修改",
        'PendingReplace': "修改中",
        'Replaced': "已修改",
        'PartialFilled': "部分成交",
        'WaitToCancel': "待撤单",
        'PendingCancel': "撤单中",
        'Canceled': "已撤单",
        'Rejected': "已拒绝",
        'Removed': "已移除",
        'Expired': "已过期",
        'PartialWithdrawal': "部分撤销"
    }

    return status_map.get(status_name, status_name)


# ========== 账户列表接口 ==========

@trade_bp.route('/api/trade/accounts', methods=['GET'])
@login_required
def get_trade_accounts():
    """获取可用于交易的账户列表"""
    try:
        db = DbUtil()
        sql = """
            SELECT id, broker_type, account_id, is_default
            FROM broker_accounts
            WHERE user_id = %s AND is_active = 1
            ORDER BY is_default DESC, id ASC
        """
        rows = db.fetch_all(sql, (request.user_id,))

        accounts = []
        for row in rows:
            broker_type = row.get('broker_type', '')
            account_id = row.get('account_id', '')
            broker_name = {'longbridge': '长桥', 'tiger': '老虎', 'interactive_brokers': '盈透'}.get(broker_type, broker_type)
            accounts.append({
                'id': row.get('id'),
                'broker_type': broker_type,
                'account_id': account_id,
                'name': f"{broker_name} - {account_id}",
                'is_default': bool(row.get('is_default', 0))
            })

        return jsonify({
            "success": True,
            "accounts": accounts
        })

    except Exception as e:
        print(f"❌ [TradeAPI] 获取账户列表失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ========== 持仓接口 ==========

@trade_bp.route('/api/real_positions', methods=['GET'])
@login_required
def get_real_positions():
    """获取真实持仓数据 - 支持多账户"""
    try:
        account_id = request.args.get('account_id')
        
        if not account_id:
            # 如果没有指定账户，返回所有账户的持仓
            return get_all_positions(request.user_id)
        
        tc, qc, config = get_trade_context_for_account(int(account_id), user_id=request.user_id)
        if not tc:
            return jsonify({"success": False, "error": "交易服务初始化失败"}), 500
        
        broker_type = config.get('broker_type')
        positions = []
        
        if broker_type == 'longbridge':
            # 获取持仓信息
            pos_resp = tc.stock_positions()
            
            # 解析持仓数据
            if pos_resp and hasattr(pos_resp, 'channels'):
                for channel in pos_resp.channels:
                    if hasattr(channel, 'positions'):
                        for p in channel.positions:
                            symbol = p.symbol
                            qty = _unpack(p.quantity)
                            cost_price = _unpack(p.cost_price)
                            
                            # 获取实时价格
                            current_price = 0.0
                            try:
                                quotes = qc.quote([symbol])
                                if quotes and len(quotes) > 0:
                                    q = quotes[0]
                                    current_price = _unpack(q.last_done)
                                    if current_price == 0:
                                        current_price = _unpack(getattr(q, 'prev_close', 0))
                            except Exception as e:
                                print(f"⚠️ [TradeAPI] 获取{symbol}行情失败: {e}")
                            
                            # 计算盈亏
                            market_value = current_price * qty if current_price > 0 else 0
                            pnl = (current_price - cost_price) * qty if current_price > 0 else 0
                            pnl_ratio = ((current_price - cost_price) / cost_price * 100) if cost_price > 0 else 0
                            
                            positions.append({
                                "symbol": symbol,
                                "name": getattr(p, 'symbol_name', symbol),
                                "quantity": qty,
                                "cost_price": cost_price,
                                "current_price": current_price,
                                "market_value": market_value,
                                "pnl": pnl,
                                "pnl_ratio": pnl_ratio,
                                "currency": getattr(p, 'currency', 'USD'),
                                "account_id": account_id,
                                "account_name": config.get('account_name', '')
                            })
        elif broker_type == 'tiger':
            # 老虎证券
            tiger_positions = tc.get_positions()
            for p in tiger_positions:
                positions.append({
                    "symbol": p.symbol,
                    "name": p.symbol,
                    "quantity": p.quantity,
                    "cost_price": p.average_cost,
                    "current_price": p.market_price,
                    "market_value": p.market_value,
                    "pnl": p.unrealized_pnl,
                    "pnl_ratio": (p.unrealized_pnl / (p.average_cost * p.quantity) * 100) if p.average_cost > 0 and p.quantity > 0 else 0,
                    "currency": 'USD',
                    "account_id": account_id,
                    "account_name": config.get('account_name', '')
                })
        
        print(f"✅ [TradeAPI] 获取持仓成功: 账户{account_id}, {len(positions)} 只股票")
        
        return jsonify({
            "success": True,
            "positions": positions,
            "count": len(positions),
            "account_id": account_id
        })
        
    except Exception as e:
        print(f"❌ [TradeAPI] 获取持仓失败: {e}")
        import traceback
        print(traceback.format_exc())
        return jsonify({"success": False, "error": str(e)}), 500


def get_all_positions(user_id):
    """获取所有账户的持仓"""
    try:
        db = DbUtil()
        sql = """
            SELECT id, broker_type, account_id
            FROM broker_accounts
            WHERE user_id = %s AND is_active = 1
        """
        rows = db.fetch_all(sql, (user_id,))
        
        all_positions = []
        for row in rows:
            account_id = row.get('id')
            try:
                tc, qc, config = get_trade_context_for_account(account_id, user_id=user_id)
                if not tc:
                    continue
                
                broker_type = config.get('broker_type')
                
                if broker_type == 'longbridge':
                    pos_resp = tc.stock_positions()
                    if pos_resp and hasattr(pos_resp, 'channels'):
                        for channel in pos_resp.channels:
                            if hasattr(channel, 'positions'):
                                for p in channel.positions:
                                    symbol = p.symbol
                                    qty = _unpack(p.quantity)
                                    cost_price = _unpack(p.cost_price)
                                    
                                    current_price = 0.0
                                    try:
                                        quotes = qc.quote([symbol])
                                        if quotes and len(quotes) > 0:
                                            q = quotes[0]
                                            current_price = _unpack(q.last_done)
                                            if current_price == 0:
                                                current_price = _unpack(getattr(q, 'prev_close', 0))
                                    except:
                                        pass
                                    
                                    market_value = current_price * qty if current_price > 0 else 0
                                    pnl = (current_price - cost_price) * qty if current_price > 0 else 0
                                    pnl_ratio = ((current_price - cost_price) / cost_price * 100) if cost_price > 0 else 0
                                    
                                    all_positions.append({
                                        "symbol": symbol,
                                        "name": getattr(p, 'symbol_name', symbol),
                                        "quantity": qty,
                                        "cost_price": cost_price,
                                        "current_price": current_price,
                                        "market_value": market_value,
                                        "pnl": pnl,
                                        "pnl_ratio": pnl_ratio,
                                        "currency": getattr(p, 'currency', 'USD'),
                                        "account_id": account_id,
                                        "account_name": config.get('account_name', '')
                                    })
                elif broker_type == 'tiger':
                    tiger_positions = tc.get_positions()
                    for p in tiger_positions:
                        all_positions.append({
                            "symbol": p.symbol,
                            "name": p.symbol,
                            "quantity": p.quantity,
                            "cost_price": p.average_cost,
                            "current_price": p.market_price,
                            "market_value": p.market_value,
                            "pnl": p.unrealized_pnl,
                            "pnl_ratio": (p.unrealized_pnl / (p.average_cost * p.quantity) * 100) if p.average_cost > 0 and p.quantity > 0 else 0,
                            "currency": 'USD',
                            "account_id": account_id,
                            "account_name": config.get('account_name', '')
                        })
            except Exception as e:
                print(f"⚠️ [TradeAPI] 获取账户{account_id}持仓失败: {e}")
                continue
        
        return jsonify({
            "success": True,
            "positions": all_positions,
            "count": len(all_positions)
        })
        
    except Exception as e:
        print(f"❌ [TradeAPI] 获取所有持仓失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ========== 订单接口 ==========

@trade_bp.route('/api/real_orders', methods=['GET'])
@login_required
def get_real_orders():
    """获取真实订单数据 - 支持多账户"""
    proxied = _proxy_trade_service(
        '/orders',
        method='GET',
        params={
            'account_id': request.args.get('account_id'),
            'status': request.args.get('status'),
            'limit': request.args.get('limit', 200)
        }
    )
    if proxied is not None:
        return proxied

    try:
        account_id = request.args.get('account_id')
        
        if not account_id:
            # 如果没有指定账户，返回所有账户的订单
            return get_all_orders(request.user_id)
        
        tc, qc, config = get_trade_context_for_account(int(account_id), user_id=request.user_id)
        if not tc:
            return jsonify({"success": False, "error": "交易服务初始化失败"}), 500
        
        broker_type = config.get('broker_type')
        orders = []
        
        if broker_type == 'longbridge':
            # 获取当日订单
            orders_resp = tc.today_orders()

            # 解析订单数据
            if orders_resp:
                for o in orders_resp:
                    orders.append({
                        "order_id": getattr(o, 'order_id', ''),
                        "symbol": getattr(o, 'symbol', ''),
                        "side": "买入" if str(getattr(o, 'side', '')).lower() == 'buy' else "卖出",
                        "quantity": _unpack(getattr(o, 'quantity', 0)),
                        "price": _unpack(getattr(o, 'price', 0)),
                        "status": _get_order_status(getattr(o, 'status', None)),
                        "create_time": str(getattr(o, 'submitted_at', '')),
                        "account_id": account_id,
                        "account_name": config.get('account_name', '')
                    })
        elif broker_type == 'tiger':
            # 老虎证券订单查询
            tiger_orders = tc.get_orders()
            for o in tiger_orders:
                orders.append({
                    "order_id": o.order_id,
                    "symbol": o.symbol,
                    "side": "买入" if o.action == 'BUY' else "卖出",
                    "quantity": o.quantity,
                    "price": o.price,
                    "status": _get_order_status(o.status),
                    "create_time": str(o.create_time),
                    "account_id": account_id,
                    "account_name": config.get('account_name', '')
                })

        print(f"✅ [TradeAPI] 获取订单成功: 账户{account_id}, {len(orders)} 笔订单")
        
        return jsonify({
            "success": True,
            "orders": orders,
            "count": len(orders),
            "account_id": account_id
        })
        
    except Exception as e:
        print(f"❌ [TradeAPI] 获取订单失败: {e}")
        import traceback
        print(traceback.format_exc())
        return jsonify({"success": False, "error": str(e)}), 500


def get_all_orders(user_id):
    """获取所有账户的订单"""
    try:
        db = DbUtil()
        sql = """
            SELECT id, broker_type, account_id
            FROM broker_accounts
            WHERE user_id = %s AND is_active = 1
        """
        rows = db.fetch_all(sql, (user_id,))
        
        all_orders = []
        for row in rows:
            account_id = row.get('id')
            try:
                tc, qc, config = get_trade_context_for_account(account_id, user_id=user_id)
                if not tc:
                    continue
                
                broker_type = config.get('broker_type')
                
                if broker_type == 'longbridge':
                    orders_resp = tc.today_orders()
                    if orders_resp:
                        for o in orders_resp:
                            all_orders.append({
                                "order_id": getattr(o, 'order_id', ''),
                                "symbol": getattr(o, 'symbol', ''),
                                "side": "买入" if str(getattr(o, 'side', '')).lower() == 'buy' else "卖出",
                                "quantity": _unpack(getattr(o, 'quantity', 0)),
                                "price": _unpack(getattr(o, 'price', 0)),
                                "status": _get_order_status(getattr(o, 'status', None)),
                                "create_time": str(getattr(o, 'submitted_at', '')),
                                "account_id": account_id,
                                "account_name": config.get('account_name', '')
                            })
                elif broker_type == 'tiger':
                    # 老虎证券订单查询
                    tiger_orders = tc.get_orders()
                    for o in tiger_orders:
                        all_orders.append({
                            "order_id": o.order_id,
                            "symbol": o.symbol,
                            "side": "买入" if o.action == 'BUY' else "卖出",
                            "quantity": o.quantity,
                            "price": o.price,
                            "status": _get_order_status(o.status),
                            "create_time": str(o.create_time),
                            "account_id": account_id,
                            "account_name": config.get('account_name', '')
                        })
            except Exception as e:
                print(f"⚠️ [TradeAPI] 获取账户{account_id}订单失败: {e}")
                import traceback
                print(traceback.format_exc())
                continue
        
        return jsonify({
            "success": True,
            "orders": all_orders,
            "count": len(all_orders)
        })
        
    except Exception as e:
        print(f"❌ [TradeAPI] 获取所有订单失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ========== 交易接口 ==========

@trade_bp.route('/api/trade/buy', methods=['POST'])
@login_required
def buy_stock():
    """买入股票 - 支持指定账户"""
    if settings.TRADE_SERVICE_ENABLED:
        data = request.json or {}
        return _proxy_trade_service(
            '/orders/submit',
            method='POST',
            payload={
                'symbol': data.get('symbol'),
                'action': 'BUY',
                'quantity': data.get('quantity'),
                'price': data.get('price'),
                'account_id': data.get('account_id'),
                'order_type': data.get('order_type', 'LIMIT'),
                'time_in_force': data.get('time_in_force', 'DAY')
            }
        )

    try:
        data = request.json
        symbol = data.get('symbol')
        quantity = int(data.get('quantity', 0))
        price = float(data.get('price', 0))
        account_id = data.get('account_id')
        
        if not symbol or quantity <= 0 or price <= 0:
            return jsonify({"success": False, "error": "参数错误：股票代码、数量和价格必须大于0"}), 400
        
        if not account_id:
            return jsonify({"success": False, "error": "请选择交易账户"}), 400
        
        tc, qc, config = get_trade_context_for_account(int(account_id), user_id=request.user_id)
        if not tc:
            return jsonify({"success": False, "error": "交易服务初始化失败或账户不属于当前用户"}), 500
        
        broker_type = config.get('broker_type')
        
        if broker_type == 'longbridge':
            # 提交买入订单
            resp = tc.submit_order(
                symbol=symbol,
                order_type=OrderType.LO,
                side=OrderSide.Buy,
                submitted_quantity=quantity,
                submitted_price=price,
                time_in_force=TimeInForceType.Day
            )
            
            print(f"✅ [TradeAPI] 买入订单提交成功: {symbol} | 数量:{quantity} | 价格:{price}")
            
            return jsonify({
                "success": True,
                "message": f"买入订单提交成功: {symbol}",
                "order_id": getattr(resp, 'order_id', None),
                "symbol": symbol,
                "side": "BUY",
                "quantity": quantity,
                "price": price,
                "account_id": account_id
            })
        elif broker_type == 'tiger':
            # 老虎证券交易
            resp = tc.place_order(
                symbol=symbol,
                action='BUY',
                quantity=quantity,
                order_type='LIMIT',
                price=price,
                time_in_force='DAY'
            )
            
            print(f"✅ [TradeAPI] 老虎证券买入订单提交成功: {symbol} | 数量:{quantity} | 价格:{price}")
            
            return jsonify({
                "success": True,
                "message": f"买入订单提交成功: {symbol}",
                "order_id": resp.get('order_id', ''),
                "symbol": symbol,
                "side": "BUY",
                "quantity": quantity,
                "price": price,
                "account_id": account_id
            })
        else:
            return jsonify({"success": False, "error": "不支持的券商类型"}), 400
        
    except Exception as e:
        print(f"❌ [TradeAPI] 买入失败: {e}")
        import traceback
        print(traceback.format_exc())
        return jsonify({"success": False, "error": str(e)}), 500


@trade_bp.route('/api/trade/sell', methods=['POST'])
@login_required
def sell_stock():
    """卖出股票 - 支持指定账户"""
    if settings.TRADE_SERVICE_ENABLED:
        data = request.json or {}
        return _proxy_trade_service(
            '/orders/submit',
            method='POST',
            payload={
                'symbol': data.get('symbol'),
                'action': 'SELL',
                'quantity': data.get('quantity'),
                'price': data.get('price'),
                'account_id': data.get('account_id'),
                'order_type': data.get('order_type', 'LIMIT'),
                'time_in_force': data.get('time_in_force', 'DAY')
            }
        )

    try:
        data = request.json
        symbol = data.get('symbol')
        quantity = int(data.get('quantity', 0))
        price = float(data.get('price', 0))
        account_id = data.get('account_id')
        
        if not symbol or quantity <= 0 or price <= 0:
            return jsonify({"success": False, "error": "参数错误：股票代码、数量和价格必须大于0"}), 400
        
        if not account_id:
            return jsonify({"success": False, "error": "请选择交易账户"}), 400
        
        tc, qc, config = get_trade_context_for_account(int(account_id), user_id=request.user_id)
        if not tc:
            return jsonify({"success": False, "error": "交易服务初始化失败或账户不属于当前用户"}), 500
        
        broker_type = config.get('broker_type')
        
        if broker_type == 'longbridge':
            # 提交卖出订单
            resp = tc.submit_order(
                symbol=symbol,
                order_type=OrderType.LO,
                side=OrderSide.Sell,
                submitted_quantity=quantity,
                submitted_price=price,
                time_in_force=TimeInForceType.Day
            )
            
            print(f"✅ [TradeAPI] 卖出订单提交成功: {symbol} | 数量:{quantity} | 价格:{price}")
            
            return jsonify({
                "success": True,
                "message": f"卖出订单提交成功: {symbol}",
                "order_id": getattr(resp, 'order_id', None),
                "symbol": symbol,
                "side": "SELL",
                "quantity": quantity,
                "price": price,
                "account_id": account_id
            })
        elif broker_type == 'tiger':
            # 老虎证券交易
            resp = tc.place_order(
                symbol=symbol,
                action='SELL',
                quantity=quantity,
                order_type='LIMIT',
                price=price,
                time_in_force='DAY'
            )
            
            print(f"✅ [TradeAPI] 老虎证券卖出订单提交成功: {symbol} | 数量:{quantity} | 价格:{price}")
            
            return jsonify({
                "success": True,
                "message": f"卖出订单提交成功: {symbol}",
                "order_id": resp.get('order_id', ''),
                "symbol": symbol,
                "side": "SELL",
                "quantity": quantity,
                "price": price,
                "account_id": account_id
            })
        else:
            return jsonify({"success": False, "error": "不支持的券商类型"}), 400
        
    except Exception as e:
        print(f"❌ [TradeAPI] 卖出失败: {e}")
        import traceback
        print(traceback.format_exc())
        return jsonify({"success": False, "error": str(e)}), 500


@trade_bp.route('/api/trade/cancel', methods=['POST'])
@login_required
def cancel_order():
    """撤销订单 - 支持指定账户"""
    if settings.TRADE_SERVICE_ENABLED:
        data = request.json or {}
        return _proxy_trade_service(
            '/orders/cancel',
            method='POST',
            payload={
                'order_id': data.get('order_id'),
                'account_id': data.get('account_id')
            }
        )

    try:
        data = request.json
        order_id = data.get('order_id')
        account_id = data.get('account_id')
        
        if not order_id:
            return jsonify({"success": False, "error": "订单ID不能为空"}), 400
        
        if not account_id:
            return jsonify({"success": False, "error": "请选择交易账户"}), 400
        
        tc, qc, config = get_trade_context_for_account(int(account_id), user_id=request.user_id)
        if not tc:
            return jsonify({"success": False, "error": "交易服务初始化失败或账户不属于当前用户"}), 500
        
        broker_type = config.get('broker_type')
        
        if broker_type == 'longbridge':
            # 撤销订单
            tc.cancel_order(order_id=order_id)
            
            print(f"✅ [TradeAPI] 撤销订单成功: {order_id}")
            
            return jsonify({
                "success": True,
                "message": f"订单 {order_id} 已撤销",
                "order_id": order_id,
                "account_id": account_id
            })
        elif broker_type == 'tiger':
            # 老虎证券撤单
            success = tc.cancel_order(order_id=order_id)
            
            if success:
                print(f"✅ [TradeAPI] 老虎证券撤销订单成功: {order_id}")
                return jsonify({
                    "success": True,
                    "message": f"订单 {order_id} 已撤销",
                    "order_id": order_id,
                    "account_id": account_id
                })
            else:
                return jsonify({"success": False, "error": "撤单失败"}), 500
        else:
            return jsonify({"success": False, "error": "不支持的券商类型"}), 400
        
    except Exception as e:
        print(f"❌ [TradeAPI] 撤销订单失败: {e}")
        import traceback
        print(traceback.format_exc())
        return jsonify({"success": False, "error": str(e)}), 500


@trade_bp.route('/api/stock_quote/<symbol>', methods=['GET'])
@login_required
def get_stock_quote(symbol):
    """获取股票实时行情 - 支持多账户"""
    try:
        account_id = request.args.get('account_id')
        
        # 如果没有指定账户，使用默认券商账户
        if not account_id:
            account_id = _resolve_default_account_id(request.user_id)
            if not account_id:
                return jsonify({"success": False, "error": "当前用户没有可用的交易账户"}), 400
        
        tc, qc, config = get_trade_context_for_account(int(account_id), user_id=request.user_id)
        if not tc:
            return jsonify({"success": False, "error": "交易服务初始化失败或账户不属于当前用户"}), 500
        
        broker_type = config.get('broker_type')
        
        if broker_type == 'longbridge':
            # 长桥证券获取行情
            try:
                print(f"[TradeAPI] 长桥获取行情: symbol={symbol}")
                quotes = qc.quote([symbol])
                print(f"[TradeAPI] 长桥返回: quotes={quotes}")
                if quotes and len(quotes) > 0:
                    q = quotes[0]
                    price = _unpack(q.last_done)
                    if price == 0:
                        price = _unpack(getattr(q, 'prev_close', 0))

                    return jsonify({
                        "success": True,
                        "data": {
                            "symbol": symbol,
                            "price": price,
                            "change": _unpack(getattr(q, 'change', 0)),
                            "change_percent": _unpack(getattr(q, 'change_percent', 0)),
                            "volume": _unpack(getattr(q, 'volume', 0)),
                            "open": _unpack(getattr(q, 'open', 0)),
                            "high": _unpack(getattr(q, 'high', 0)),
                            "low": _unpack(getattr(q, 'low', 0)),
                            "prev_close": _unpack(getattr(q, 'prev_close', 0))
                        }
                    })
                else:
                    return jsonify({"success": False, "error": f"无法获取股票 {symbol} 的行情，请检查股票代码是否正确"}), 400
            except Exception as e:
                print(f"❌ [TradeAPI] 长桥获取行情失败: {e}")
                import traceback
                print(traceback.format_exc())
                return jsonify({"success": False, "error": f"获取行情失败: {str(e)}"}), 500
                
        elif broker_type == 'tiger':
            # 老虎证券获取行情
            try:
                print(f"[TradeAPI] 老虎获取行情: symbol={symbol}")
                quotes = tc.get_quote([symbol])
                print(f"[TradeAPI] 老虎返回: quotes={quotes}")
                if quotes and symbol in quotes:
                    q = quotes[symbol]
                    return jsonify({
                        "success": True,
                        "data": {
                            "symbol": symbol,
                            "price": q.get('last_price', 0),
                            "change": q.get('last_price', 0) - q.get('prev_close', 0),
                            "change_percent": ((q.get('last_price', 0) - q.get('prev_close', 0)) / q.get('prev_close', 0) * 100) if q.get('prev_close', 0) > 0 else 0,
                            "volume": q.get('volume', 0),
                            "open": q.get('open', 0),
                            "high": q.get('high', 0),
                            "low": q.get('low', 0),
                            "prev_close": q.get('prev_close', 0)
                        }
                    })
                else:
                    return jsonify({"success": False, "error": "无法获取股票行情"}), 400
            except Exception as e:
                error_msg = str(e)
                print(f"❌ [TradeAPI] 老虎获取行情失败: {e}")
                import traceback
                print(traceback.format_exc())
                
                # 检查是否是权限错误
                if "permission denied" in error_msg.lower() or "do not have permissions" in error_msg.lower():
                    return jsonify({
                        "success": False, 
                        "error": "老虎证券账户没有美股行情权限，请在老虎证券官网开通行情权限后再试"
                    }), 403
                
                return jsonify({"success": False, "error": f"获取行情失败: {error_msg}"}), 500
        else:
            return jsonify({"success": False, "error": "不支持的券商类型"}), 400
            
    except Exception as e:
        print(f"❌ [TradeAPI] 获取股票行情失败: {e}")
        import traceback
        print(traceback.format_exc())
        return jsonify({"success": False, "error": str(e)}), 500
