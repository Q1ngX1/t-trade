"""手动测试 Yahoo API 函数"""
import asyncio
import sys
sys.path.insert(0, 'src')

from tbot.api.main import fetch_yahoo_quote, fetch_yahoo_ma20

async def main():
    print("=== 测试 Yahoo Finance API ===\n")
    
    symbol = "AAPL"
    
    # 测试 fetch_yahoo_quote
    print(f"调用 fetch_yahoo_quote({symbol})...")
    quote = await fetch_yahoo_quote(symbol)
    
    if quote:
        print(f"  price: {quote.get('price')}")
        print(f"  prev_close: {quote.get('prev_close')}")
        print(f"  open: {quote.get('open')}")
        print(f"  high: {quote.get('high')}")
        print(f"  low: {quote.get('low')}")
        print(f"  exchange: {quote.get('exchange')}")
    else:
        print("  返回 None")
    print()
    
    # 测试 fetch_yahoo_ma20
    print(f"调用 fetch_yahoo_ma20({symbol})...")
    ma20 = await fetch_yahoo_ma20(symbol)
    print(f"  MA20: {ma20}")
    print()
    
    # 计算 VWAP
    if quote:
        high = quote.get('high') or quote.get('price')
        low = quote.get('low') or quote.get('price')
        price = quote.get('price')
        vwap = (high + low + price) / 3
        vwap_diff = (price - vwap) / vwap * 100
        print(f"计算的 VWAP: {vwap:.2f}")
        print(f"VWAP 差异: {vwap_diff:.2f}%")

if __name__ == "__main__":
    asyncio.run(main())
