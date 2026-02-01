"""
Watchlist 管理模块

持久化存储用户自选股列表
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger


class WatchlistManager:
    """Watchlist 管理器"""
    
    DEFAULT_SYMBOLS = ["QQQM", "AAPL"]
    
    def __init__(self, file_path: Path | str):
        """
        初始化 Watchlist 管理器
        
        Args:
            file_path: 存储文件路径
        """
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._symbols: list[str] = []
        self._load()
    
    def _load(self) -> None:
        """从文件加载 Watchlist"""
        if self.file_path.exists():
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._symbols = data.get("symbols", self.DEFAULT_SYMBOLS)
                    logger.info(f"加载 Watchlist: {self._symbols}")
            except Exception as e:
                logger.error(f"加载 Watchlist 失败: {e}")
                self._symbols = self.DEFAULT_SYMBOLS.copy()
        else:
            self._symbols = self.DEFAULT_SYMBOLS.copy()
            self._save()
    
    def _save(self) -> None:
        """保存 Watchlist 到文件"""
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump({"symbols": self._symbols}, f, indent=2)
            logger.debug(f"保存 Watchlist: {self._symbols}")
        except Exception as e:
            logger.error(f"保存 Watchlist 失败: {e}")
    
    def get_all(self) -> list[str]:
        """获取所有股票"""
        return self._symbols.copy()
    
    def add(self, symbol: str) -> bool:
        """
        添加股票
        
        Args:
            symbol: 股票代码
            
        Returns:
            是否添加成功
        """
        symbol = symbol.upper().strip()
        if symbol and symbol not in self._symbols:
            self._symbols.append(symbol)
            self._save()
            return True
        return False
    
    def remove(self, symbol: str) -> bool:
        """
        移除股票
        
        Args:
            symbol: 股票代码
            
        Returns:
            是否移除成功
        """
        symbol = symbol.upper().strip()
        if symbol in self._symbols:
            self._symbols.remove(symbol)
            self._save()
            return True
        return False
    
    def contains(self, symbol: str) -> bool:
        """检查是否包含某股票"""
        return symbol.upper().strip() in self._symbols
    
    def clear(self) -> None:
        """清空 Watchlist"""
        self._symbols = []
        self._save()
    
    def reset(self) -> None:
        """重置为默认"""
        self._symbols = self.DEFAULT_SYMBOLS.copy()
        self._save()
