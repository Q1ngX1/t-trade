"""
日志配置模块
"""

import sys
from pathlib import Path

from loguru import logger


def setup_logging(
    log_level: str = "INFO",
    log_dir: Path | None = None,
    log_to_file: bool = True,
) -> None:
    """
    配置日志

    Args:
        log_level: 日志级别
        log_dir: 日志目录
        log_to_file: 是否写入文件
    """
    # 移除默认 handler
    logger.remove()

    # 控制台输出格式
    console_format = (
        "<green>{time:HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    )

    # 添加控制台 handler
    logger.add(
        sys.stderr,
        format=console_format,
        level=log_level,
        colorize=True,
    )

    # 添加文件 handler
    if log_to_file and log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)

        file_format = (
            "{time:YYYY-MM-DD HH:mm:ss} | "
            "{level: <8} | "
            "{name}:{function}:{line} - "
            "{message}"
        )

        # 主日志文件（按日期轮转）
        logger.add(
            log_dir / "tbot_{time:YYYY-MM-DD}.log",
            format=file_format,
            level=log_level,
            rotation="00:00",  # 每天轮转
            retention="30 days",  # 保留30天
            compression="zip",
        )

        # 错误日志单独文件
        logger.add(
            log_dir / "errors_{time:YYYY-MM-DD}.log",
            format=file_format,
            level="ERROR",
            rotation="00:00",
            retention="30 days",
            compression="zip",
        )

    logger.info(f"日志配置完成: level={log_level}")
