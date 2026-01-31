"""
IBKR 客户端模块

使用 ib_insync 连接 TWS/IB Gateway，订阅行情数据。
第一阶段只需要行情，不需要下单功能。
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Any

import pandas as pd
from ib_insync import IB, BarData, Contract, Stock, util
from loguru import logger

if TYPE_CHECKING:
    from collections.abc import Callable


class IBKRClient:
    """IBKR 客户端封装"""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 7497,
        client_id: int = 1,
        timeout: int = 30,
        readonly: bool = True,
    ):
        """
        初始化 IBKR 客户端

        Args:
            host: TWS/Gateway 主机地址
            port: 端口号 (7497=TWS, 4001=Gateway)
            client_id: 客户端ID
            timeout: 连接超时（秒）
            readonly: 只读模式
        """
        self.host = host
        self.port = port
        self.client_id = client_id
        self.timeout = timeout
        self.readonly = readonly
        self.ib = IB()
        self._bar_callbacks: dict[str, list[Callable[[str, BarData], None]]] = {}

    @property
    def is_connected(self) -> bool:
        """是否已连接"""
        return self.ib.isConnected()

    async def connect(self) -> bool:
        """
        连接到 TWS/Gateway

        Returns:
            是否连接成功
        """
        try:
            await self.ib.connectAsync(
                host=self.host,
                port=self.port,
                clientId=self.client_id,
                timeout=self.timeout,
                readonly=self.readonly,
            )
            logger.info(f"已连接到 IBKR: {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"连接 IBKR 失败: {e}")
            return False

    def connect_sync(self) -> bool:
        """同步连接"""
        try:
            self.ib.connect(
                host=self.host,
                port=self.port,
                clientId=self.client_id,
                timeout=self.timeout,
                readonly=self.readonly,
            )
            logger.info(f"已连接到 IBKR: {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"连接 IBKR 失败: {e}")
            return False

    def disconnect(self) -> None:
        """断开连接"""
        if self.is_connected:
            self.ib.disconnect()
            logger.info("已断开 IBKR 连接")

    def create_stock_contract(
        self,
        symbol: str,
        exchange: str = "SMART",
        currency: str = "USD",
    ) -> Stock:
        """
        创建股票合约

        Args:
            symbol: 股票代码
            exchange: 交易所
            currency: 货币

        Returns:
            Stock 合约对象
        """
        return Stock(symbol, exchange, currency)

    def qualify_contract(self, contract: Contract) -> Contract | None:
        """
        验证合约

        Args:
            contract: 合约对象

        Returns:
            验证后的合约，失败返回 None
        """
        try:
            qualified = self.ib.qualifyContracts(contract)
            if qualified:
                return qualified[0]
        except Exception as e:
            logger.error(f"验证合约失败: {e}")
        return None

    def get_historical_bars(
        self,
        contract: Contract,
        duration: str = "1 D",
        bar_size: str = "1 min",
        what_to_show: str = "TRADES",
        use_rth: bool = True,
        end_datetime: datetime | str = "",
    ) -> pd.DataFrame:
        """
        获取历史K线数据

        Args:
            contract: 合约对象
            duration: 数据时长 (e.g., "1 D", "1 W", "1 M")
            bar_size: K线周期 (e.g., "1 min", "5 mins", "1 hour", "1 day")
            what_to_show: 数据类型 (TRADES, MIDPOINT, BID, ASK)
            use_rth: 是否只用正规交易时段
            end_datetime: 结束时间

        Returns:
            DataFrame with columns: date, open, high, low, close, volume, average, barCount
        """
        try:
            bars = self.ib.reqHistoricalData(
                contract,
                endDateTime=end_datetime,
                durationStr=duration,
                barSizeSetting=bar_size,
                whatToShow=what_to_show,
                useRTH=use_rth,
                formatDate=1,
            )
            if bars:
                df = util.df(bars)
                logger.info(f"获取 {contract.symbol} 历史数据: {len(df)} 条")
                return df
            else:
                logger.warning(f"未获取到 {contract.symbol} 的历史数据")
                return pd.DataFrame()
        except Exception as e:
            logger.error(f"获取历史数据失败: {e}")
            return pd.DataFrame()

    def get_daily_bars(
        self,
        contract: Contract,
        duration: str = "1 Y",
    ) -> pd.DataFrame:
        """
        获取日线数据（用于计算 MA20、ATR 等）

        Args:
            contract: 合约对象
            duration: 数据时长

        Returns:
            日线 DataFrame
        """
        return self.get_historical_bars(
            contract,
            duration=duration,
            bar_size="1 day",
            what_to_show="TRADES",
            use_rth=True,
        )

    def get_intraday_bars(
        self,
        contract: Contract,
        duration: str = "1 D",
        bar_size: str = "1 min",
    ) -> pd.DataFrame:
        """
        获取日内分钟数据

        Args:
            contract: 合约对象
            duration: 数据时长
            bar_size: K线周期

        Returns:
            分钟线 DataFrame
        """
        return self.get_historical_bars(
            contract,
            duration=duration,
            bar_size=bar_size,
            what_to_show="TRADES",
            use_rth=True,
        )

    def subscribe_realtime_bars(
        self,
        contract: Contract,
        callback: Callable[[str, BarData], None],
        what_to_show: str = "TRADES",
        use_rth: bool = True,
    ) -> Any:
        """
        订阅实时5秒K线

        Args:
            contract: 合约对象
            callback: 回调函数 (symbol, bar) -> None
            what_to_show: 数据类型
            use_rth: 是否只用正规交易时段

        Returns:
            订阅句柄
        """
        symbol = contract.symbol

        def on_bar_update(bars: Any, has_new_bar: bool) -> None:
            if has_new_bar and bars:
                callback(symbol, bars[-1])

        try:
            bars = self.ib.reqRealTimeBars(
                contract,
                barSize=5,  # 5秒K线
                whatToShow=what_to_show,
                useRTH=use_rth,
            )
            bars.updateEvent += on_bar_update
            logger.info(f"已订阅 {symbol} 实时数据")
            return bars
        except Exception as e:
            logger.error(f"订阅实时数据失败: {e}")
            return None

    def get_market_data_snapshot(self, contract: Contract) -> dict[str, Any]:
        """
        获取行情快照

        Args:
            contract: 合约对象

        Returns:
            包含 last, bid, ask, volume 等的字典
        """
        try:
            self.ib.reqMktData(contract, "", False, False)
            self.ib.sleep(1)  # 等待数据

            ticker = self.ib.ticker(contract)
            if ticker:
                return {
                    "symbol": contract.symbol,
                    "last": ticker.last,
                    "bid": ticker.bid,
                    "ask": ticker.ask,
                    "bid_size": ticker.bidSize,
                    "ask_size": ticker.askSize,
                    "volume": ticker.volume,
                    "high": ticker.high,
                    "low": ticker.low,
                    "close": ticker.close,
                    "time": ticker.time,
                }
        except Exception as e:
            logger.error(f"获取行情快照失败: {e}")

        return {}

    def run_loop(self) -> None:
        """运行事件循环（阻塞）"""
        logger.info("启动 IBKR 事件循环...")
        self.ib.run()

    def sleep(self, seconds: float) -> None:
        """在事件循环中等待"""
        self.ib.sleep(seconds)

    async def sleep_async(self, seconds: float) -> None:
        """异步等待"""
        await asyncio.sleep(seconds)

    def __enter__(self) -> "IBKRClient":
        self.connect_sync()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.disconnect()
