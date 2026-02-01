"""
FastAPI 主应用

提供 REST API 接口：
- Watchlist 管理
- 实时股票状态
- 日类型分类
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

import httpx
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pydantic import BaseModel

from tbot.api.watchlist import WatchlistManager
from tbot.indicators import VWAP, OpeningRange, calculate_vwap
from tbot.regime import RegimeClassifier, extract_features
from tbot.services.tws_data_service import TWSDataService, get_tws_service, init_tws_service, stop_tws_service
from tbot.services.news_event_detector import NewsEventDetector, get_news_detector
from tbot.settings import get_settings, init_settings
from tbot.utils import get_market_session, get_trading_progress, is_trading_allowed
from tbot.utils.time import get_et_now


# ============== Pydantic Models ==============

class SymbolRequest(BaseModel):
    """添加股票请求"""
    symbol: str


class WatchlistResponse(BaseModel):
    """Watchlist 响应"""
    symbols: list[str]


class ValidateSymbolResponse(BaseModel):
    """股票验证响应"""
    valid: bool
    symbol: str
    name: str | None = None
    price: float | None = None
    error: str | None = None


class StockStatus(BaseModel):
    """股票状态"""
    symbol: str
    name: str  # 股票名称
    exchange: str | None  # 交易所
    price: float
    prev_close: float | None = None  # 昨收
    day_high: float | None = None  # 当日最高
    day_low: float | None = None  # 当日最低
    day_open: float | None = None  # 当日开盘
    ma20: float | None = None  # 20日均线
    vwap: float
    vwap_diff_pct: float
    above_vwap: bool
    or5_high: float | None
    or5_low: float | None
    or15_high: float | None
    or15_low: float | None
    or15_complete: bool
    regime: str
    regime_confidence: float
    regime_reasons: list[str]
    news_event_score: float = 0.0  # 新闻事件得分
    news_keywords: list[str] = []  # 检测到的新闻关键词
    sparkline: list[float] = []  # 今日价格走势 (简化后的价格序列)
    updated_at: str


class MarketStatusResponse(BaseModel):
    """市场状态响应"""
    session: str
    progress: float
    trading_allowed: bool
    trading_reason: str
    current_time: str


class DashboardResponse(BaseModel):
    """仪表盘完整响应"""
    market_status: MarketStatusResponse
    watchlist: list[str]
    stocks: list[StockStatus]
    data_source: str = "yahoo"  # 当前数据源


class DataSourceStatus(BaseModel):
    """数据源状态"""
    current: str  # yahoo 或 tws
    tws_available: bool
    tws_error: str | None = None


class DataSourceRequest(BaseModel):
    """切换数据源请求"""
    source: str  # yahoo 或 tws


# ============== 全局状态 ==============

watchlist_manager: WatchlistManager | None = None
stock_cache: dict[str, StockStatus] = {}
stock_price_cache: dict[str, dict[str, Any]] = {}  # 缓存真实股票数据
tws_service: TWSDataService | None = None  # TWS 数据服务
news_detector: NewsEventDetector | None = None  # 新闻检测器
current_data_source: str = "yahoo"  # 当前数据源: yahoo 或 tws


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global watchlist_manager, news_detector, tws_service
    
    settings = init_settings()
    watchlist_manager = WatchlistManager(settings.abs_data_dir / "watchlist.json")
    news_detector = get_news_detector()
    
    logger.info("FastAPI 应用启动")
    yield
    
    # 停止 TWS 服务
    if tws_service is not None:
        tws_service.stop()
    
    logger.info("FastAPI 应用关闭")


def create_app() -> FastAPI:
    """创建 FastAPI 应用"""
    app = FastAPI(
        title="T-Trade Dashboard API",
        description="日内交易提示系统 API",
        version="0.1.0",
        lifespan=lifespan,
    )
    
    # CORS 配置
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    return app


app = create_app()


# ============== API Endpoints ==============

@app.get("/")
async def root():
    """根路径"""
    return {"message": "T-Trade Dashboard API", "version": "0.1.0"}


@app.get("/api/health")
async def health_check():
    """健康检查"""
    return {"status": "ok", "timestamp": get_et_now().isoformat()}


# -------------- Data Source API --------------

@app.get("/api/datasource", response_model=DataSourceStatus)
async def get_data_source():
    """获取当前数据源状态"""
    global tws_service
    
    tws_available = False
    tws_error = None
    
    if tws_service is not None:
        tws_available = tws_service.is_connected
        if not tws_available:
            tws_error = tws_service.error or "TWS 连接已断开"
    else:
        tws_error = "TWS 服务未启动"
    
    return DataSourceStatus(
        current=current_data_source,
        tws_available=tws_available,
        tws_error=tws_error
    )


@app.post("/api/datasource", response_model=DataSourceStatus)
async def set_data_source(request: DataSourceRequest):
    """切换数据源"""
    global current_data_source, tws_service
    
    source = request.source.lower()
    
    if source not in ("yahoo", "tws"):
        raise HTTPException(status_code=400, detail="数据源必须是 'yahoo' 或 'tws'")
    
    tws_available = False
    tws_error = None
    
    if source == "tws":
        # 使用 TWSDataService 连接
        if tws_service is None:
            tws_service = TWSDataService(port=7497, client_id=20)
        
        if not tws_service.is_running:
            success = tws_service.start()
            if success:
                tws_available = True
                current_data_source = "tws"
                
                # 订阅 Watchlist 中的股票
                if watchlist_manager:
                    symbols = watchlist_manager.get_all()
                    tws_service.subscribe(symbols)
                
                logger.info("TWSDataService 已启动，切换数据源为 TWS")
            else:
                tws_error = tws_service.error or "无法连接到 TWS"
                current_data_source = "yahoo"
                logger.warning(f"TWS 连接失败: {tws_error}")
        else:
            tws_available = tws_service.is_connected
            if tws_available:
                current_data_source = "tws"
            else:
                tws_error = tws_service.error or "TWS 连接断开"
                current_data_source = "yahoo"
    else:
        # 切换回 Yahoo
        current_data_source = "yahoo"
        if tws_service is not None and tws_service.is_connected:
            tws_available = True
    
    return DataSourceStatus(
        current=current_data_source,
        tws_available=tws_available,
        tws_error=tws_error
    )


@app.post("/api/datasource/connect-tws")
async def connect_tws(port: int = 7497):
    """手动连接 TWS"""
    global tws_service, current_data_source
    
    # 停止旧服务
    if tws_service is not None:
        tws_service.stop()
    
    # 创建新服务
    tws_service = TWSDataService(port=port, client_id=20)
    success = tws_service.start()
    
    if success:
        current_data_source = "tws"
        
        # 订阅 Watchlist
        if watchlist_manager:
            symbols = watchlist_manager.get_all()
            tws_service.subscribe(symbols)
        
        return {
            "success": True,
            "message": f"成功连接到 TWS (端口 {port})",
            "data_source": "tws"
        }
    else:
        return {
            "success": False,
            "message": tws_service.error or "无法连接到 TWS，请确保 TWS 已启动并启用 API",
            "data_source": "yahoo"
        }


# -------------- Watchlist API --------------

@app.get("/api/watchlist", response_model=WatchlistResponse)
async def get_watchlist():
    """获取 Watchlist"""
    if watchlist_manager is None:
        raise HTTPException(status_code=500, detail="Watchlist manager not initialized")
    return WatchlistResponse(symbols=watchlist_manager.get_all())


@app.post("/api/watchlist", response_model=WatchlistResponse)
async def add_to_watchlist(request: SymbolRequest):
    """添加股票到 Watchlist"""
    if watchlist_manager is None:
        raise HTTPException(status_code=500, detail="Watchlist manager not initialized")
    
    symbol = request.symbol.upper().strip()
    if not symbol:
        raise HTTPException(status_code=400, detail="Symbol cannot be empty")
    
    if len(symbol) > 10:
        raise HTTPException(status_code=400, detail="Symbol too long")
    
    watchlist_manager.add(symbol)
    
    # 如果 TWS 服务运行中，订阅新股票
    if tws_service is not None and tws_service.is_connected:
        tws_service.subscribe([symbol])
    
    logger.info(f"添加到 Watchlist: {symbol}")
    
    return WatchlistResponse(symbols=watchlist_manager.get_all())


@app.delete("/api/watchlist/{symbol}", response_model=WatchlistResponse)
async def remove_from_watchlist(symbol: str):
    """从 Watchlist 移除股票"""
    if watchlist_manager is None:
        raise HTTPException(status_code=500, detail="Watchlist manager not initialized")
    
    symbol = symbol.upper().strip()
    watchlist_manager.remove(symbol)
    
    # 如果 TWS 服务运行中，取消订阅
    if tws_service is not None and tws_service.is_connected:
        tws_service.unsubscribe([symbol])
    
    logger.info(f"从 Watchlist 移除: {symbol}")
    
    return WatchlistResponse(symbols=watchlist_manager.get_all())


# -------------- Symbol Validation API --------------

@app.get("/api/validate/{symbol}", response_model=ValidateSymbolResponse)
async def validate_symbol(symbol: str):
    """验证股票代码是否有效"""
    symbol = symbol.upper().strip()
    
    # 基本格式验证
    if not symbol or len(symbol) > 10:
        return ValidateSymbolResponse(
            valid=False,
            symbol=symbol,
            error="股票代码格式无效"
        )
    
    # 只允许字母和数字
    if not symbol.replace(".", "").replace("-", "").isalnum():
        return ValidateSymbolResponse(
            valid=False,
            symbol=symbol,
            error="股票代码只能包含字母和数字"
        )
    
    # 使用 Yahoo Finance 验证
    try:
        stock_data = await fetch_yahoo_quote(symbol)
        if stock_data and stock_data.get("price"):
            return ValidateSymbolResponse(
                valid=True,
                symbol=symbol,
                name=stock_data.get("name"),
                price=stock_data.get("price")
            )
        else:
            return ValidateSymbolResponse(
                valid=False,
                symbol=symbol,
                error=f"未找到股票: {symbol}"
            )
    except Exception as e:
        logger.error(f"验证股票 {symbol} 失败: {e}")
        return ValidateSymbolResponse(
            valid=False,
            symbol=symbol,
            error=f"验证失败: {str(e)}"
        )


# -------------- Market Status API --------------

@app.get("/api/market/status", response_model=MarketStatusResponse)
async def get_market_status():
    """获取市场状态"""
    now = get_et_now()
    session = get_market_session(now)
    progress = get_trading_progress(now)
    allowed, reason = is_trading_allowed(now)
    
    return MarketStatusResponse(
        session=session.value,
        progress=progress,
        trading_allowed=allowed,
        trading_reason=reason,
        current_time=now.strftime("%Y-%m-%d %H:%M:%S ET"),
    )


# -------------- Stock Data API --------------

@app.get("/api/stocks/{symbol}", response_model=StockStatus)
async def get_stock_status(symbol: str):
    """获取单个股票状态（真实数据）"""
    symbol = symbol.upper().strip()
    
    # 获取真实数据
    status = await get_real_stock_status(symbol)
    return status


@app.get("/api/stocks", response_model=list[StockStatus])
async def get_all_stocks_status():
    """获取所有 Watchlist 股票状态"""
    if watchlist_manager is None:
        raise HTTPException(status_code=500, detail="Watchlist manager not initialized")
    
    symbols = watchlist_manager.get_all()
    
    # 并发获取所有股票数据
    tasks = [get_real_stock_status(symbol) for symbol in symbols]
    statuses = await asyncio.gather(*tasks)
    
    return list(statuses)


# -------------- Dashboard API --------------

@app.get("/api/dashboard", response_model=DashboardResponse)
async def get_dashboard():
    """获取仪表盘完整数据"""
    if watchlist_manager is None:
        raise HTTPException(status_code=500, detail="Watchlist manager not initialized")
    
    # 市场状态
    now = get_et_now()
    session = get_market_session(now)
    progress = get_trading_progress(now)
    allowed, reason = is_trading_allowed(now)
    
    market_status = MarketStatusResponse(
        session=session.value,
        progress=progress,
        trading_allowed=allowed,
        trading_reason=reason,
        current_time=now.strftime("%Y-%m-%d %H:%M:%S ET"),
    )
    
    # Watchlist
    symbols = watchlist_manager.get_all()
    
    # 根据数据源获取股票数据
    if current_data_source == "tws" and tws_service is not None and tws_service.is_connected:
        # 使用 TWS 实时数据
        tasks = [get_tws_stock_status(symbol) for symbol in symbols]
        actual_source = "tws"
    else:
        # 使用 Yahoo Finance 数据
        tasks = [get_yahoo_stock_status(symbol) for symbol in symbols]
        actual_source = "yahoo"
    
    stocks = await asyncio.gather(*tasks)
    
    return DashboardResponse(
        market_status=market_status,
        watchlist=symbols,
        stocks=list(stocks),
        data_source=actual_source,
    )


# ============== Helper Functions ==============

# Yahoo Finance API 需要的 Headers（避免 429 速率限制）
YAHOO_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}


async def fetch_yahoo_quote(symbol: str) -> dict[str, Any] | None:
    """
    从 Yahoo Finance 获取股票实时报价
    
    使用 Yahoo Finance API (query1.finance.yahoo.com)
    需要添加 User-Agent 头避免 429 错误
    """
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {
        "interval": "1m",
        "range": "1d",
        "includePrePost": "false",
    }
    
    try:
        async with httpx.AsyncClient(timeout=15.0, headers=YAHOO_HEADERS) as client:
            response = await client.get(url, params=params)
            
            if response.status_code == 404:
                logger.warning(f"Yahoo Finance: 股票 {symbol} 不存在")
                return None
            
            if response.status_code != 200:
                logger.warning(f"Yahoo Finance 返回 {response.status_code} for {symbol}")
                return None
            
            data = response.json()
            chart = data.get("chart", {})
            
            # 检查 API 错误
            if chart.get("error"):
                logger.warning(f"Yahoo Finance API 错误: {chart['error']}")
                return None
            
            result = chart.get("result", [])
            
            if not result:
                return None
            
            quote = result[0]
            meta = quote.get("meta", {})
            
            # 获取价格数据
            price = meta.get("regularMarketPrice")
            prev_close = meta.get("previousClose") or meta.get("chartPreviousClose")
            
            # 获取日内 OHLCV - 使用 meta 中的全天数据
            indicators = quote.get("indicators", {})
            quotes = indicators.get("quote", [{}])[0]
            
            # 全天高低点从 meta 获取（更准确）
            day_high = meta.get("regularMarketDayHigh")
            day_low = meta.get("regularMarketDayLow")
            day_open = meta.get("regularMarketOpen")
            
            # 如果 meta 中没有开盘价，从第一个1分钟K线获取
            if day_open is None and quotes.get("open"):
                opens = quotes.get("open", [])
                # 找第一个非 None 的开盘价
                for o in opens:
                    if o is not None:
                        day_open = o
                        break
            
            # 计算总成交量（所有1分钟K线成交量之和）
            volumes = quotes.get("volume", [])
            total_volume = sum(v for v in volumes if v is not None) if volumes else None
            
            return {
                "symbol": symbol,
                "name": meta.get("shortName") or meta.get("longName") or symbol,
                "price": price,
                "prev_close": prev_close,
                "open": day_open,
                "high": day_high,
                "low": day_low,
                "volume": total_volume,
                "currency": meta.get("currency", "USD"),
                "exchange": meta.get("exchangeName"),
            }
            
    except Exception as e:
        logger.error(f"获取 {symbol} 报价失败: {e}")
        return None


async def fetch_yahoo_ma20(symbol: str) -> float | None:
    """
    从 Yahoo Finance 获取 20 日均线
    
    使用日线数据计算 MA20
    """
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {
        "interval": "1d",
        "range": "1mo",  # 获取1个月数据计算 MA20
    }
    
    try:
        async with httpx.AsyncClient(timeout=15.0, headers=YAHOO_HEADERS) as client:
            response = await client.get(url, params=params)
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            result = data.get("chart", {}).get("result", [])
            
            if not result:
                return None
            
            quotes = result[0].get("indicators", {}).get("quote", [{}])[0]
            closes = quotes.get("close", [])
            
            # 过滤 None 值
            valid_closes = [c for c in closes if c is not None]
            
            if len(valid_closes) >= 20:
                ma20 = sum(valid_closes[-20:]) / 20
                return round(ma20, 2)
            elif len(valid_closes) > 0:
                # 不足20天，使用可用数据
                ma20 = sum(valid_closes) / len(valid_closes)
                return round(ma20, 2)
            
            return None
            
    except Exception as e:
        logger.error(f"获取 {symbol} MA20 失败: {e}")
        return None


async def fetch_yahoo_sparkline(symbol: str, points: int = 30) -> list[float]:
    """
    从 Yahoo Finance 获取价格序列用于 Sparkline
    
    - 交易日：获取今日 5 分钟 K 线
    - 休市日（周末/节假日）：获取上一个交易日的数据
    
    Args:
        symbol: 股票代码
        points: 返回的数据点数 (默认 30 个点)
    
    Returns:
        简化后的价格序列
    """
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    
    # 先尝试获取 1d 数据
    params = {
        "interval": "5m",
        "range": "1d",
        "includePrePost": "false",
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0, headers=YAHOO_HEADERS) as client:
            response = await client.get(url, params=params)
            
            if response.status_code != 200:
                return []
            
            data = response.json()
            result = data.get("chart", {}).get("result", [])
            
            if not result:
                return []
            
            quotes = result[0].get("indicators", {}).get("quote", [{}])[0]
            closes = quotes.get("close", [])
            timestamps = result[0].get("timestamp", [])
            
            # 过滤 None 值
            valid_closes = [c for c in closes if c is not None]
            
            # 如果数据点太少（休市或盘前），获取更多天数的数据
            if len(valid_closes) < 5:
                # 获取最近 5 天的数据，提取最后一个完整交易日
                params["range"] = "5d"
                response = await client.get(url, params=params)
                
                if response.status_code != 200:
                    return []
                
                data = response.json()
                result = data.get("chart", {}).get("result", [])
                
                if not result:
                    return []
                
                quotes = result[0].get("indicators", {}).get("quote", [{}])[0]
                closes = quotes.get("close", [])
                timestamps = result[0].get("timestamp", [])
                
                if not timestamps or not closes:
                    return []
                
                # 按日期分组，找到最后一个完整交易日
                from datetime import datetime
                
                day_data: dict[str, list[float]] = {}
                for ts, close in zip(timestamps, closes):
                    if ts and close is not None:
                        # 转换为美东时间的日期
                        dt = datetime.fromtimestamp(ts)
                        day_key = dt.strftime("%Y-%m-%d")
                        if day_key not in day_data:
                            day_data[day_key] = []
                        day_data[day_key].append(close)
                
                # 取数据点最多的那一天（通常是最后一个完整交易日）
                if day_data:
                    # 按日期排序，取最后一天有足够数据的
                    sorted_days = sorted(day_data.keys(), reverse=True)
                    for day in sorted_days:
                        if len(day_data[day]) >= 5:  # 至少要有5个数据点
                            valid_closes = day_data[day]
                            break
                    else:
                        # 如果没有足够数据，取最后一天的所有数据
                        valid_closes = day_data[sorted_days[0]] if sorted_days else []
            
            if not valid_closes:
                return []
            
            # 简化数据点：如果数据过多，采样到指定点数
            if len(valid_closes) > points:
                step = len(valid_closes) / points
                sampled = [valid_closes[int(i * step)] for i in range(points)]
                return [round(p, 2) for p in sampled]
            
            return [round(p, 2) for p in valid_closes]
            
    except Exception as e:
        logger.error(f"获取 {symbol} Sparkline 失败: {e}")
        return []


async def get_yahoo_stock_status(symbol: str) -> StockStatus:
    """获取股票状态（使用 Yahoo Finance + 新闻检测）"""
    
    # 并行获取报价、新闻、MA20 和 Sparkline
    quote_task = fetch_yahoo_quote(symbol)
    ma20_task = fetch_yahoo_ma20(symbol)
    sparkline_task = fetch_yahoo_sparkline(symbol)
    news_task = news_detector.detect(symbol) if news_detector else None
    
    quote = await quote_task
    ma20 = await ma20_task
    sparkline = await sparkline_task
    news_result = await news_task if news_task else None
    
    # 新闻事件信息
    news_score = news_result.event_score if news_result else 0.0
    news_keywords = news_result.detected_keywords if news_result else []
    
    if quote and quote.get("price"):
        price = quote["price"]
        prev_close = quote.get("prev_close") or price
        open_price = quote.get("open") or price
        high = quote.get("high") or price
        low = quote.get("low") or price
        
        # 简单计算 VWAP (使用 typical price 近似)
        vwap = (high + low + price) / 3 if high and low else price
        
        # OR 使用开盘价附近范围
        or_range = abs(high - low) * 0.3 if high != low else price * 0.01
        or15_high = open_price + or_range
        or15_low = open_price - or_range
        
        vwap_diff_pct = (price - vwap) / vwap * 100 if vwap else 0
        
        # 计算缺口
        gap_pct = (open_price - prev_close) / prev_close if prev_close else 0
        
        # 基于价格走势和新闻判断日类型
        day_change = (price - prev_close) / prev_close if prev_close else 0
        
        # 事件日判断 (新闻得分高 或 大缺口)
        if news_score >= 0.6 or abs(gap_pct) >= 0.015:
            regime = "event"
            reasons = []
            if news_keywords:
                reasons.append(f"新闻事件: {', '.join(news_keywords[:3])}")
            if abs(gap_pct) >= 0.015:
                reasons.append(f"跳空缺口 {gap_pct:.2%}")
            if day_change > 0:
                reasons.append(f"日涨幅 {day_change:.2%}")
            else:
                reasons.append(f"日跌幅 {day_change:.2%}")
            confidence = max(news_score, 0.7)
        elif abs(day_change) > 0.02:  # 波动超过 2%
            if day_change > 0:
                regime = "trend_up"
                reasons = [
                    f"日涨幅 {day_change:.2%}",
                    f"当前价格 ${price:.2f} 高于开盘价 ${open_price:.2f}" if price > open_price else "价格在高位震荡",
                ]
            else:
                regime = "trend_down"
                reasons = [
                    f"日跌幅 {day_change:.2%}",
                    f"当前价格 ${price:.2f} 低于开盘价 ${open_price:.2f}" if price < open_price else "价格在低位震荡",
                ]
            confidence = min(0.7 + abs(day_change) * 5, 0.95)
        else:
            regime = "range"
            reasons = [
                f"日波动 {day_change:.2%} 较小",
                "价格在开盘区间内震荡",
            ]
            confidence = 0.6
        
        return StockStatus(
            symbol=symbol,
            name=quote.get("name") or symbol,
            exchange=quote.get("exchange"),
            price=round(price, 2),
            prev_close=round(prev_close, 2) if prev_close else None,
            day_high=round(high, 2) if high else None,
            day_low=round(low, 2) if low else None,
            day_open=round(open_price, 2) if open_price else None,
            ma20=ma20,
            vwap=round(vwap, 2),
            vwap_diff_pct=round(vwap_diff_pct, 2),
            above_vwap=price > vwap,
            or5_high=round(or15_high, 2),
            or5_low=round(or15_low, 2),
            or15_high=round(or15_high, 2),
            or15_low=round(or15_low, 2),
            or15_complete=True,
            regime=regime,
            regime_confidence=round(confidence, 2),
            regime_reasons=reasons,
            news_event_score=round(news_score, 2),
            news_keywords=news_keywords,
            sparkline=sparkline,
            updated_at=get_et_now().strftime("%H:%M:%S"),
        )
    
    # 如果获取失败，返回错误状态
    return StockStatus(
        symbol=symbol,
        name=symbol,
        exchange=None,
        price=0.0,
        prev_close=None,
        day_high=None,
        day_low=None,
        day_open=None,
        ma20=None,
        vwap=0.0,
        vwap_diff_pct=0.0,
        above_vwap=False,
        or5_high=None,
        or5_low=None,
        or15_high=None,
        or15_low=None,
        or15_complete=False,
        regime="unknown",
        regime_confidence=0.0,
        regime_reasons=["无法获取股票数据"],
        updated_at=get_et_now().strftime("%H:%M:%S"),
    )


# ============== TWS 数据服务模式 ==============
# 说明：TWSDataService 在后台线程中运行 ib_insync，提供实时行情数据
# 当 TWS 连接可用时，从缓存读取实时数据；否则回退到 Yahoo Finance


async def get_tws_stock_status(symbol: str) -> StockStatus:
    """从 TWSDataService 获取实时股票状态"""
    global tws_service, news_detector
    
    if not tws_service or not tws_service.is_connected:
        # TWS 未连接，回退到 Yahoo
        return await get_yahoo_stock_status(symbol)
    
    # 从缓存获取 TWS 数据
    stock_data = tws_service.get_stock_data(symbol)
    
    if not stock_data or stock_data.price <= 0:
        # 没有 TWS 数据，回退到 Yahoo
        return await get_yahoo_stock_status(symbol)
    
    # 使用 TWS 的实时数据
    price = stock_data.price
    vwap = stock_data.vwap if stock_data.vwap > 0 else price
    high = stock_data.high if stock_data.high > 0 else price
    low = stock_data.low if stock_data.low > 0 else price
    open_price = stock_data.open if stock_data.open > 0 else price
    prev_close = stock_data.close if stock_data.close > 0 else price
    
    # 获取新闻事件信息和 MA20（TWS 不提供 MA20，从 Yahoo 获取）
    news_task = news_detector.detect(symbol) if news_detector else None
    ma20_task = fetch_yahoo_ma20(symbol)
    
    news_result = await news_task if news_task else None
    ma20 = await ma20_task
    
    news_score = news_result.event_score if news_result else 0.0
    news_keywords = news_result.detected_keywords if news_result else []
    
    vwap_diff_pct = (price - vwap) / vwap * 100 if vwap > 0 else 0
    
    # OR 计算 (使用当日高低范围的 30%)
    or_range = abs(high - low) * 0.3 if high > low else price * 0.01
    or15_high = open_price + or_range
    or15_low = open_price - or_range
    
    # 计算缺口
    gap_pct = (open_price - prev_close) / prev_close if prev_close > 0 else 0
    day_change = (price - prev_close) / prev_close if prev_close > 0 else 0
    
    # 事件日判断
    if news_score >= 0.6 or abs(gap_pct) >= 0.015:
        regime = "event"
        reasons = []
        if news_keywords:
            reasons.append(f"新闻事件: {', '.join(news_keywords[:3])}")
        if abs(gap_pct) >= 0.015:
            reasons.append(f"跳空缺口 {gap_pct:.2%}")
        reasons.append(f"日涨幅 {day_change:.2%}" if day_change > 0 else f"日跌幅 {day_change:.2%}")
        confidence = max(news_score, 0.7)
    elif abs(day_change) > 0.02:
        if day_change > 0:
            regime = "trend_up"
            reasons = [f"日涨幅 {day_change:.2%}", f"价格高于VWAP {vwap_diff_pct:.2f}%" if vwap_diff_pct > 0 else "价格在高位震荡"]
        else:
            regime = "trend_down"
            reasons = [f"日跌幅 {day_change:.2%}", f"价格低于VWAP {vwap_diff_pct:.2f}%" if vwap_diff_pct < 0 else "价格在低位震荡"]
        confidence = min(0.7 + abs(day_change) * 5, 0.95)
    else:
        regime = "range"
        reasons = [f"日波动 {day_change:.2%} 较小", "价格在区间内震荡"]
        confidence = 0.6
    
    return StockStatus(
        symbol=symbol,
        name=symbol,  # TWS 不提供公司名称
        exchange="SMART",
        price=round(price, 2),
        prev_close=round(prev_close, 2),
        day_high=round(high, 2),
        day_low=round(low, 2),
        day_open=round(open_price, 2),
        ma20=ma20,
        vwap=round(vwap, 2),
        vwap_diff_pct=round(vwap_diff_pct, 2),
        above_vwap=price > vwap,
        or5_high=round(or15_high, 2),
        or5_low=round(or15_low, 2),
        or15_high=round(or15_high, 2),
        or15_low=round(or15_low, 2),
        or15_complete=True,
        regime=regime,
        regime_confidence=round(confidence, 2),
        regime_reasons=reasons,
        news_event_score=round(news_score, 2),
        news_keywords=news_keywords,
        updated_at=get_et_now().strftime("%H:%M:%S"),
    )


async def get_real_stock_status(symbol: str) -> StockStatus:
    """获取股票状态 - 自动选择数据源
    
    优先级：
    1. TWS 连接可用且有数据 -> 使用 TWS 实时数据
    2. 否则 -> 使用 Yahoo Finance
    """
    global tws_service
    
    # 如果 TWS 服务可用且已连接，使用 TWS 数据
    if tws_service and tws_service.is_connected:
        return await get_tws_stock_status(symbol)
    
    # 默认使用 Yahoo Finance
    return await get_yahoo_stock_status(symbol)


def main():
    """运行 API 服务器"""
    import uvicorn
    uvicorn.run(
        "tbot.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )


if __name__ == "__main__":
    main()
