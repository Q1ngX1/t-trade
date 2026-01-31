"""
配置管理模块

使用 pydantic-settings 管理配置，支持：
- 环境变量
- .env 文件
- YAML 配置文件
"""

from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def load_yaml_config(file_path: Path) -> dict[str, Any]:
    """加载 YAML 配置文件"""
    if file_path.exists():
        with open(file_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


class IBKRSettings(BaseSettings):
    """IBKR 连接配置"""

    host: str = Field(default="127.0.0.1", description="TWS/Gateway 主机地址")
    port: int = Field(default=7497, description="TWS/Gateway 端口 (7497=TWS, 4001=Gateway)")
    client_id: int = Field(default=1, description="客户端ID")
    timeout: int = Field(default=30, description="连接超时（秒）")
    readonly: bool = Field(default=True, description="只读模式（第一阶段推荐）")

    model_config = SettingsConfigDict(env_prefix="IBKR_")


class NotificationSettings(BaseSettings):
    """通知配置"""

    telegram_bot_token: str | None = Field(default=None, description="Telegram Bot Token")
    telegram_chat_id: str | None = Field(default=None, description="Telegram Chat ID")
    discord_webhook_url: str | None = Field(default=None, description="Discord Webhook URL")

    model_config = SettingsConfigDict(env_prefix="NOTIFY_")


class Settings(BaseSettings):
    """主配置类"""

    # 项目路径
    project_root: Path = Field(
        default_factory=lambda: Path(__file__).parent.parent.parent.parent,
        description="项目根目录",
    )

    # 数据目录
    data_dir: Path = Field(default=Path("data"), description="数据目录")
    config_dir: Path = Field(default=Path("config"), description="配置目录")

    # 日志配置
    log_level: str = Field(default="INFO", description="日志级别")
    log_dir: Path = Field(default=Path("logs"), description="日志目录")

    # 运行模式
    debug: bool = Field(default=False, description="调试模式")
    dry_run: bool = Field(default=True, description="模拟运行（不实际下单）")

    # 子配置
    ibkr: IBKRSettings = Field(default_factory=IBKRSettings)
    notification: NotificationSettings = Field(default_factory=NotificationSettings)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    @property
    def abs_data_dir(self) -> Path:
        """数据目录绝对路径"""
        if self.data_dir.is_absolute():
            return self.data_dir
        return self.project_root / self.data_dir

    @property
    def abs_config_dir(self) -> Path:
        """配置目录绝对路径"""
        if self.config_dir.is_absolute():
            return self.config_dir
        return self.project_root / self.config_dir

    @property
    def abs_log_dir(self) -> Path:
        """日志目录绝对路径"""
        if self.log_dir.is_absolute():
            return self.log_dir
        return self.project_root / self.log_dir

    @property
    def db_path(self) -> Path:
        """SQLite 数据库路径"""
        return self.abs_data_dir / "db" / "tbot.db"

    @property
    def reports_dir(self) -> Path:
        """报告目录"""
        return self.abs_data_dir / "reports"

    def load_symbols_config(self) -> dict[str, Any]:
        """加载标的配置"""
        return load_yaml_config(self.abs_config_dir / "symbols.yaml")

    def load_params_config(self) -> dict[str, Any]:
        """加载参数配置"""
        return load_yaml_config(self.abs_config_dir / "params.yaml")

    def load_calendar_config(self) -> dict[str, Any]:
        """加载日历配置"""
        return load_yaml_config(self.abs_config_dir / "calendar.yaml")


# 全局配置单例
_settings: Settings | None = None


def get_settings() -> Settings:
    """获取全局配置"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def init_settings(**kwargs: Any) -> Settings:
    """初始化全局配置（允许覆盖默认值）"""
    global _settings
    _settings = Settings(**kwargs)
    return _settings
