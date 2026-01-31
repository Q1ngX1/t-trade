"""
T-Trade 主程序入口

提供两种运行模式：
1. 实时模式：盘中实时更新，每分钟输出
2. 报告模式：收盘后生成当日总结报告
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger
from rich.console import Console
from rich.table import Table

from tbot.brokers import IBKRClient
from tbot.datafeed import DataStore
from tbot.indicators import VWAP, OpeningRange, calculate_vwap, get_ma20_from_daily
from tbot.indicators.ma20 import get_atr_from_daily
from tbot.regime import RegimeClassifier, extract_features
from tbot.report import DailyReport
from tbot.report.notifier import ConsoleNotifier, create_notifier
from tbot.settings import get_settings, init_settings
from tbot.utils import get_market_session, get_trading_progress, is_market_open, is_trading_allowed
from tbot.utils.logging import setup_logging
from tbot.utils.time import get_et_now


console = Console()


def display_realtime_status(
    symbol: str,
    price: float,
    vwap_value: float,
    or_data: dict[str, Any],
    regime_result: Any,
    trading_allowed: tuple[bool, str],
) -> None:
    """在终端显示实时状态"""
    table = Table(title=f"📊 {symbol} 实时状态")

    table.add_column("指标", style="cyan")
    table.add_column("值", style="green")

    # 价格信息
    table.add_row("当前价格", f"{price:.2f}")
    table.add_row("VWAP", f"{vwap_value:.2f}")

    position = "上方 ✅" if price > vwap_value else "下方 ❌"
    diff_pct = (price - vwap_value) / vwap_value * 100
    table.add_row("相对VWAP", f"{position} ({diff_pct:+.2f}%)")

    # OR 信息
    if or_data.get("or15_complete"):
        table.add_row("OR15 High", f"{or_data['or15_high']:.2f}")
        table.add_row("OR15 Low", f"{or_data['or15_low']:.2f}")

    # 日类型
    if regime_result:
        emoji = "📈" if "up" in regime_result.regime.value else "📉" if "down" in regime_result.regime.value else "↔️"
        table.add_row("日类型", f"{emoji} {regime_result.regime.value}")
        table.add_row("置信度", f"{regime_result.confidence:.0%}")

    # 交易许可
    allowed, reason = trading_allowed
    status = "✅ 允许" if allowed else "❌ 禁止"
    table.add_row("交易许可", f"{status} - {reason}")

    console.clear()
    console.print(table)


def run_realtime_mode(symbols: list[str], settings: Any) -> None:
    """
    实时模式：盘中实时更新

    Args:
        symbols: 监控的标的
        settings: 配置
    """
    logger.info(f"启动实时模式，监控: {symbols}")

    # 初始化组件
    store = DataStore(settings.db_path)
    classifier = RegimeClassifier()
    notifier = create_notifier({
        "telegram_bot_token": settings.notification.telegram_bot_token,
        "telegram_chat_id": settings.notification.telegram_chat_id,
        "discord_webhook_url": settings.notification.discord_webhook_url,
    })

    # VWAP 和 OR 计算器
    vwap_calculators: dict[str, VWAP] = {s: VWAP(s) for s in symbols}
    or_calculators: dict[str, OpeningRange] = {s: OpeningRange(s) for s in symbols}

    # 连接 IBKR
    client = IBKRClient(
        host=settings.ibkr.host,
        port=settings.ibkr.port,
        client_id=settings.ibkr.client_id,
        readonly=settings.ibkr.readonly,
    )

    if not client.connect_sync():
        logger.error("无法连接到 IBKR，退出")
        sys.exit(1)

    try:
        # 获取合约
        contracts = {}
        for symbol in symbols:
            contract = client.create_stock_contract(symbol)
            qualified = client.qualify_contract(contract)
            if qualified:
                contracts[symbol] = qualified
                logger.info(f"合约已验证: {symbol}")
            else:
                logger.warning(f"合约验证失败: {symbol}")

        # 获取日线数据（用于 MA20、ATR）
        daily_data: dict[str, pd.DataFrame] = {}
        for symbol, contract in contracts.items():
            df = client.get_daily_bars(contract, duration="60 D")
            if not df.empty:
                daily_data[symbol] = df
                store.save_bars_daily(symbol, df)
                logger.info(f"{symbol} 日线数据: {len(df)} 条")

        console.print("[green]数据初始化完成，开始实时监控...[/green]")
        console.print("按 Ctrl+C 退出")

        # 主循环
        while True:
            try:
                now = get_et_now()
                session = get_market_session(now)
                progress = get_trading_progress(now)
                trading_allowed = is_trading_allowed(now)

                # 获取日内数据
                for symbol, contract in contracts.items():
                    # 获取当日分钟数据
                    intraday_df = client.get_intraday_bars(contract, duration="1 D")

                    if intraday_df.empty:
                        continue

                    # 更新 VWAP
                    vwap = vwap_calculators[symbol]
                    for _, row in intraday_df.iterrows():
                        timestamp = row.get("date") or row.get("timestamp")
                        if isinstance(timestamp, str):
                            timestamp = pd.to_datetime(timestamp)
                        vwap.update_from_bar(
                            timestamp,
                            row["high"],
                            row["low"],
                            row["close"],
                            row["volume"],
                        )

                    # 更新 OR
                    or_calc = or_calculators[symbol]
                    for _, row in intraday_df.iterrows():
                        timestamp = row.get("date") or row.get("timestamp")
                        if isinstance(timestamp, str):
                            timestamp = pd.to_datetime(timestamp)
                        or_calc.update(timestamp, row["high"], row["low"])

                    # 计算特征和分类
                    daily_df = daily_data.get(symbol)
                    prev_close = float(daily_df["close"].iloc[-1]) if daily_df is not None and not daily_df.empty else None

                    features = extract_features(
                        intraday_df,
                        daily_df,
                        symbol=symbol,
                        date=now.strftime("%Y-%m-%d"),
                        prev_close=prev_close,
                    )

                    result = classifier.classify_realtime(features, progress)

                    # 显示状态
                    current_price = float(intraday_df["close"].iloc[-1])
                    display_realtime_status(
                        symbol,
                        current_price,
                        vwap.value,
                        or_calc.to_dict(),
                        result,
                        trading_allowed,
                    )

                # 等待下一分钟
                client.sleep(60)

            except KeyboardInterrupt:
                logger.info("收到退出信号")
                break
            except Exception as e:
                logger.error(f"实时更新异常: {e}")
                client.sleep(5)

    finally:
        client.disconnect()


def run_report_mode(symbols: list[str], settings: Any, date: str | None = None) -> None:
    """
    报告模式：生成当日报告

    Args:
        symbols: 分析的标的
        settings: 配置
        date: 日期（默认今天）
    """
    if date is None:
        date = get_et_now().strftime("%Y-%m-%d")

    logger.info(f"生成 {date} 报告，标的: {symbols}")

    # 初始化组件
    store = DataStore(settings.db_path)
    classifier = RegimeClassifier()

    # 连接 IBKR
    client = IBKRClient(
        host=settings.ibkr.host,
        port=settings.ibkr.port,
        client_id=settings.ibkr.client_id,
        readonly=settings.ibkr.readonly,
    )

    if not client.connect_sync():
        logger.error("无法连接到 IBKR，退出")
        sys.exit(1)

    try:
        report = DailyReport(date=date)

        for symbol in symbols:
            console.print(f"[cyan]分析 {symbol}...[/cyan]")

            # 获取合约
            contract = client.create_stock_contract(symbol)
            qualified = client.qualify_contract(contract)
            if not qualified:
                logger.warning(f"合约验证失败: {symbol}")
                continue

            # 获取日内数据
            intraday_df = client.get_intraday_bars(qualified, duration="1 D")
            if intraday_df.empty:
                logger.warning(f"{symbol} 无日内数据")
                continue

            # 保存数据
            store.save_bars_1m(symbol, intraday_df)

            # 获取日线数据
            daily_df = client.get_daily_bars(qualified, duration="60 D")
            if not daily_df.empty:
                store.save_bars_daily(symbol, daily_df)

            # 计算前日收盘价
            prev_close = float(daily_df["close"].iloc[-2]) if len(daily_df) >= 2 else None

            # 提取特征
            features = extract_features(
                intraday_df,
                daily_df,
                symbol=symbol,
                date=date,
                prev_close=prev_close,
            )

            # 分类
            result = classifier.classify(features)

            # 保存分类结果
            store.save_regime(symbol, date, result.regime.value, features.to_dict())

            # 添加到报告
            report.add_regime_result(symbol, result, features)

            # 显示结果
            emoji = "📈" if "up" in result.regime.value else "📉" if "down" in result.regime.value else "↔️"
            console.print(f"  {emoji} {result.regime.value} (置信度: {result.confidence:.0%})")
            for reason in result.reasons:
                console.print(f"    - {reason}")

        # 保存报告
        md_path, json_path = report.save(settings.reports_dir)

        console.print(f"\n[green]报告已生成:[/green]")
        console.print(f"  Markdown: {md_path}")
        console.print(f"  JSON: {json_path}")

        # 输出报告内容预览
        console.print("\n" + "=" * 50)
        console.print(report.to_markdown())

    finally:
        client.disconnect()


def run_demo_mode(symbols: list[str], settings: Any) -> None:
    """
    演示模式：不连接 IBKR，使用模拟数据

    Args:
        symbols: 标的
        settings: 配置
    """
    import numpy as np

    logger.info("启动演示模式（模拟数据）")

    # 生成模拟数据
    def generate_mock_data(symbol: str, n_bars: int = 390) -> pd.DataFrame:
        """生成模拟的日内数据"""
        np.random.seed(hash(symbol) % 2**32)

        base_price = {"QQQM": 200, "AAPL": 180, "MU": 90}.get(symbol, 100)

        # 生成随机走势
        returns = np.random.randn(n_bars) * 0.001
        prices = base_price * np.cumprod(1 + returns)

        # 生成 OHLC
        data = []
        for i, close in enumerate(prices):
            volatility = np.random.uniform(0.001, 0.003)
            high = close * (1 + volatility)
            low = close * (1 - volatility)
            open_ = prices[i - 1] if i > 0 else close
            volume = np.random.uniform(10000, 100000)

            timestamp = pd.Timestamp("2024-01-15 09:30:00") + pd.Timedelta(minutes=i)

            data.append({
                "timestamp": timestamp,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            })

        return pd.DataFrame(data)

    # 初始化组件
    store = DataStore(settings.db_path)
    classifier = RegimeClassifier()

    date = get_et_now().strftime("%Y-%m-%d")
    report = DailyReport(date=date)

    for symbol in symbols:
        console.print(f"[cyan]分析 {symbol} (模拟数据)...[/cyan]")

        # 生成模拟数据
        intraday_df = generate_mock_data(symbol)

        # 提取特征
        features = extract_features(
            intraday_df,
            daily_df=None,
            symbol=symbol,
            date=date,
        )

        # 分类
        result = classifier.classify(features)

        # 添加到报告
        report.add_regime_result(symbol, result, features)

        # 显示结果
        emoji = "📈" if "up" in result.regime.value else "📉" if "down" in result.regime.value else "↔️"
        console.print(f"  {emoji} {result.regime.value} (置信度: {result.confidence:.0%})")
        for reason in result.reasons:
            console.print(f"    - {reason}")

    # 保存报告
    md_path, json_path = report.save(settings.reports_dir)

    console.print(f"\n[green]演示报告已生成:[/green]")
    console.print(f"  Markdown: {md_path}")
    console.print(f"  JSON: {json_path}")


def main() -> None:
    """主函数"""
    parser = argparse.ArgumentParser(
        description="T-Trade: IBKR 日内交易提示系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  tbot realtime          # 实时模式
  tbot report            # 生成当日报告
  tbot demo              # 演示模式（不需要 IBKR）
  tbot realtime -s AAPL  # 只监控 AAPL
        """,
    )

    parser.add_argument(
        "mode",
        choices=["realtime", "report", "demo"],
        nargs="?",
        default="demo",
        help="运行模式: realtime(实时), report(报告), demo(演示)",
    )

    parser.add_argument(
        "-s", "--symbols",
        nargs="+",
        default=["QQQM", "AAPL"],
        help="监控的标的 (默认: QQQM AAPL)",
    )

    parser.add_argument(
        "-d", "--date",
        help="报告日期 (格式: YYYY-MM-DD)",
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="调试模式",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=7497,
        help="IBKR 端口 (默认: 7497=TWS, 4001=Gateway)",
    )

    args = parser.parse_args()

    # 初始化配置
    settings = init_settings(debug=args.debug)
    settings.ibkr.port = args.port

    # 配置日志
    log_level = "DEBUG" if args.debug else "INFO"
    setup_logging(log_level=log_level, log_dir=settings.abs_log_dir)

    # 显示启动信息
    console.print("[bold blue]T-Trade 交易提示系统[/bold blue]")
    console.print(f"模式: {args.mode}")
    console.print(f"标的: {args.symbols}")
    console.print("")

    # 运行
    if args.mode == "realtime":
        run_realtime_mode(args.symbols, settings)
    elif args.mode == "report":
        run_report_mode(args.symbols, settings, args.date)
    else:
        run_demo_mode(args.symbols, settings)


if __name__ == "__main__":
    main()
