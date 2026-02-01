"""
T-Trade 服务模块

提供后台数据服务：
- TWSDataService: TWS 实时数据服务
- NewsEventDetector: 新闻事件检测服务
"""

from tbot.services.tws_data_service import (
    TWSDataService,
    get_tws_service,
    init_tws_service,
    stop_tws_service,
)
from tbot.services.news_event_detector import (
    NewsEventDetector,
    get_news_detector,
)

__all__ = [
    "TWSDataService",
    "get_tws_service",
    "init_tws_service",
    "stop_tws_service",
    "NewsEventDetector",
    "get_news_detector",
]
