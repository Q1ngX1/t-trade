"""
Yahoo Finance API 测试脚本

测试股票代码验证和报价获取功能
"""

import asyncio
import httpx


async def test_yahoo_finance_api(symbol: str) -> dict:
    """测试 Yahoo Finance API"""
    print(f"\n{'='*50}")
    print(f"测试股票: {symbol}")
    print('='*50)
    
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {
        "interval": "1d",
        "range": "1d",
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            print(f"请求 URL: {url}")
            print(f"参数: {params}")
            
            response = await client.get(url, params=params)
            
            print(f"状态码: {response.status_code}")
            
            if response.status_code != 200:
                print(f"❌ 请求失败: {response.text[:500]}")
                return {"success": False, "error": f"HTTP {response.status_code}"}
            
            data = response.json()
            
            # 检查错误
            if "chart" not in data:
                print(f"❌ 响应中没有 chart 字段")
                print(f"响应: {data}")
                return {"success": False, "error": "No chart in response"}
            
            chart = data["chart"]
            
            if chart.get("error"):
                error = chart["error"]
                print(f"❌ API 返回错误: {error}")
                return {"success": False, "error": error}
            
            result = chart.get("result", [])
            
            if not result:
                print(f"❌ 没有结果数据")
                return {"success": False, "error": "No result data"}
            
            quote = result[0]
            meta = quote.get("meta", {})
            
            # 打印元数据
            print(f"\n✅ 获取成功!")
            print(f"股票代码: {meta.get('symbol')}")
            print(f"名称: {meta.get('shortName') or meta.get('longName')}")
            print(f"交易所: {meta.get('exchangeName')}")
            print(f"货币: {meta.get('currency')}")
            print(f"当前价格: {meta.get('regularMarketPrice')}")
            print(f"前收盘价: {meta.get('previousClose') or meta.get('chartPreviousClose')}")
            print(f"市场状态: {meta.get('marketState')}")
            
            # 获取日内数据
            indicators = quote.get("indicators", {})
            quotes = indicators.get("quote", [{}])[0]
            
            if quotes:
                print(f"\n日内数据:")
                print(f"  开盘: {quotes.get('open', [])[-1] if quotes.get('open') else 'N/A'}")
                print(f"  最高: {quotes.get('high', [])[-1] if quotes.get('high') else 'N/A'}")
                print(f"  最低: {quotes.get('low', [])[-1] if quotes.get('low') else 'N/A'}")
                print(f"  收盘: {quotes.get('close', [])[-1] if quotes.get('close') else 'N/A'}")
                print(f"  成交量: {quotes.get('volume', [])[-1] if quotes.get('volume') else 'N/A'}")
            
            return {
                "success": True,
                "symbol": meta.get("symbol"),
                "name": meta.get("shortName") or meta.get("longName"),
                "price": meta.get("regularMarketPrice"),
                "prev_close": meta.get("previousClose") or meta.get("chartPreviousClose"),
            }
            
    except httpx.TimeoutException:
        print(f"❌ 请求超时")
        return {"success": False, "error": "Timeout"}
    except Exception as e:
        print(f"❌ 异常: {type(e).__name__}: {e}")
        return {"success": False, "error": str(e)}


async def test_alternative_api(symbol: str) -> dict:
    """测试备用 API (v7)"""
    print(f"\n{'='*50}")
    print(f"测试备用 API (v7): {symbol}")
    print('='*50)
    
    url = f"https://query1.finance.yahoo.com/v7/finance/quote"
    params = {
        "symbols": symbol,
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            print(f"请求 URL: {url}")
            print(f"参数: {params}")
            
            response = await client.get(url, params=params)
            
            print(f"状态码: {response.status_code}")
            
            if response.status_code != 200:
                print(f"❌ 请求失败: {response.text[:500]}")
                return {"success": False, "error": f"HTTP {response.status_code}"}
            
            data = response.json()
            
            quote_response = data.get("quoteResponse", {})
            error = quote_response.get("error")
            
            if error:
                print(f"❌ API 返回错误: {error}")
                return {"success": False, "error": error}
            
            result = quote_response.get("result", [])
            
            if not result:
                print(f"❌ 没有结果数据 - 股票代码无效")
                return {"success": False, "error": "Invalid symbol"}
            
            quote = result[0]
            
            print(f"\n✅ 获取成功!")
            print(f"股票代码: {quote.get('symbol')}")
            print(f"名称: {quote.get('shortName') or quote.get('longName')}")
            print(f"交易所: {quote.get('exchange')}")
            print(f"货币: {quote.get('currency')}")
            print(f"当前价格: {quote.get('regularMarketPrice')}")
            print(f"前收盘价: {quote.get('regularMarketPreviousClose')}")
            print(f"市场状态: {quote.get('marketState')}")
            print(f"开盘价: {quote.get('regularMarketOpen')}")
            print(f"最高价: {quote.get('regularMarketDayHigh')}")
            print(f"最低价: {quote.get('regularMarketDayLow')}")
            print(f"成交量: {quote.get('regularMarketVolume')}")
            
            return {
                "success": True,
                "symbol": quote.get("symbol"),
                "name": quote.get("shortName") or quote.get("longName"),
                "price": quote.get("regularMarketPrice"),
                "prev_close": quote.get("regularMarketPreviousClose"),
                "open": quote.get("regularMarketOpen"),
                "high": quote.get("regularMarketDayHigh"),
                "low": quote.get("regularMarketDayLow"),
                "volume": quote.get("regularMarketVolume"),
            }
            
    except httpx.TimeoutException:
        print(f"❌ 请求超时")
        return {"success": False, "error": "Timeout"}
    except Exception as e:
        print(f"❌ 异常: {type(e).__name__}: {e}")
        return {"success": False, "error": str(e)}


async def main():
    """主测试函数"""
    print("Yahoo Finance API 测试")
    print("=" * 60)
    
    # 测试有效股票
    valid_symbols = ["AAPL", "MSFT", "GOOGL", "QQQM", "TSLA"]
    
    # 测试无效股票
    invalid_symbols = ["INVALID123", "XXXYYY", "12345"]
    
    print("\n" + "=" * 60)
    print("测试 v8/finance/chart API")
    print("=" * 60)
    
    for symbol in valid_symbols[:2]:
        await test_yahoo_finance_api(symbol)
    
    for symbol in invalid_symbols[:1]:
        await test_yahoo_finance_api(symbol)
    
    print("\n" + "=" * 60)
    print("测试 v7/finance/quote API (备用)")
    print("=" * 60)
    
    for symbol in valid_symbols[:2]:
        await test_alternative_api(symbol)
    
    for symbol in invalid_symbols[:1]:
        await test_alternative_api(symbol)
    
    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
