"""
通知模块

支持 Telegram / Discord 通知
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import httpx
from loguru import logger


class Notifier(ABC):
    """通知器基类"""

    @abstractmethod
    async def send(self, message: str) -> bool:
        """发送消息"""
        ...

    @abstractmethod
    def send_sync(self, message: str) -> bool:
        """同步发送消息"""
        ...


class TelegramNotifier(Notifier):
    """Telegram 通知器"""

    def __init__(self, bot_token: str, chat_id: str):
        """
        初始化 Telegram 通知器

        Args:
            bot_token: Bot Token
            chat_id: Chat ID
        """
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"

    async def send(self, message: str) -> bool:
        """异步发送消息"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/sendMessage",
                    json={
                        "chat_id": self.chat_id,
                        "text": message,
                        "parse_mode": "Markdown",
                    },
                    timeout=10.0,
                )
                if response.status_code == 200:
                    logger.debug("Telegram 消息发送成功")
                    return True
                else:
                    logger.error(f"Telegram 发送失败: {response.text}")
                    return False
        except Exception as e:
            logger.error(f"Telegram 发送异常: {e}")
            return False

    def send_sync(self, message: str) -> bool:
        """同步发送消息"""
        try:
            with httpx.Client() as client:
                response = client.post(
                    f"{self.base_url}/sendMessage",
                    json={
                        "chat_id": self.chat_id,
                        "text": message,
                        "parse_mode": "Markdown",
                    },
                    timeout=10.0,
                )
                if response.status_code == 200:
                    logger.debug("Telegram 消息发送成功")
                    return True
                else:
                    logger.error(f"Telegram 发送失败: {response.text}")
                    return False
        except Exception as e:
            logger.error(f"Telegram 发送异常: {e}")
            return False


class DiscordNotifier(Notifier):
    """Discord 通知器"""

    def __init__(self, webhook_url: str):
        """
        初始化 Discord 通知器

        Args:
            webhook_url: Discord Webhook URL
        """
        self.webhook_url = webhook_url

    async def send(self, message: str) -> bool:
        """异步发送消息"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.webhook_url,
                    json={"content": message},
                    timeout=10.0,
                )
                if response.status_code in [200, 204]:
                    logger.debug("Discord 消息发送成功")
                    return True
                else:
                    logger.error(f"Discord 发送失败: {response.text}")
                    return False
        except Exception as e:
            logger.error(f"Discord 发送异常: {e}")
            return False

    def send_sync(self, message: str) -> bool:
        """同步发送消息"""
        try:
            with httpx.Client() as client:
                response = client.post(
                    self.webhook_url,
                    json={"content": message},
                    timeout=10.0,
                )
                if response.status_code in [200, 204]:
                    logger.debug("Discord 消息发送成功")
                    return True
                else:
                    logger.error(f"Discord 发送失败: {response.text}")
                    return False
        except Exception as e:
            logger.error(f"Discord 发送异常: {e}")
            return False


class ConsoleNotifier(Notifier):
    """控制台通知器（用于测试）"""

    async def send(self, message: str) -> bool:
        """打印到控制台"""
        print(f"\n{'='*50}")
        print("📢 通知:")
        print(message)
        print(f"{'='*50}\n")
        return True

    def send_sync(self, message: str) -> bool:
        """同步打印"""
        print(f"\n{'='*50}")
        print("📢 通知:")
        print(message)
        print(f"{'='*50}\n")
        return True


def create_notifier(config: dict[str, Any]) -> Notifier | None:
    """
    根据配置创建通知器

    Args:
        config: 通知配置

    Returns:
        Notifier 或 None
    """
    if config.get("telegram_bot_token") and config.get("telegram_chat_id"):
        return TelegramNotifier(
            bot_token=config["telegram_bot_token"],
            chat_id=config["telegram_chat_id"],
        )

    if config.get("discord_webhook_url"):
        return DiscordNotifier(webhook_url=config["discord_webhook_url"])

    logger.warning("未配置通知渠道，使用控制台输出")
    return ConsoleNotifier()
