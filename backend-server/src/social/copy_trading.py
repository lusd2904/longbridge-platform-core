"""
社交跟单系统
投资组合分享、跟单交易、排行榜
"""
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import asyncio

logger = logging.getLogger(__name__)


class TraderTier(Enum):
    """交易员等级"""
    ROOKIE = "rookie"           # 新手
    INTERMEDIATE = "intermediate"  # 中级
    ADVANCED = "advanced"       # 高级
    EXPERT = "expert"           # 专家
    MASTER = "master"           # 大师


class CopyTradeStatus(Enum):
    """跟单状态"""
    ACTIVE = "active"           # 活跃
    PAUSED = "paused"           # 暂停
    STOPPED = "stopped"         # 停止


@dataclass
class TraderProfile:
    """交易员档案"""
    user_id: str
    username: str
    avatar: str
    tier: TraderTier
    followers: int = 0
    total_return: float = 0.0
    monthly_return: float = 0.0
    win_rate: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    trading_days: int = 0
    description: str = ""
    is_public: bool = True
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class CopyTradeConfig:
    """跟单配置"""
    follower_id: str
    trader_id: str
    copy_mode: str  # "fixed" | "ratio" | "mirror"
    fixed_amount: float = 0.0  # 固定金额
    copy_ratio: float = 1.0    # 跟单比例
    max_position: float = 10000.0  # 最大持仓
    stop_loss: float = 0.0     # 止损比例
    take_profit: float = 0.0   # 止盈比例
    status: CopyTradeStatus = CopyTradeStatus.ACTIVE
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class TradeSignal:
    """交易信号"""
    signal_id: str
    trader_id: str
    symbol: str
    action: str  # "buy" | "sell"
    quantity: float
    price: float
    timestamp: str
    copied_by: List[str] = field(default_factory=list)


@dataclass
class PortfolioShare:
    """投资组合分享"""
    share_id: str
    user_id: str
    username: str
    title: str
    description: str
    holdings: List[Dict]
    total_value: float
    total_return: float
    is_public: bool = True
    likes: int = 0
    comments: int = 0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


class CopyTradingService:
    """跟单交易服务"""
    
    def __init__(self):
        self.traders: Dict[str, TraderProfile] = {}
        self.copy_configs: Dict[str, CopyTradeConfig] = {}
        self.trade_signals: List[TradeSignal] = []
        self.portfolio_shares: Dict[str, PortfolioShare] = {}
        self.followers: Dict[str, List[str]] = {}  # trader_id -> [follower_ids]
        
        logger.info("跟单交易服务初始化完成")
    
    def register_trader(self, profile: TraderProfile) -> bool:
        """
        注册交易员
        
        Args:
            profile: 交易员档案
        
        Returns:
            是否成功
        """
        if profile.user_id in self.traders:
            logger.warning(f"交易员已存在: {profile.user_id}")
            return False
        
        self.traders[profile.user_id] = profile
        self.followers[profile.user_id] = []
        
        logger.info(f"交易员已注册: {profile.username}")
        return True
    
    def update_trader_stats(
        self,
        user_id: str,
        return_rate: float,
        win_rate: float,
        drawdown: float
    ):
        """更新交易员统计"""
        if user_id not in self.traders:
            return
        
        trader = self.traders[user_id]
        trader.monthly_return = return_rate
        trader.win_rate = win_rate
        trader.max_drawdown = drawdown
        
        # 更新等级
        trader.tier = self._calculate_tier(trader)
        
        logger.info(f"交易员统计已更新: {trader.username}, 等级: {trader.tier.value}")
    
    def _calculate_tier(self, trader: TraderProfile) -> TraderTier:
        """计算交易员等级"""
        # 根据收益、胜率、回撤综合评分
        score = (
            trader.total_return * 0.4 +
            trader.win_rate * 100 * 0.3 +
            (1 - trader.max_drawdown) * 100 * 0.3
        )
        
        if score >= 80:
            return TraderTier.MASTER
        elif score >= 60:
            return TraderTier.EXPERT
        elif score >= 40:
            return TraderTier.ADVANCED
        elif score >= 20:
            return TraderTier.INTERMEDIATE
        else:
            return TraderTier.ROOKIE
    
    def follow_trader(self, follower_id: str, trader_id: str) -> bool:
        """
        关注交易员
        
        Args:
            follower_id: 关注者ID
            trader_id: 交易员ID
        
        Returns:
            是否成功
        """
        if trader_id not in self.traders:
            logger.warning(f"交易员不存在: {trader_id}")
            return False
        
        if follower_id in self.followers.get(trader_id, []):
            logger.warning(f"已关注该交易员: {trader_id}")
            return False
        
        self.followers[trader_id].append(follower_id)
        self.traders[trader_id].followers += 1
        
        logger.info(f"用户 {follower_id} 关注了交易员 {trader_id}")
        return True
    
    def unfollow_trader(self, follower_id: str, trader_id: str) -> bool:
        """取消关注"""
        if trader_id not in self.followers:
            return False
        
        if follower_id in self.followers[trader_id]:
            self.followers[trader_id].remove(follower_id)
            self.traders[trader_id].followers -= 1
            
            logger.info(f"用户 {follower_id} 取消关注了交易员 {trader_id}")
            return True
        
        return False
    
    def start_copy_trading(self, config: CopyTradeConfig) -> bool:
        """
        开始跟单
        
        Args:
            config: 跟单配置
        
        Returns:
            是否成功
        """
        if config.trader_id not in self.traders:
            logger.warning(f"交易员不存在: {config.trader_id}")
            return False
        
        config_id = f"{config.follower_id}_{config.trader_id}"
        self.copy_configs[config_id] = config
        
        # 自动关注
        self.follow_trader(config.follower_id, config.trader_id)
        
        logger.info(f"跟单已启动: {config.follower_id} -> {config.trader_id}")
        return True
    
    def stop_copy_trading(self, follower_id: str, trader_id: str) -> bool:
        """停止跟单"""
        config_id = f"{follower_id}_{trader_id}"
        
        if config_id in self.copy_configs:
            self.copy_configs[config_id].status = CopyTradeStatus.STOPPED
            logger.info(f"跟单已停止: {follower_id} -> {trader_id}")
            return True
        
        return False
    
    def pause_copy_trading(self, follower_id: str, trader_id: str) -> bool:
        """暂停跟单"""
        config_id = f"{follower_id}_{trader_id}"
        
        if config_id in self.copy_configs:
            self.copy_configs[config_id].status = CopyTradeStatus.PAUSED
            logger.info(f"跟单已暂停: {follower_id} -> {trader_id}")
            return True
        
        return False
    
    def resume_copy_trading(self, follower_id: str, trader_id: str) -> bool:
        """恢复跟单"""
        config_id = f"{follower_id}_{trader_id}"
        
        if config_id in self.copy_configs:
            self.copy_configs[config_id].status = CopyTradeStatus.ACTIVE
            logger.info(f"跟单已恢复: {follower_id} -> {trader_id}")
            return True
        
        return False
    
    def publish_trade_signal(self, signal: TradeSignal) -> List[Dict]:
        """
        发布交易信号
        
        Args:
            signal: 交易信号
        
        Returns:
            生成的跟单订单列表
        """
        self.trade_signals.append(signal)
        
        # 查找跟单者
        orders = []
        for config_id, config in self.copy_configs.items():
            if config.trader_id != signal.trader_id:
                continue
            
            if config.status != CopyTradeStatus.ACTIVE:
                continue
            
            # 生成跟单订单
            order = self._generate_copy_order(signal, config)
            if order:
                orders.append(order)
                signal.copied_by.append(config.follower_id)
        
        logger.info(f"交易信号已发布: {signal.signal_id}, 跟单数: {len(orders)}")
        return orders
    
    def _generate_copy_order(
        self,
        signal: TradeSignal,
        config: CopyTradeConfig
    ) -> Optional[Dict]:
        """生成跟单订单"""
        # 计算跟单数量
        if config.copy_mode == "fixed":
            quantity = config.fixed_amount / signal.price
        elif config.copy_mode == "ratio":
            quantity = signal.quantity * config.copy_ratio
        elif config.copy_mode == "mirror":
            quantity = signal.quantity
        else:
            return None
        
        # 检查最大持仓限制
        order_value = quantity * signal.price
        if order_value > config.max_position:
            quantity = config.max_position / signal.price
        
        return {
            "follower_id": config.follower_id,
            "trader_id": signal.trader_id,
            "signal_id": signal.signal_id,
            "symbol": signal.symbol,
            "action": signal.action,
            "quantity": quantity,
            "price": signal.price,
            "timestamp": datetime.now().isoformat()
        }
    
    def get_trader_ranking(
        self,
        sort_by: str = "total_return",
        limit: int = 100
    ) -> List[TraderProfile]:
        """
        获取交易员排行榜
        
        Args:
            sort_by: 排序字段
            limit: 数量限制
        
        Returns:
            交易员列表
        """
        traders = list(self.traders.values())
        
        # 排序
        if sort_by == "total_return":
            traders.sort(key=lambda x: x.total_return, reverse=True)
        elif sort_by == "monthly_return":
            traders.sort(key=lambda x: x.monthly_return, reverse=True)
        elif sort_by == "win_rate":
            traders.sort(key=lambda x: x.win_rate, reverse=True)
        elif sort_by == "sharpe_ratio":
            traders.sort(key=lambda x: x.sharpe_ratio, reverse=True)
        elif sort_by == "followers":
            traders.sort(key=lambda x: x.followers, reverse=True)
        
        return traders[:limit]
    
    def get_trader_detail(self, trader_id: str) -> Optional[Dict]:
        """获取交易员详情"""
        if trader_id not in self.traders:
            return None
        
        trader = self.traders[trader_id]
        
        # 获取最近交易信号
        recent_signals = [
            signal for signal in self.trade_signals
            if signal.trader_id == trader_id
        ][-20:]
        
        return {
            "profile": {
                "user_id": trader.user_id,
                "username": trader.username,
                "avatar": trader.avatar,
                "tier": trader.tier.value,
                "followers": trader.followers,
                "total_return": trader.total_return,
                "monthly_return": trader.monthly_return,
                "win_rate": trader.win_rate,
                "max_drawdown": trader.max_drawdown,
                "sharpe_ratio": trader.sharpe_ratio,
                "trading_days": trader.trading_days,
                "description": trader.description
            },
            "recent_signals": [
                {
                    "symbol": s.symbol,
                    "action": s.action,
                    "quantity": s.quantity,
                    "price": s.price,
                    "timestamp": s.timestamp,
                    "copied_count": len(s.copied_by)
                }
                for s in recent_signals
            ]
        }
    
    def share_portfolio(self, share: PortfolioShare) -> str:
        """
        分享投资组合
        
        Args:
            share: 组合分享
        
        Returns:
            分享ID
        """
        self.portfolio_shares[share.share_id] = share
        logger.info(f"投资组合已分享: {share.share_id}")
        return share.share_id
    
    def get_portfolio_shares(
        self,
        sort_by: str = "likes",
        limit: int = 50
    ) -> List[PortfolioShare]:
        """获取组合分享列表"""
        shares = list(self.portfolio_shares.values())
        
        if sort_by == "likes":
            shares.sort(key=lambda x: x.likes, reverse=True)
        elif sort_by == "return":
            shares.sort(key=lambda x: x.total_return, reverse=True)
        elif sort_by == "recent":
            shares.sort(key=lambda x: x.created_at, reverse=True)
        
        return shares[:limit]
    
    def like_portfolio(self, share_id: str, user_id: str) -> bool:
        """点赞组合"""
        if share_id in self.portfolio_shares:
            self.portfolio_shares[share_id].likes += 1
            return True
        return False
    
    def get_copy_performance(
        self,
        follower_id: str,
        trader_id: str
    ) -> Dict:
        """获取跟单绩效"""
        config_id = f"{follower_id}_{trader_id}"
        
        if config_id not in self.copy_configs:
            return {"error": "跟单配置不存在"}
        
        config = self.copy_configs[config_id]
        
        # 统计跟单信号
        copied_signals = [
            signal for signal in self.trade_signals
            if signal.trader_id == trader_id and follower_id in signal.copied_by
        ]
        
        return {
            "follower_id": follower_id,
            "trader_id": trader_id,
            "config": {
                "copy_mode": config.copy_mode,
                "copy_ratio": config.copy_ratio,
                "fixed_amount": config.fixed_amount,
                "status": config.status.value
            },
            "statistics": {
                "total_signals": len(copied_signals),
                "first_copy_date": copied_signals[0].timestamp if copied_signals else None,
                "last_copy_date": copied_signals[-1].timestamp if copied_signals else None
            }
        }


# 全局跟单服务实例
copy_trading_service = CopyTradingService()
