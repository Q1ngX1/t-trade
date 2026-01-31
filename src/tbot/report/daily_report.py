"""
日报生成模块

生成 Markdown 格式的每日报告（Obsidian 友好）
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from tbot.regime.features import RegimeFeatures
from tbot.regime.rules import ClassificationResult, Regime


@dataclass
class SignalSummary:
    """信号摘要"""

    symbol: str
    timestamp: datetime
    signal_type: str  # "entry", "exit", "no_trade"
    direction: str | None = None  # "long", "short"
    entry_price: float | None = None
    stop_loss: float | None = None
    target_price: float | None = None
    r_ratio: float | None = None
    notes: str = ""


@dataclass
class DailyReport:
    """每日报告"""

    date: str
    generated_at: datetime = field(default_factory=datetime.now)

    # 各标的分类结果
    regime_results: dict[str, ClassificationResult] = field(default_factory=dict)

    # 各标的特征
    features: dict[str, RegimeFeatures] = field(default_factory=dict)

    # 信号
    signals: list[SignalSummary] = field(default_factory=list)

    # 可交易性判断
    tradeable_symbols: list[str] = field(default_factory=list)
    non_tradeable_reasons: dict[str, str] = field(default_factory=dict)

    # 备注
    notes: str = ""

    def add_regime_result(
        self,
        symbol: str,
        result: ClassificationResult,
        features: RegimeFeatures,
    ) -> None:
        """添加分类结果"""
        self.regime_results[symbol] = result
        self.features[symbol] = features

        # 判断可交易性
        if result.regime in [Regime.TREND_UP, Regime.TREND_DOWN]:
            if result.confidence >= 0.5:
                self.tradeable_symbols.append(symbol)
            else:
                self.non_tradeable_reasons[symbol] = "趋势日但置信度不足"
        elif result.regime == Regime.RANGE:
            self.non_tradeable_reasons[symbol] = "震荡日，不建议交易"
        elif result.regime == Regime.EVENT:
            self.non_tradeable_reasons[symbol] = "事件日，风险较高"
        else:
            self.non_tradeable_reasons[symbol] = "日类型不明确"

    def add_signal(self, signal: SignalSummary) -> None:
        """添加信号"""
        self.signals.append(signal)

    def to_markdown(self) -> str:
        """生成 Markdown 格式报告"""
        lines = [
            f"# 交易日报 {self.date}",
            "",
            f"> 生成时间: {self.generated_at.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "---",
            "",
            "## 📊 日类型分类",
            "",
        ]

        # 分类结果表格
        lines.extend([
            "| 标的 | 日类型 | 置信度 | 可交易 |",
            "|------|--------|--------|--------|",
        ])

        for symbol in sorted(self.regime_results.keys()):
            result = self.regime_results[symbol]
            regime_emoji = self._get_regime_emoji(result.regime)
            tradeable = "✅" if symbol in self.tradeable_symbols else "❌"
            lines.append(
                f"| {symbol} | {regime_emoji} {result.regime.value} | "
                f"{result.confidence:.0%} | {tradeable} |"
            )

        lines.append("")

        # 详细分析
        lines.extend([
            "## 📈 详细分析",
            "",
        ])

        for symbol in sorted(self.regime_results.keys()):
            result = self.regime_results[symbol]
            feat = self.features.get(symbol)

            lines.extend([
                f"### {symbol}",
                "",
                f"**日类型**: {result.regime.value}",
                f"**置信度**: {result.confidence:.0%}",
                "",
                "**判断依据**:",
            ])

            for reason in result.reasons:
                lines.append(f"- {reason}")

            if feat:
                lines.extend([
                    "",
                    "**关键指标**:",
                    f"- VWAP 穿越次数: {feat.vwap_cross_count}",
                    f"- VWAP 上方时间: {feat.pct_time_above_vwap:.1%}",
                    f"- 当日波动: {feat.intraday_range:.2f} ({feat.intraday_range_pct:.2%})",
                ])

                if feat.or15_width:
                    lines.append(f"- OR15 宽度: {feat.or15_width:.2f}")
                if feat.range_atr_ratio:
                    lines.append(f"- 波动/ATR: {feat.range_atr_ratio:.2f}")
                if abs(feat.gap_pct) > 0.001:
                    lines.append(f"- 开盘缺口: {feat.gap_pct:.2%}")

            lines.append("")

        # 交易建议
        lines.extend([
            "## 💡 交易建议",
            "",
        ])

        if self.tradeable_symbols:
            lines.append("**可交易标的**:")
            for symbol in self.tradeable_symbols:
                result = self.regime_results[symbol]
                direction = "做多" if result.regime == Regime.TREND_UP else "做空"
                lines.append(f"- {symbol}: {direction}信号")
        else:
            lines.append("**今日无明确交易机会**")

        lines.append("")

        if self.non_tradeable_reasons:
            lines.append("**不建议交易**:")
            for symbol, reason in self.non_tradeable_reasons.items():
                lines.append(f"- {symbol}: {reason}")

        lines.append("")

        # 信号详情
        if self.signals:
            lines.extend([
                "## 🎯 信号详情",
                "",
            ])

            for signal in self.signals:
                lines.extend([
                    f"### {signal.symbol} - {signal.signal_type}",
                    f"- 时间: {signal.timestamp}",
                ])
                if signal.direction:
                    lines.append(f"- 方向: {signal.direction}")
                if signal.entry_price:
                    lines.append(f"- 入场价: {signal.entry_price:.2f}")
                if signal.stop_loss:
                    lines.append(f"- 止损价: {signal.stop_loss:.2f}")
                if signal.target_price:
                    lines.append(f"- 目标价: {signal.target_price:.2f}")
                if signal.r_ratio:
                    lines.append(f"- 风险收益比: 1:{signal.r_ratio:.1f}")
                if signal.notes:
                    lines.append(f"- 备注: {signal.notes}")
                lines.append("")

        # 备注
        if self.notes:
            lines.extend([
                "## 📝 备注",
                "",
                self.notes,
                "",
            ])

        lines.extend([
            "---",
            "",
            "*本报告由 T-Trade 系统自动生成*",
        ])

        return "\n".join(lines)

    def _get_regime_emoji(self, regime: Regime) -> str:
        """获取日类型对应的 emoji"""
        emoji_map = {
            Regime.TREND_UP: "📈",
            Regime.TREND_DOWN: "📉",
            Regime.RANGE: "↔️",
            Regime.EVENT: "⚡",
            Regime.UNKNOWN: "❓",
        }
        return emoji_map.get(regime, "❓")

    def to_json(self) -> str:
        """生成 JSON 格式"""
        data = {
            "date": self.date,
            "generated_at": self.generated_at.isoformat(),
            "regime_results": {
                symbol: result.to_dict()
                for symbol, result in self.regime_results.items()
            },
            "features": {
                symbol: feat.to_dict()
                for symbol, feat in self.features.items()
            },
            "tradeable_symbols": self.tradeable_symbols,
            "non_tradeable_reasons": self.non_tradeable_reasons,
            "signals": [
                {
                    "symbol": s.symbol,
                    "timestamp": s.timestamp.isoformat(),
                    "signal_type": s.signal_type,
                    "direction": s.direction,
                    "entry_price": s.entry_price,
                    "stop_loss": s.stop_loss,
                    "target_price": s.target_price,
                }
                for s in self.signals
            ],
            "notes": self.notes,
        }
        return json.dumps(data, indent=2, ensure_ascii=False)

    def save(self, output_dir: Path) -> tuple[Path, Path]:
        """
        保存报告

        Args:
            output_dir: 输出目录

        Returns:
            (Markdown 文件路径, JSON 文件路径)
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        md_path = output_dir / f"daily_report_{self.date}.md"
        json_path = output_dir / f"daily_report_{self.date}.json"

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(self.to_markdown())
        logger.info(f"Markdown 报告已保存: {md_path}")

        with open(json_path, "w", encoding="utf-8") as f:
            f.write(self.to_json())
        logger.info(f"JSON 报告已保存: {json_path}")

        return md_path, json_path


def generate_daily_report(
    date: str,
    regime_results: dict[str, ClassificationResult],
    features: dict[str, RegimeFeatures],
    signals: list[SignalSummary] | None = None,
    notes: str = "",
) -> DailyReport:
    """
    生成每日报告

    Args:
        date: 日期
        regime_results: 分类结果
        features: 特征
        signals: 信号列表
        notes: 备注

    Returns:
        DailyReport
    """
    report = DailyReport(date=date, notes=notes)

    for symbol in regime_results:
        result = regime_results[symbol]
        feat = features.get(symbol)
        if feat:
            report.add_regime_result(symbol, result, feat)

    if signals:
        for signal in signals:
            report.add_signal(signal)

    return report
