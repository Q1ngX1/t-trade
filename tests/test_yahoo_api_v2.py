"""
Yahoo Finance API 测试脚本 v2

添加 User-Agent 头和重试逻辑
"""

import asyncio
import httpx


# 模拟浏览器的 User-Agent
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}


async def test_yahoo_v8_with_headers(symbol: str) -> dict:
    """测试 Yahoo Finance v8 API (带 headers)"""
    print(f"\n{'='*50}")
    print(f"测试 v8 API: {symbol}")
    print('='*50)
    
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {
        "interval": "1d",
        "range": "1d",
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0, headers=HEADERS) as client:
            response = await client.get(url, params=params)
            
            print(f"状态码: {response.status_code}")
            
            if response.status_code == 429:
                print(f"❌ 速率限制 (429)")
                return {"success": False, "error": "Rate limited"}
            
            if response.status_code != 200:
                print(f"❌ 请求失败: {response.text[:200]}")
                return {"success": False, "error": f"HTTP {response.status_code}"}
            
            data = response.json()
            chart = data.get("chart", {})
            
            if chart.get("error"):
                print(f"❌ API 错误: {chart['error']}")
                return {"success": False, "error": chart["error"]}
            
            result = chart.get("result", [])
            if not result:
                print(f"❌ 无效股票代码")
                return {"success": False, "error": "Invalid symbol"}
            
            meta = result[0].get("meta", {})
            print(f"✅ 成功! 价格: ${meta.get('regularMarketPrice')}")
            
            return {
                "success": True,
                "symbol": meta.get("symbol"),
                "name": meta.get("shortName"),
                "price": meta.get("regularMarketPrice"),
            }
            
    except Exception as e:
        print(f"❌ 异常: {e}")
        return {"success": False, "error": str(e)}


async def test_yahoo_v7_with_headers(symbol: str) -> dict:
    """测试 Yahoo Finance v7 API (带 headers)"""
    print(f"\n{'='*50}")
    print(f"测试 v7 API: {symbol}")
    print('='*50)
    
    url = "https://query1.finance.yahoo.com/v7/finance/quote"
    params = {"symbols": symbol}
    
    try:
        async with httpx.AsyncClient(timeout=10.0, headers=HEADERS) as client:
            response = await client.get(url, params=params)
            
            print(f"状态码: {response.status_code}")
            
            if response.status_code == 429:
                print(f"❌ 速率限制 (429)")
                return {"success": False, "error": "Rate limited"}
            
            if response.status_code != 200:
                print(f"❌ 请求失败: {response.text[:200]}")
                return {"success": False, "error": f"HTTP {response.status_code}"}
            
            data = response.json()
            quote_response = data.get("quoteResponse", {})
            result = quote_response.get("result", [])
            
            if not result:
                print(f"❌ 无效股票代码")
                return {"success": False, "error": "Invalid symbol"}
            
            quote = result[0]
            print(f"✅ 成功! 价格: ${quote.get('regularMarketPrice')}")
            
            return {
                "success": True,
                "symbol": quote.get("symbol"),
                "name": quote.get("shortName"),
                "price": quote.get("regularMarketPrice"),
            }
            
    except Exception as e:
        print(f"❌ 异常: {e}")
        return {"success": False, "error": str(e)}


async def test_yfinance_download(symbol: str) -> dict:
    """测试 Yahoo Finance 下载 API"""
    print(f"\n{'='*50}")
    print(f"测试下载 API: {symbol}")
    print('='*50)
    
    # 这个 API 更稳定
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {
        "interval": "1m",
        "range": "1d",
        "includePrePost": "false",
    }
    
    try:
        async with httpx.AsyncClient(timeout=15.0, headers=HEADERS, follow_redirects=True) as client:
            response = await client.get(url, params=params)
            
            print(f"状态码: {response.status_code}")
            
            if response.status_code == 429:
                print(f"❌ 速率限制 (429)")
                return {"success": False, "error": "Rate limited"}
            
            if response.status_code != 200:
                print(f"❌ 请求失败")
                return {"success": False, "error": f"HTTP {response.status_code}"}
            
            data = response.json()
            chart = data.get("chart", {})
            
            if chart.get("error"):
                error_msg = chart["error"].get("description", "Unknown error")
                print(f"❌ API 错误: {error_msg}")
                return {"success": False, "error": error_msg}
            
            result = chart.get("result")
            if not result:
                print(f"❌ 无效股票代码")
                return {"success": False, "error": "Invalid symbol"}
            
            meta = result[0].get("meta", {})
            price = meta.get("regularMarketPrice")
            
            print(f"✅ 成功!")
            print(f"   代码: {meta.get('symbol')}")
            print(f"   价格: ${price}")
            print(f"   名称: {meta.get('shortName')}")
            
            return {
                "success": True,
                "symbol": meta.get("symbol"),
                "name": meta.get("shortName"),
                "price": price,
            }
            
    except Exception as e:
        print(f"❌ 异常: {e}")
        return {"success": False, "error": str(e)}


async def test_finnhub_free_api(symbol: str) -> dict:
    """测试 Finnhub 免费 API（作为备用）"""
    print(f"\n{'='*50}")
    print(f"测试 Finnhub API: {symbol}")
    print('='*50)
    
    # Finnhub 免费 API（需要注册获取 API key，这里用 demo）
    url = f"https://finnhub.io/api/v1/quote"
    params = {
        "symbol": symbol,
        "token": "demo",  # demo token 有限制
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
            
            print(f"状态码: {response.status_code}")
            
            if response.status_code != 200:
                print(f"❌ 请求失败")
                return {"success": False, "error": f"HTTP {response.status_code}"}
            
            data = response.json()
            
            # c = current price, pc = previous close
            if data.get("c") and data.get("c") > 0:
                print(f"✅ 成功! 价格: ${data.get('c')}")
                return {
                    "success": True,
                    "symbol": symbol,
                    "price": data.get("c"),
                    "prev_close": data.get("pc"),
                }
            else:
                print(f"❌ 无效股票或无数据")
                return {"success": False, "error": "No data"}
            
    except Exception as e:
        print(f"❌ 异常: {e}")
        return {"success": False, "error": str(e)}


async def main():
    """主测试"""
    print("=" * 60)
    print("Yahoo Finance API 测试 v2 (带 Headers)")
    print("=" * 60)
    
    symbols = ["AAPL", "MSFT", "INVALID123"]
    
    # 测试方法 1: v8 API with headers
    print("\n\n>>> 方法 1: v8 API with headers")
    await asyncio.sleep(1)
    for symbol in symbols:
        await test_yahoo_v8_with_headers(symbol)
        await asyncio.sleep(0.5)  # 添加延迟避免速率限制
    
    # 测试方法 2: v7 API with headers  
    print("\n\n>>> 方法 2: v7 API with headers")
    await asyncio.sleep(1)
    for symbol in symbols:
        await test_yahoo_v7_with_headers(symbol)
        await asyncio.sleep(0.5)
    
    # 测试方法 3: 下载 API
    print("\n\n>>> 方法 3: 下载 API (1m interval)")
    await asyncio.sleep(1)
    for symbol in symbols:
        await test_yfinance_download(symbol)
        await asyncio.sleep(0.5)
    
    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
