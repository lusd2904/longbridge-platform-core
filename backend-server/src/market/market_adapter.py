"""
多市场适配器
支持A股、港股、美股等多个市场
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class MarketType(Enum):
    """市场类型"""

    A_SHARE = "a_share"  # A股
    HK_STOCK = "hk_stock"  # 港股
    US_STOCK = "us_stock"  # 美股
    CRYPTO = "crypto"  # 加密货币
    FUTURES = "futures"  # 期货


class MarketStatus(Enum):
    """市场状态"""

    PRE_MARKET = "pre_market"  # 盘前
    OPEN = "open"  # 开盘
    CLOSE = "close"  # 收盘
    AFTER_HOURS = "after_hours"  # 盘后
    HALTED = "halted"  # 停牌


@dataclass
class MarketSession:
    """市场交易时段"""

    market_type: MarketType
    open_time: str
    close_time: str
    timezone: str
    pre_market_open: str | None = None
    after_hours_close: str | None = None


@dataclass
class Quote:
    """行情数据"""

    symbol: str
    market_type: MarketType
    price: float
    open: float
    high: float
    low: float
    close: float
    volume: int
    change: float
    change_percent: float
    timestamp: datetime
    bid: float | None = None
    ask: float | None = None
    bid_volume: int | None = None
    ask_volume: int | None = None


@dataclass
class MarketInfo:
    """市场信息"""

    market_type: MarketType
    name: str
    currency: str
    status: MarketStatus
    session: MarketSession
    holidays: list[str]


class BaseMarketAdapter:
    """市场适配器基类"""

    def __init__(self, market_type: MarketType):
        self.market_type = market_type
        self.is_connected = False

    async def connect(self):
        """连接市场数据源"""
        raise NotImplementedError

    async def disconnect(self):
        """断开连接"""
        raise NotImplementedError

    async def get_quote(self, symbol: str) -> Quote | None:
        """获取实时行情"""
        raise NotImplementedError

    async def get_quotes(self, symbols: list[str]) -> list[Quote]:
        """批量获取行情"""
        raise NotImplementedError

    async def get_historical_data(
        self, symbol: str, start_date: datetime, end_date: datetime, interval: str = "1d"
    ) -> list[dict]:
        """获取历史数据"""
        raise NotImplementedError

    async def get_market_info(self) -> MarketInfo:
        """获取市场信息"""
        raise NotImplementedError

    def normalize_symbol(self, symbol: str) -> str:
        """标准化股票代码"""
        return symbol.upper().strip()


class AShareAdapter(BaseMarketAdapter):
    """A股适配器"""

    def __init__(self):
        super().__init__(MarketType.A_SHARE)
        self.session = MarketSession(
            market_type=MarketType.A_SHARE,
            open_time="09:30",
            close_time="15:00",
            timezone="Asia/Shanghai",
            pre_market_open="09:15",
        )

    async def connect(self):
        """连接A股数据源"""
        logger.info("连接A股数据源...")
        # 实际实现中连接通达信、同花顺等数据源
        self.is_connected = True
        logger.info("A股数据源连接成功")

    async def disconnect(self):
        """断开连接"""
        self.is_connected = False
        logger.info("A股数据源已断开")

    async def get_quote(self, symbol: str) -> Quote | None:
        """获取A股行情"""
        symbol = self.normalize_symbol(symbol)

        # 模拟数据，实际应该调用API
        return Quote(
            symbol=symbol,
            market_type=MarketType.A_SHARE,
            price=100.0,
            open=99.0,
            high=101.0,
            low=98.5,
            close=100.0,
            volume=1000000,
            change=1.0,
            change_percent=1.01,
            timestamp=datetime.now(),
        )

    async def get_quotes(self, symbols: list[str]) -> list[Quote]:
        """批量获取A股行情"""
        quotes = []
        for symbol in symbols:
            quote = await self.get_quote(symbol)
            if quote:
                quotes.append(quote)
        return quotes

    async def get_historical_data(
        self, symbol: str, start_date: datetime, end_date: datetime, interval: str = "1d"
    ) -> list[dict]:
        """获取A股历史数据"""
        # 实际实现中调用Tushare、AKShare等库
        return []

    async def get_market_info(self) -> MarketInfo:
        """获取A股市场信息"""
        return MarketInfo(
            market_type=MarketType.A_SHARE,
            name="A股市场",
            currency="CNY",
            status=MarketStatus.OPEN,
            session=self.session,
            holidays=[],
        )

    def normalize_symbol(self, symbol: str) -> str:
        """标准化A股代码"""
        symbol = symbol.upper().strip()

        # 添加市场后缀
        if not symbol.endswith((".SH", ".SZ", ".BJ")):
            # 根据代码规则判断市场
            if symbol.startswith("6"):
                symbol += ".SH"
            elif symbol.startswith("0") or symbol.startswith("3"):
                symbol += ".SZ"
            elif symbol.startswith("8") or symbol.startswith("4"):
                symbol += ".BJ"

        return symbol


class HKStockAdapter(BaseMarketAdapter):
    """港股适配器"""

    def __init__(self):
        super().__init__(MarketType.HK_STOCK)
        self.session = MarketSession(
            market_type=MarketType.HK_STOCK,
            open_time="09:30",
            close_time="16:00",
            timezone="Asia/Hong_Kong",
            pre_market_open="09:00",
        )

    async def connect(self):
        """连接港股数据源"""
        logger.info("连接港股数据源...")
        self.is_connected = True
        logger.info("港股数据源连接成功")

    async def disconnect(self):
        """断开连接"""
        self.is_connected = False
        logger.info("港股数据源已断开")

    async def get_quote(self, symbol: str) -> Quote | None:
        """获取港股行情"""
        symbol = self.normalize_symbol(symbol)

        return Quote(
            symbol=symbol,
            market_type=MarketType.HK_STOCK,
            price=50.0,
            open=49.5,
            high=51.0,
            low=49.0,
            close=50.0,
            volume=500000,
            change=0.5,
            change_percent=1.01,
            timestamp=datetime.now(),
        )

    async def get_quotes(self, symbols: list[str]) -> list[Quote]:
        """批量获取港股行情"""
        quotes = []
        for symbol in symbols:
            quote = await self.get_quote(symbol)
            if quote:
                quotes.append(quote)
        return quotes

    async def get_historical_data(
        self, symbol: str, start_date: datetime, end_date: datetime, interval: str = "1d"
    ) -> list[dict]:
        """获取港股历史数据"""
        return []

    async def get_market_info(self) -> MarketInfo:
        """获取港股市场信息"""
        return MarketInfo(
            market_type=MarketType.HK_STOCK,
            name="港股市场",
            currency="HKD",
            status=MarketStatus.OPEN,
            session=self.session,
            holidays=[],
        )

    def normalize_symbol(self, symbol: str) -> str:
        """标准化港股代码"""
        symbol = symbol.upper().strip()

        if not symbol.endswith(".HK"):
            # 补齐5位代码
            symbol = symbol.zfill(5)
            symbol += ".HK"

        return symbol


class USStockAdapter(BaseMarketAdapter):
    """美股适配器"""

    def __init__(self):
        super().__init__(MarketType.US_STOCK)
        self.session = MarketSession(
            market_type=MarketType.US_STOCK,
            open_time="09:30",
            close_time="16:00",
            timezone="America/New_York",
            pre_market_open="04:00",
            after_hours_close="20:00",
        )

    async def connect(self):
        """连接美股数据源"""
        logger.info("连接美股数据源...")
        self.is_connected = True
        logger.info("美股数据源连接成功")

    async def disconnect(self):
        """断开连接"""
        self.is_connected = False
        logger.info("美股数据源已断开")

    async def get_quote(self, symbol: str) -> Quote | None:
        """获取美股行情"""
        symbol = self.normalize_symbol(symbol)

        return Quote(
            symbol=symbol,
            market_type=MarketType.US_STOCK,
            price=150.0,
            open=148.0,
            high=152.0,
            low=147.5,
            close=150.0,
            volume=10000000,
            change=2.0,
            change_percent=1.35,
            timestamp=datetime.now(),
        )

    async def get_quotes(self, symbols: list[str]) -> list[Quote]:
        """批量获取美股行情"""
        quotes = []
        for symbol in symbols:
            quote = await self.get_quote(symbol)
            if quote:
                quotes.append(quote)
        return quotes

    async def get_historical_data(
        self, symbol: str, start_date: datetime, end_date: datetime, interval: str = "1d"
    ) -> list[dict]:
        """获取美股历史数据"""
        return []

    async def get_market_info(self) -> MarketInfo:
        """获取美股市场信息"""
        return MarketInfo(
            market_type=MarketType.US_STOCK,
            name="美股市场",
            currency="USD",
            status=MarketStatus.OPEN,
            session=self.session,
            holidays=[],
        )

    def normalize_symbol(self, symbol: str) -> str:
        """标准化美股代码"""
        return symbol.upper().strip()


class CryptoAdapter(BaseMarketAdapter):
    """加密货币适配器"""

    def __init__(self):
        super().__init__(MarketType.CRYPTO)
        self.session = MarketSession(
            market_type=MarketType.CRYPTO, open_time="00:00", close_time="23:59", timezone="UTC"
        )

    async def connect(self):
        """连接加密货币数据源"""
        logger.info("连接加密货币数据源...")
        self.is_connected = True
        logger.info("加密货币数据源连接成功")

    async def disconnect(self):
        """断开连接"""
        self.is_connected = False
        logger.info("加密货币数据源已断开")

    async def get_quote(self, symbol: str) -> Quote | None:
        """获取加密货币行情"""
        symbol = self.normalize_symbol(symbol)

        return Quote(
            symbol=symbol,
            market_type=MarketType.CRYPTO,
            price=50000.0,
            open=49000.0,
            high=51000.0,
            low=48500.0,
            close=50000.0,
            volume=100000,
            change=1000.0,
            change_percent=2.04,
            timestamp=datetime.now(),
        )

    async def get_quotes(self, symbols: list[str]) -> list[Quote]:
        """批量获取加密货币行情"""
        quotes = []
        for symbol in symbols:
            quote = await self.get_quote(symbol)
            if quote:
                quotes.append(quote)
        return quotes

    async def get_historical_data(
        self, symbol: str, start_date: datetime, end_date: datetime, interval: str = "1d"
    ) -> list[dict]:
        """获取加密货币历史数据"""
        return []

    async def get_market_info(self) -> MarketInfo:
        """获取加密货币市场信息"""
        return MarketInfo(
            market_type=MarketType.CRYPTO,
            name="加密货币市场",
            currency="USDT",
            status=MarketStatus.OPEN,
            session=self.session,
            holidays=[],
        )

    def normalize_symbol(self, symbol: str) -> str:
        """标准化加密货币代码"""
        symbol = symbol.upper().strip()

        # 添加USDT后缀
        if not symbol.endswith("USDT") and not symbol.endswith("/USDT"):
            symbol = f"{symbol}/USDT"

        return symbol


class UnifiedMarketData:
    """统一市场数据服务"""

    def __init__(self):
        self.adapters: dict[MarketType, BaseMarketAdapter] = {
            MarketType.A_SHARE: AShareAdapter(),
            MarketType.HK_STOCK: HKStockAdapter(),
            MarketType.US_STOCK: USStockAdapter(),
            MarketType.CRYPTO: CryptoAdapter(),
        }
        self.is_connected = False

    async def connect_all(self):
        """连接所有市场"""
        logger.info("连接所有市场数据源...")

        tasks = [adapter.connect() for adapter in self.adapters.values()]
        await asyncio.gather(*tasks, return_exceptions=True)

        self.is_connected = True
        logger.info("所有市场数据源连接完成")

    async def disconnect_all(self):
        """断开所有市场"""
        tasks = [adapter.disconnect() for adapter in self.adapters.values()]
        await asyncio.gather(*tasks, return_exceptions=True)

        self.is_connected = False
        logger.info("所有市场数据源已断开")

    def get_adapter(self, market_type: MarketType) -> BaseMarketAdapter | None:
        """获取市场适配器"""
        return self.adapters.get(market_type)

    async def get_quote(self, symbol: str, market_type: MarketType) -> Quote | None:
        """获取行情"""
        adapter = self.get_adapter(market_type)
        if adapter:
            return await adapter.get_quote(symbol)
        return None

    async def get_quotes(self, symbols_by_market: dict[MarketType, list[str]]) -> dict[MarketType, list[Quote]]:
        """批量获取多市场行情"""
        results = {}

        for market_type, symbols in symbols_by_market.items():
            adapter = self.get_adapter(market_type)
            if adapter:
                quotes = await adapter.get_quotes(symbols)
                results[market_type] = quotes

        return results

    def detect_market_type(self, symbol: str) -> MarketType:
        """检测市场类型"""
        symbol = symbol.upper().strip()

        # A股
        if symbol.endswith(".SH") or symbol.endswith(".SZ") or symbol.endswith(".BJ"):
            return MarketType.A_SHARE

        # 港股
        if symbol.endswith(".HK"):
            return MarketType.HK_STOCK

        # 加密货币
        if symbol.endswith("USDT") or symbol.endswith("/USDT") or symbol in ["BTC", "ETH", "BNB"]:
            return MarketType.CRYPTO

        # 默认为美股
        return MarketType.US_STOCK

    async def get_all_market_info(self) -> dict[MarketType, MarketInfo]:
        """获取所有市场信息"""
        results = {}

        for market_type, adapter in self.adapters.items():
            info = await adapter.get_market_info()
            results[market_type] = info

        return results


# 全局统一市场数据服务
unified_market = UnifiedMarketData()
