"""
测试后端 API 端点
"""

import asyncio
import httpx

API_BASE = "http://localhost:8000/api"


async def test_api():
    """测试 API 端点"""
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        
        # 1. 测试健康检查
        print("\n1. 测试健康检查")
        try:
            response = await client.get(f"{API_BASE}/health")
            print(f"   状态码: {response.status_code}")
            print(f"   响应: {response.json()}")
        except Exception as e:
            print(f"   ❌ 错误: {e}")
            print("   请确保后端服务已启动: uv run uvicorn tbot.api.main:app --reload")
            return
        
        # 2. 测试验证有效股票
        print("\n2. 测试验证有效股票 (AAPL)")
        response = await client.get(f"{API_BASE}/validate/AAPL")
        print(f"   状态码: {response.status_code}")
        data = response.json()
        print(f"   有效: {data.get('valid')}")
        print(f"   名称: {data.get('name')}")
        print(f"   价格: ${data.get('price')}")
        
        # 3. 测试验证无效股票
        print("\n3. 测试验证无效股票 (INVALID123)")
        response = await client.get(f"{API_BASE}/validate/INVALID123")
        print(f"   状态码: {response.status_code}")
        data = response.json()
        print(f"   有效: {data.get('valid')}")
        print(f"   错误: {data.get('error')}")
        
        # 4. 测试获取股票状态
        print("\n4. 测试获取股票状态 (AAPL)")
        response = await client.get(f"{API_BASE}/stocks/AAPL")
        print(f"   状态码: {response.status_code}")
        data = response.json()
        print(f"   价格: ${data.get('price')}")
        print(f"   VWAP: ${data.get('vwap')}")
        print(f"   日类型: {data.get('regime')}")
        
        # 5. 测试 Dashboard
        print("\n5. 测试 Dashboard")
        response = await client.get(f"{API_BASE}/dashboard")
        print(f"   状态码: {response.status_code}")
        data = response.json()
        print(f"   Watchlist: {data.get('watchlist')}")
        print(f"   股票数量: {len(data.get('stocks', []))}")
        
        print("\n✅ 测试完成!")


if __name__ == "__main__":
    asyncio.run(test_api())
