"""
TWS 数据服务

在独立线程中运行 ib_insync，提供：
- 持久化 TWS 连接
- 实时行情订阅
- 数据缓存供 API 读取
"""

from __future__ import annotations

import asyncio
import queue
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from loguru import logger


@dataclass
class StockData:
    """股票实时数据"""
    symbol: str
    price: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    high: float = 0.0
    low: float = 0.0
    open: float = 0.0
    close: float = 0.0  # 昨收
    volume: int = 0
    vwap: float = 0.0
    exchange: str = ""
    updated_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "price": self.price,
            "bid": self.bid,
            "ask": self.ask,
            "high": self.high,
            "low": self.low,
            "open": self.open,
            "close": self.close,
            "volume": self.volume,
            "vwap": self.vwap,
            "exchange": self.exchange,
            "updated_at": self.updated_at.isoformat(),
        }


class TWSDataService:
    """
    TWS 数据服务
    
    在独立线程中运行 ib_insync 事件循环，
    提供线程安全的数据访问接口。
    
    Usage:
        service = TWSDataService(port=7497)
        service.start()
        
        # 订阅股票
        service.subscribe(["AAPL", "TSLA", "NVDA"])
        
        # 获取数据
        data = service.get_stock_data("AAPL")
        
        # 停止服务
        service.stop()
    """
    
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 7497,
        client_id: int = 20,
        timeout: int = 10,
    ):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.timeout = timeout
        
        # 状态
        self._running = False
        self._connected = False
        self._error: str | None = None
        
        # 线程和事件循环
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        
        # 命令队列 (主线程 -> TWS 线程)
        self._command_queue: queue.Queue = queue.Queue()
        
        # 数据缓存 (线程安全)
        self._data_lock = threading.Lock()
        self._stock_data: dict[str, StockData] = {}
        self._subscribed_symbols: set[str] = set()
        
        # ib_insync 对象 (仅在 TWS 线程中访问)
        self._ib = None
        self._contracts: dict[str, Any] = {}
    
    @property
    def is_running(self) -> bool:
        return self._running
    
    @property
    def is_connected(self) -> bool:
        return self._connected
    
    @property
    def error(self) -> str | None:
        return self._error
    
    def start(self) -> bool:
        """启动服务"""
        if self._running:
            logger.warning("TWSDataService 已在运行")
            return True
        
        self._running = True
        self._error = None
        
        # 启动后台线程
        self._thread = threading.Thread(
            target=self._run_event_loop,
            name="TWSDataService",
            daemon=True,
        )
        self._thread.start()
        
        # 等待连接
        start_time = time.time()
        while time.time() - start_time < self.timeout:
            if self._connected:
                logger.info(f"TWSDataService 已连接到 TWS (端口 {self.port})")
                return True
            if self._error:
                logger.error(f"TWSDataService 连接失败: {self._error}")
                return False
            time.sleep(0.1)
        
        self._error = "连接超时"
        logger.error("TWSDataService 连接超时")
        return False
    
    def stop(self):
        """停止服务"""
        if not self._running:
            return
        
        logger.info("正在停止 TWSDataService...")
        self._running = False
        
        # 发送停止命令
        self._command_queue.put(("STOP", None))
        
        # 等待线程结束
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        
        self._connected = False
        logger.info("TWSDataService 已停止")
    
    def subscribe(self, symbols: list[str]):
        """订阅股票行情"""
        for symbol in symbols:
            if symbol not in self._subscribed_symbols:
                self._command_queue.put(("SUBSCRIBE", symbol.upper()))
                self._subscribed_symbols.add(symbol.upper())
    
    def unsubscribe(self, symbols: list[str]):
        """取消订阅"""
        for symbol in symbols:
            symbol = symbol.upper()
            if symbol in self._subscribed_symbols:
                self._command_queue.put(("UNSUBSCRIBE", symbol))
                self._subscribed_symbols.discard(symbol)
    
    def get_stock_data(self, symbol: str) -> StockData | None:
        """获取股票数据 (线程安全)"""
        with self._data_lock:
            return self._stock_data.get(symbol.upper())
    
    def get_all_stock_data(self) -> dict[str, StockData]:
        """获取所有股票数据 (线程安全)"""
        with self._data_lock:
            return dict(self._stock_data)
    
    def get_subscribed_symbols(self) -> list[str]:
        """获取已订阅的股票列表"""
        return list(self._subscribed_symbols)
    
    # ============== 内部方法 (在 TWS 线程中运行) ==============
    
    def _run_event_loop(self):
        """运行事件循环 (在独立线程中)"""
        # 创建新的事件循环
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        
        try:
            self._loop.run_until_complete(self._async_main())
        except Exception as e:
            logger.error(f"TWSDataService 事件循环异常: {e}")
            self._error = str(e)
        finally:
            self._loop.close()
            self._connected = False
    
    async def _async_main(self):
        """异步主函数"""
        # 延迟导入 ib_insync (必须在有事件循环的线程中)
        try:
            from ib_insync import IB, Stock, util
        except ImportError:
            self._error = "ib_insync 未安装"
            return
        
        # 创建 IB 客户端
        self._ib = IB()
        
        # 连接 TWS
        try:
            await self._ib.connectAsync(
                self.host,
                self.port,
                clientId=self.client_id,
                timeout=self.timeout,
            )
            self._connected = True
            logger.info(f"已连接到 TWS: {self.host}:{self.port}")
        except Exception as e:
            self._error = f"连接失败: {e}"
            return
        
        # 注册断开回调
        self._ib.disconnectedEvent += self._on_disconnected
        
        # 主循环：处理命令和事件
        while self._running and self._ib.isConnected():
            # 处理命令队列
            await self._process_commands()
            
            # 让 ib_insync 处理事件
            await asyncio.sleep(0.1)
        
        # 断开连接
        if self._ib.isConnected():
            self._ib.disconnect()
    
    async def _process_commands(self):
        """处理命令队列"""
        try:
            while not self._command_queue.empty():
                cmd, data = self._command_queue.get_nowait()
                
                if cmd == "STOP":
                    self._running = False
                elif cmd == "SUBSCRIBE":
                    await self._subscribe_symbol(data)
                elif cmd == "UNSUBSCRIBE":
                    await self._unsubscribe_symbol(data)
        except queue.Empty:
            pass
    
    async def _subscribe_symbol(self, symbol: str):
        """订阅单个股票"""
        from ib_insync import Stock
        
        if symbol in self._contracts:
            return
        
        try:
            # 创建合约
            contract = Stock(symbol, "SMART", "USD")
            qualified = await self._ib.qualifyContractsAsync(contract)
            
            if not qualified:
                logger.warning(f"无法验证合约: {symbol}")
                return
            
            contract = qualified[0]
            self._contracts[symbol] = contract
            
            # 订阅行情
            self._ib.reqMktData(contract, "", False, False)
            
            # 注册更新回调
            ticker = self._ib.ticker(contract)
            if ticker:
                ticker.updateEvent += lambda t: self._on_ticker_update(symbol, t)
            
            logger.info(f"已订阅: {symbol} ({contract.exchange})")
            
            # 初始化数据
            with self._data_lock:
                self._stock_data[symbol] = StockData(
                    symbol=symbol,
                    exchange=contract.exchange,
                )
                
        except Exception as e:
            logger.error(f"订阅 {symbol} 失败: {e}")
    
    async def _unsubscribe_symbol(self, symbol: str):
        """取消订阅"""
        if symbol not in self._contracts:
            return
        
        try:
            contract = self._contracts.pop(symbol)
            self._ib.cancelMktData(contract)
            
            with self._data_lock:
                self._stock_data.pop(symbol, None)
            
            logger.info(f"已取消订阅: {symbol}")
        except Exception as e:
            logger.error(f"取消订阅 {symbol} 失败: {e}")
    
    def _on_ticker_update(self, symbol: str, ticker):
        """行情更新回调"""
        with self._data_lock:
            if symbol not in self._stock_data:
                self._stock_data[symbol] = StockData(symbol=symbol)
            
            data = self._stock_data[symbol]
            
            # 更新数据
            if ticker.last is not None and ticker.last > 0:
                data.price = ticker.last
            elif ticker.close is not None:
                data.price = ticker.close
            
            if ticker.bid is not None:
                data.bid = ticker.bid
            if ticker.ask is not None:
                data.ask = ticker.ask
            if ticker.high is not None:
                data.high = ticker.high
            if ticker.low is not None:
                data.low = ticker.low
            if ticker.open is not None:
                data.open = ticker.open
            if ticker.close is not None:
                data.close = ticker.close
            if ticker.volume is not None:
                data.volume = int(ticker.volume)
            if ticker.vwap is not None:
                data.vwap = ticker.vwap
            
            data.updated_at = datetime.now()
    
    def _on_disconnected(self):
        """断开连接回调"""
        logger.warning("TWS 连接已断开")
        self._connected = False


# 全局服务实例
_tws_service: TWSDataService | None = None


def get_tws_service() -> TWSDataService | None:
    """获取全局 TWS 服务实例"""
    return _tws_service


def init_tws_service(port: int = 7497, client_id: int = 20) -> TWSDataService:
    """初始化全局 TWS 服务"""
    global _tws_service
    
    if _tws_service is not None:
        _tws_service.stop()
    
    _tws_service = TWSDataService(port=port, client_id=client_id)
    return _tws_service


def stop_tws_service():
    """停止全局 TWS 服务"""
    global _tws_service
    
    if _tws_service is not None:
        _tws_service.stop()
        _tws_service = None
