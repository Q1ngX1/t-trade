"""
新闻事件检测器

从 Yahoo Finance 获取新闻，分析关键词，
检测可能影响股价的重大事件。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import httpx
from loguru import logger


# 事件关键词及权重
EVENT_KEYWORDS: dict[str, tuple[float, str]] = {
    # 财报相关 (高影响)
    "earnings": (0.8, "财报"),
    "quarterly results": (0.8, "季报"),
    "beat": (0.6, "超预期"),
    "miss": (0.6, "不及预期"),
    "guidance": (0.7, "业绩指引"),
    "revenue": (0.5, "营收"),
    "profit": (0.5, "利润"),
    "EPS": (0.6, "每股收益"),
    
    # 重大事件 (高影响)
    "FDA": (0.9, "FDA"),
    "approval": (0.8, "获批"),
    "approved": (0.8, "获批"),
    "merger": (0.9, "合并"),
    "acquisition": (0.9, "收购"),
    "acquire": (0.8, "收购"),
    "buyout": (0.9, "收购"),
    "takeover": (0.9, "收购"),
    "split": (0.7, "拆股"),
    "dividend": (0.5, "分红"),
    "buyback": (0.6, "回购"),
    
    # 分析师/机构 (中影响)
    "upgrade": (0.6, "上调评级"),
    "downgrade": (0.6, "下调评级"),
    "price target": (0.5, "目标价"),
    "rating": (0.4, "评级"),
    "initiate": (0.4, "首次评级"),
    
    # 负面事件 (高影响)
    "lawsuit": (0.7, "诉讼"),
    "sue": (0.7, "起诉"),
    "investigation": (0.7, "调查"),
    "probe": (0.7, "调查"),
    "recall": (0.8, "召回"),
    "fraud": (0.9, "欺诈"),
    "bankruptcy": (0.9, "破产"),
    "default": (0.8, "违约"),
    "layoff": (0.6, "裁员"),
    
    # 管理层变动 (中影响)
    "CEO": (0.6, "CEO"),
    "CFO": (0.5, "CFO"),
    "resign": (0.6, "辞职"),
    "appoint": (0.5, "任命"),
    "executive": (0.4, "高管"),
    
    # 产品/业务 (中影响)
    "launch": (0.5, "发布"),
    "partnership": (0.5, "合作"),
    "contract": (0.5, "合同"),
    "deal": (0.5, "交易"),
}


@dataclass
class NewsItem:
    """新闻条目"""
    title: str
    publisher: str
    link: str
    publish_time: datetime
    thumbnail: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "publisher": self.publisher,
            "link": self.link,
            "publish_time": self.publish_time.isoformat(),
        }


@dataclass
class NewsEventResult:
    """新闻事件检测结果"""
    symbol: str
    event_score: float = 0.0
    is_event_day: bool = False
    detected_keywords: list[str] = field(default_factory=list)
    headlines: list[str] = field(default_factory=list)
    news_items: list[NewsItem] = field(default_factory=list)
    error: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "event_score": self.event_score,
            "is_event_day": self.is_event_day,
            "detected_keywords": self.detected_keywords,
            "headlines": self.headlines[:5],  # 最多5条
            "error": self.error,
        }


class NewsEventDetector:
    """
    新闻事件检测器
    
    从 Yahoo Finance 获取新闻，分析关键词，
    返回事件评分和检测到的关键词。
    
    Usage:
        detector = NewsEventDetector()
        result = await detector.detect(symbol)
        
        if result.is_event_day:
            print(f"检测到事件: {result.detected_keywords}")
    """
    
    def __init__(
        self,
        event_threshold: float = 0.6,
        lookback_hours: int = 24,
    ):
        self.event_threshold = event_threshold
        self.lookback_hours = lookback_hours
        
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        }
    
    async def detect(self, symbol: str) -> NewsEventResult:
        """
        检测股票是否有重大新闻事件
        
        Args:
            symbol: 股票代码
            
        Returns:
            NewsEventResult
        """
        result = NewsEventResult(symbol=symbol)
        
        try:
            # 获取新闻
            news_items = await self._fetch_yahoo_news(symbol)
            result.news_items = news_items
            result.headlines = [n.title for n in news_items]
            
            # 分析关键词
            score, keywords = self._analyze_headlines(result.headlines)
            result.event_score = score
            result.detected_keywords = keywords
            result.is_event_day = score >= self.event_threshold
            
            if result.is_event_day:
                logger.info(f"{symbol} 检测到事件日: {keywords} (得分: {score:.2f})")
            
        except Exception as e:
            result.error = str(e)
            logger.error(f"检测 {symbol} 新闻事件失败: {e}")
        
        return result
    
    async def detect_batch(self, symbols: list[str]) -> dict[str, NewsEventResult]:
        """批量检测多个股票"""
        import asyncio
        
        tasks = [self.detect(symbol) for symbol in symbols]
        results = await asyncio.gather(*tasks)
        
        return {r.symbol: r for r in results}
    
    async def _fetch_yahoo_news(self, symbol: str) -> list[NewsItem]:
        """从 Yahoo Finance 获取新闻"""
        url = f"https://query2.finance.yahoo.com/v1/finance/search"
        params = {
            "q": symbol,
            "newsCount": 20,
            "quotesCount": 0,
            "enableFuzzyQuery": False,
            "quotesQueryId": "tss_match_phrase_query",
        }
        
        async with httpx.AsyncClient(timeout=10.0, headers=self.headers) as client:
            response = await client.get(url, params=params)
            
            if response.status_code != 200:
                logger.warning(f"Yahoo News API 返回 {response.status_code}")
                return []
            
            data = response.json()
            news_list = data.get("news", [])
            
            # 过滤时间
            cutoff_time = datetime.now() - timedelta(hours=self.lookback_hours)
            
            items = []
            for news in news_list:
                publish_time = datetime.fromtimestamp(
                    news.get("providerPublishTime", 0)
                )
                
                # 只保留最近的新闻
                if publish_time < cutoff_time:
                    continue
                
                items.append(NewsItem(
                    title=news.get("title", ""),
                    publisher=news.get("publisher", ""),
                    link=news.get("link", ""),
                    publish_time=publish_time,
                    thumbnail=news.get("thumbnail", {}).get("resolutions", [{}])[0].get("url", ""),
                ))
            
            return items
    
    def _analyze_headlines(self, headlines: list[str]) -> tuple[float, list[str]]:
        """
        分析标题中的关键词
        
        Returns:
            (最高得分, 检测到的关键词列表)
        """
        max_score = 0.0
        detected: list[str] = []
        seen_keywords: set[str] = set()
        
        for headline in headlines:
            headline_lower = headline.lower()
            
            for keyword, (weight, label) in EVENT_KEYWORDS.items():
                # 避免重复
                if keyword in seen_keywords:
                    continue
                
                # 关键词匹配 (使用单词边界)
                pattern = rf"\b{re.escape(keyword)}\b"
                if re.search(pattern, headline_lower, re.IGNORECASE):
                    max_score = max(max_score, weight)
                    detected.append(label)
                    seen_keywords.add(keyword)
        
        # 多个关键词时提高得分
        if len(detected) >= 3:
            max_score = min(max_score + 0.1, 1.0)
        elif len(detected) >= 2:
            max_score = min(max_score + 0.05, 1.0)
        
        return round(max_score, 2), detected


# 全局实例
_news_detector: NewsEventDetector | None = None


def get_news_detector() -> NewsEventDetector:
    """获取全局新闻检测器实例"""
    global _news_detector
    
    if _news_detector is None:
        _news_detector = NewsEventDetector()
    
    return _news_detector
