import time

from config.Config import AppConfig  # 导入 AppConfig
from shared.longbridge import OrderSide, OrderType, TimeInForceType
from utils.MonitorLink import MonitorLink


class TradeEngine:
    def __init__(self, tc, qc):
        self.tc = tc
        self.qc = qc

    def _unpack(self, obj):
        """物理脱壳：安全转换 SDK 包装对象"""
        if obj is None:
            return 0.0
        val = getattr(obj, "value", obj)
        try:
            return float(val)
        except:
            return 0.0

    def sync_market_data(self, symbols):
        """行情对齐：通过分批请求物理避让 QPS 限制"""
        import datetime

        from pytz import timezone

        price_map = {}
        cash_total_hkd = 0.0
        # 港币到美元的汇率（可以根据实际情况调整或从API获取）
        hkd_to_usd_rate = 0.128

        # 获取当前时间（美东时间）
        et = timezone("US/Eastern")
        now = datetime.datetime.now(et)
        current_hour = now.hour
        current_minute = now.minute
        current_time = current_hour + current_minute / 60.0

        # 美股交易时间（美东时间）
        # 盘前：4:00 AM - 9:30 AM
        # 盘中：9:30 AM - 4:00 PM
        # 盘后：4:00 PM - 8:00 PM
        # 夜盘：8:00 PM 以后
        is_pre_market = 4.0 <= current_time < 9.5
        is_regular_hours = 9.5 <= current_time < 16.0
        is_post_market = 16.0 <= current_time < 20.0
        is_night_market = current_time >= 20.0 or current_time < 4.0

        MonitorLink.log(
            f"🕐 [时间] 当前美东时间: {now.strftime('%H:%M:%S')} | 盘前:{is_pre_market} | 盘中:{is_regular_hours} | 盘后:{is_post_market} | 夜盘:{is_night_market}"
        )

        try:
            acc_list = self.tc.account_balance()
            for acc in acc_list:
                balances = getattr(acc, "balances", [acc])
                for b in balances:
                    cash_total_hkd += self._unpack(getattr(b, "total_cash", 0.0))

            if symbols:
                batch_size = 25  # 减少批量请求大小，从 50 改为 25
                for i in range(0, len(symbols), batch_size):
                    batch = symbols[i : i + batch_size]
                    try:
                        if self.qc:
                            quotes = self.qc.quote(batch)
                            for q in quotes:
                                # 尝试获取实时价格，优先使用last_done，如果为0则使用prev_close
                                last_price = self._unpack(q.last_done)
                                prev_price = self._unpack(getattr(q, "prev_close", 0))

                                # 检查是否有盘前或盘后价格
                                pre_market_quote = getattr(q, "pre_market_quote", None)
                                post_market_quote = getattr(q, "post_market_quote", None)

                                pre_market_price = 0.0
                                post_market_price = 0.0

                                if pre_market_quote:
                                    pre_market_price = self._unpack(getattr(pre_market_quote, "last_done", 0))
                                if post_market_quote:
                                    post_market_price = self._unpack(getattr(post_market_quote, "last_done", 0))

                                # 确定最终使用的价格
                                final_price = last_price
                                if final_price == 0 and pre_market_price > 0:
                                    final_price = pre_market_price
                                if final_price == 0 and post_market_price > 0:
                                    final_price = post_market_price
                                if final_price == 0:
                                    final_price = prev_price

                                # 存储价格到price_map
                                price_map[q.symbol] = final_price

                                # 添加调试信息，查看API返回的数据结构
                                MonitorLink.log(
                                    f"📊 [行情] {q.symbol} | last_done:{last_price} | prev_close:{prev_price} | pre_market:{pre_market_price} | post_market:{post_market_price} | final_price:{final_price}"
                                )
                        else:
                            # 使用tc获取行情数据
                            for symbol in batch:
                                try:
                                    quote = self.tc.quote(symbol)
                                    if quote:
                                        # 尝试获取实时价格，优先使用last_done，如果为0则使用prev_close
                                        last_price = self._unpack(quote.last_done)
                                        prev_price = self._unpack(getattr(quote, "prev_close", 0))

                                        # 检查是否有盘前或盘后价格
                                        pre_market_quote = getattr(quote, "pre_market_quote", None)
                                        post_market_quote = getattr(quote, "post_market_quote", None)

                                        pre_market_price = 0.0
                                        post_market_price = 0.0

                                        if pre_market_quote:
                                            pre_market_price = self._unpack(getattr(pre_market_quote, "last_done", 0))
                                        if post_market_quote:
                                            post_market_price = self._unpack(getattr(post_market_quote, "last_done", 0))

                                        # 添加调试信息，查看API返回的数据结构
                                        MonitorLink.log(
                                            f"📊 [行情] {symbol} | last_done:{last_price} | prev_close:{prev_price} | pre_market:{pre_market_price} | post_market:{post_market_price}"
                                        )
                                except Exception as e:
                                    MonitorLink.log(f"❌ 单个获取行情失败: {symbol} - {e}")

                            # 所有交易时间（盘前、盘中、盘后、夜盘）都使用实时价格
                            if last_price > 0:
                                if self.qc:
                                    price_map[q.symbol] = last_price
                                    current_symbol = q.symbol
                                else:
                                    price_map[symbol] = last_price
                                    current_symbol = symbol
                                if is_night_market:
                                    MonitorLink.log(f"🌙 [夜盘] {current_symbol} 使用实时价格: {last_price}")
                                elif is_post_market:
                                    MonitorLink.log(f"🌆 [盘后] {current_symbol} 使用实时价格: {last_price}")
                                elif is_pre_market:
                                    MonitorLink.log(f"🌅 [盘前] {current_symbol} 使用实时价格: {last_price}")
                                else:
                                    MonitorLink.log(f"📈 [盘中] {current_symbol} 使用实时价格: {last_price}")
                            elif pre_market_price > 0:
                                # 非交易时间，使用盘前价格
                                if self.qc:
                                    price_map[q.symbol] = pre_market_price
                                else:
                                    price_map[symbol] = pre_market_price
                            elif post_market_price > 0:
                                # 非交易时间，使用盘后价格
                                if self.qc:
                                    price_map[q.symbol] = post_market_price
                                else:
                                    price_map[symbol] = post_market_price
                            else:
                                # 最后使用昨收价
                                if self.qc:
                                    price_map[q.symbol] = prev_price
                                else:
                                    price_map[symbol] = prev_price
                        time.sleep(2.0)  # 增加批量请求之间的延迟时间，从 1.0 改为 2.0
                    except Exception as e:
                        if "rate limit" in str(e).lower():
                            time.sleep(5)  # 增加遇到速率限制时的延迟时间，从 3 改为 5
                        continue

            # 计算美元现金
            cash_total_usd = cash_total_hkd * hkd_to_usd_rate

            # 计算持仓总市值和当日盈亏
            pos_resp = self.tc.stock_positions()
            items = (
                getattr(pos_resp, "channels", [pos_resp])[0].positions if hasattr(pos_resp, "channels") else pos_resp
            )
            total_market_value = 0.0
            total_pnl = 0.0

            for p in items:
                qty = self._unpack(p.quantity)
                if qty > 0:
                    curr_p = price_map.get(p.symbol, 0.0)
                    cost_p = self._unpack(p.cost_price)
                    market_value = curr_p * qty if curr_p > 0 else 0.0
                    pnl = (curr_p - cost_p) * qty if curr_p > 0 else 0.0
                    total_market_value += market_value
                    total_pnl += pnl

            # 计算账户总资产
            total_assets = cash_total_usd + total_market_value

            # 打印账户信息
            MonitorLink.log(
                f"💰 [账户] 现金: HK${cash_total_hkd:.2f} (${cash_total_usd:.2f} USD) | 总资产: ${total_assets:.2f} USD"
            )
            MonitorLink.log(f"📊 [账户] 持仓总市值: ${total_market_value:.2f} USD | 当日盈亏: ${total_pnl:+.2f} USD")
            MonitorLink.log(f"📡 [账户] 已获取行情: {len(price_map)}")

            return cash_total_usd, price_map, total_assets, total_market_value, total_pnl
        except Exception as e:
            MonitorLink.log(f"⚠️ 行情同步异常: {e}")
            return 0.0, {}, 0.0, 0.0, 0.0

    def get_portfolio_status(self, price_map):
        holds = {}
        try:
            pos_resp = self.tc.stock_positions()
            items = (
                getattr(pos_resp, "channels", [pos_resp])[0].positions if hasattr(pos_resp, "channels") else pos_resp
            )
            for p in items:
                qty = self._unpack(p.quantity)
                if qty > 0:
                    curr_p = price_map.get(p.symbol, 0.0)
                    cost_p = self._unpack(p.cost_price)
                    pnl = (curr_p - cost_p) * qty if curr_p > 0 else 0.0
                    # 计算盈亏比例
                    pnl_ratio = ((curr_p - cost_p) / cost_p * 100) if (curr_p > 0 and cost_p > 0) else 0.0
                    holds[p.symbol] = {"qty": qty, "price": curr_p, "cost": cost_p, "pnl": pnl, "pnl_ratio": pnl_ratio}
                    if curr_p > 0:
                        status = f"成本:{cost_p:.2f} | 盈亏:{pnl:+.2f} ({pnl_ratio:+.2f}%)"
                    else:
                        status = "待行情..."
                    MonitorLink.log(f"📦 持仓: {p.symbol} | 现价:{curr_p:.2f} | {status}")
            return holds
        except:
            return {}

    def cancel_all_orders(self):
        try:
            orders = self.tc.today_orders()
            cancel_count = 0
            for o in orders:
                if o.status in [1, 2, 3, 4]:
                    self.tc.cancel_order(o.order_id)
                    cancel_count += 1
            if cancel_count > 0:
                MonitorLink.log(f"🧹 [系统] 已清理 {cancel_count} 笔挂单。")
        except Exception as e:
            MonitorLink.log(f"⚠️ 撤单失败: {e}")

    def cancel_stale_orders(self):
        """
        撤销长时间未成交的订单
        """
        if not AppConfig.get("ENABLE_CANCEL_STRATEGY"):
            return

        try:
            orders = self.tc.today_orders()
            current_time = time.time()
            cancel_count = 0
            for o in orders:
                # 检查订单状态是否为未成交 (1:待提交, 2:待成交, 3:部分成交, 4:已提交待报)
                if o.status in [1, 2, 3, 4]:
                    # 检查订单创建时间是否超过阈值 (使用 submitted_at 字段)
                    submitted_at = getattr(o, "submitted_at", 0)
                    if submitted_at and (current_time - submitted_at) > AppConfig.get("CANCEL_ORDER_THRESHOLD_SECONDS"):
                        self.tc.cancel_order(o.order_id)
                        cancel_count += 1
                        MonitorLink.log(
                            f"🗑️ [撤单策略] 撤销订单: {o.order_id} ({o.symbol})，已超时 {int(current_time - submitted_at)} 秒。"
                        )
            if cancel_count > 0:
                MonitorLink.log(f"🧹 [撤单策略] 已根据策略清理 {cancel_count} 笔超时挂单。")
        except Exception as e:
            MonitorLink.log(f"⚠️ 撤单策略执行异常: {e}")

    def execute_startup_cancel(self):
        """
        程序启动时执行的撤单操作
        """
        MonitorLink.log("🔄 [启动撤单] 程序启动，执行初始撤单操作...")
        # 清理所有未成交订单
        self.cancel_all_orders()
        # 清理超时挂单
        self.cancel_stale_orders()
        MonitorLink.log("✅ [启动撤单] 初始撤单操作完成")

    def execute_order(self, symbol, side, quantity, price):
        try:
            order_side = OrderSide.Buy if side == "BUY" else OrderSide.Sell
            resp = self.tc.submit_order(
                symbol=symbol,
                order_type=OrderType.LO,
                side=order_side,
                submitted_quantity=quantity,
                submitted_price=price,
                time_in_force=TimeInForceType.Day,
            )
            MonitorLink.log(f"🚀 [交易] {side} {symbol} | 数量:{quantity} | 价格:{price:.2f}")
            return resp
        except Exception as e:
            MonitorLink.log(f"❌ 下单异常: {e}")
            return None

    def get_orders(self):
        """
        获取当日订单信息
        """
        try:
            orders = self.tc.today_orders()
            order_list = []
            for o in orders:
                order_info = {
                    "id": o.order_id,
                    "symbol": o.symbol,
                    "side": "BUY" if str(getattr(o, "side", "")).split(".")[-1].lower() == "buy" else "SELL",
                    "price": self._unpack(o.submitted_price),
                    "qty": self._unpack(o.submitted_quantity),
                    "status": self._get_order_status(o.status),
                    "filled_quantity": self._unpack(o.filled_quantity),
                    "create_time": getattr(o, "submitted_at", 0),
                }
                order_list.append(order_info)
            return order_list
        except Exception as e:
            MonitorLink.log(f"⚠️ 获取订单信息失败: {e}")
            return []

    def _get_order_status(self, status_code):
        """
        将订单状态码转换为可读状态
        """
        status_map = {
            1: "待提交",
            2: "待成交",
            3: "部分成交",
            4: "已提交待报",
            5: "已成交",
            6: "已撤单",
            7: "已拒绝",
            8: "已过期",
            9: "已失败",
        }
        return status_map.get(status_code, "未知")

    def get_stock_quote(self, symbol):
        """
        获取单个股票的实时行情数据
        """
        try:
            MonitorLink.log(f"🔍 [获取行情] 开始获取 {symbol} 的实时数据")
            if self.qc:
                MonitorLink.log("✅ [获取行情] QuoteContext 可用")
                try:
                    quotes = self.qc.quote([symbol])
                    MonitorLink.log(f"✅ [获取行情] 成功获取行情数据: {len(quotes)} 条")
                    if quotes:
                        q = quotes[0]
                        MonitorLink.log(f"✅ [获取行情] 成功获取 {symbol} 的行情对象")

                        # 尝试获取实时价格，优先使用last_done，如果为0则使用prev_close
                        last_price = self._unpack(q.last_done)
                        prev_price = self._unpack(getattr(q, "prev_close", 0))
                        MonitorLink.log(f"📊 [获取行情] last_price: {last_price}, prev_price: {prev_price}")

                        # 检查是否有盘前或盘后价格
                        pre_market_quote = getattr(q, "pre_market_quote", None)
                        post_market_quote = getattr(q, "post_market_quote", None)

                        pre_market_price = 0.0
                        post_market_price = 0.0

                        if pre_market_quote:
                            pre_market_price = self._unpack(getattr(pre_market_quote, "last_done", 0))
                            MonitorLink.log(f"🌅 [获取行情] 盘前价格: {pre_market_price}")
                        if post_market_quote:
                            post_market_price = self._unpack(getattr(post_market_quote, "last_done", 0))
                            MonitorLink.log(f"🌆 [获取行情] 盘后价格: {post_market_price}")

                        # 确定最终使用的价格
                        final_price = last_price
                        if final_price == 0 and pre_market_price > 0:
                            final_price = pre_market_price
                        if final_price == 0 and post_market_price > 0:
                            final_price = post_market_price
                        if final_price == 0:
                            final_price = prev_price
                        MonitorLink.log(f"🎯 [获取行情] 最终价格: {final_price}")

                        # 计算涨跌幅
                        change = 0.0
                        change_percent = 0.0
                        if prev_price > 0 and final_price > 0:
                            change = final_price - prev_price
                            change_percent = (change / prev_price) * 100
                        MonitorLink.log(f"📈 [获取行情] 涨跌幅: {change:+.2f} ({change_percent:+.2f}%)")

                        # 构建返回数据
                        stock_data = {
                            "symbol": q.symbol,
                            "name": getattr(q, "name", q.symbol),
                            "price": final_price,
                            "change": change,
                            "changePercent": change_percent,
                            "prev_close": prev_price,
                            "open": self._unpack(getattr(q, "open", 0)),
                            "high": self._unpack(getattr(q, "high", 0)),
                            "low": self._unpack(getattr(q, "low", 0)),
                            "volume": self._unpack(getattr(q, "volume", 0)),
                            "turnover": self._unpack(getattr(q, "turnover", 0)),
                            "pre_market_price": pre_market_price,
                            "post_market_price": post_market_price,
                        }

                        MonitorLink.log(
                            f"📊 [实时行情] {symbol} | 价格:{final_price:.2f} | 涨跌幅:{change_percent:+.2f}%"
                        )
                        return stock_data
                    else:
                        raise RuntimeError(f"未获取到 {symbol} 的行情数据")
                except Exception as e:
                    MonitorLink.log(f"❌ [获取行情] QuoteContext 调用失败: {e}")
                    raise RuntimeError(f"QuoteContext 调用失败: {e}") from e
            else:
                raise RuntimeError("QuoteContext 不可用")
        except Exception as e:
            MonitorLink.log(f"❌ 获取股票行情失败: {symbol} - {e}")
            raise RuntimeError(f"获取股票行情失败: {symbol} - {e}") from e
