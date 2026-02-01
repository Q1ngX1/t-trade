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


# ============== 全局状态 ==============

watchlist_manager: WatchlistManager | None = None
stock_cache: dict[str, StockStatus] = {}
stock_price_cache: dict[str, dict[str, Any]] = {}  # 缓存真实股票数据
ibkr_client: Any = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global watchlist_manager
    
    settings = init_settings()
    watchlist_manager = WatchlistManager(settings.abs_data_dir / "watchlist.json")
    
    logger.info("FastAPI 应用启动")
    yield
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
    logger.info(f"添加到 Watchlist: {symbol}")
    
    return WatchlistResponse(symbols=watchlist_manager.get_all())


@app.delete("/api/watchlist/{symbol}", response_model=WatchlistResponse)
async def remove_from_watchlist(symbol: str):
    """从 Watchlist 移除股票"""
    if watchlist_manager is None:
        raise HTTPException(status_code=500, detail="Watchlist manager not initialized")
    
    symbol = symbol.upper().strip()
    watchlist_manager.remove(symbol)
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
    
    # 股票状态 - 并发获取真实数据
    tasks = [get_real_stock_status(symbol) for symbol in symbols]
    stocks = await asyncio.gather(*tasks)
    
    return DashboardResponse(
        market_status=market_status,
        watchlist=symbols,
        stocks=list(stocks),
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
            
            # 获取日内 OHLCV
            indicators = quote.get("indicators", {})
            quotes = indicators.get("quote", [{}])[0]
            
            return {
                "symbol": symbol,
                "name": meta.get("shortName") or meta.get("longName") or symbol,
                "price": price,
                "prev_close": prev_close,
                "open": quotes.get("open", [None])[-1] if quotes.get("open") else None,
                "high": quotes.get("high", [None])[-1] if quotes.get("high") else None,
                "low": quotes.get("low", [None])[-1] if quotes.get("low") else None,
                "volume": quotes.get("volume", [None])[-1] if quotes.get("volume") else None,
                "currency": meta.get("currency", "USD"),
                "exchange": meta.get("exchangeName"),
            }
            
    except Exception as e:
        logger.error(f"获取 {symbol} 报价失败: {e}")
        return None


async def get_real_stock_status(symbol: str) -> StockStatus:
    """获取真实股票状态（使用 Yahoo Finance）"""
    
    # 尝试获取真实数据
    quote = await fetch_yahoo_quote(symbol)
    
    if quote and quote.get("price"):
        price = quote["price"]
        prev_close = quote.get("prev_close") or price
        open_price = quote.get("open") or price
        high = quote.get("high") or price
        low = quote.get("low") or price
        
        # 简单计算 VWAP (使用 typical price 近似)
        vwap = (high + low + price) / 3 if high and low else price
        
        # OR 使用开盘价附近
        or_range = abs(high - low) * 0.3 if high and low else price * 0.01
        or15_high = open_price + or_range
        or15_low = open_price - or_range
        
        vwap_diff_pct = (price - vwap) / vwap * 100 if vwap else 0
        
        # 基于价格走势判断日类型
        day_change = (price - prev_close) / prev_close if prev_close else 0
        
        if abs(day_change) > 0.02:  # 波动超过 2%
            if day_change > 0:
                regime = "trend_up"
                reasons = [
                    f"日涨幅 {day_change:.2%}",
                    f"当前价格 ${price:.2f} 高于开盘价 ${open_price:.2f}" if price > open_price else f"价格在高位震荡",
                ]
            else:
                regime = "trend_down"
                reasons = [
                    f"日跌幅 {day_change:.2%}",
                    f"当前价格 ${price:.2f} 低于开盘价 ${open_price:.2f}" if price < open_price else f"价格在低位震荡",
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
            updated_at=get_et_now().strftime("%H:%M:%S"),
        )
    
    # 如果获取失败，返回错误状态
    return StockStatus(
        symbol=symbol,
        name=symbol,
        exchange=None,
        price=0.0,
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
