"""Drawdown metrics analysis for Alpaca symbols."""

from __future__ import annotations

from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import pandas as pd

from src.common.analysis import Analysis, AnalysisOutput
from src.common.interfaces.chart import ChartConfig, ChartType, UnitType


class AlpacaDrawdownMetricsAnalysis(Analysis):
    """Compute max drawdown, drawdown duration, and recovery time per symbol."""

    def __init__(self, bars_dir: Path | str | None = None):
        super().__init__(
            name="alpaca_drawdown_metrics",
            description="Computes max drawdown, duration to trough, and recovery time by symbol",
        )
        base_dir = Path(__file__).parent.parent.parent.parent
        self.bars_dir = Path(bars_dir or base_dir / "data" / "alpaca" / "bars")

    def run(self) -> AnalysisOutput:
        con = duckdb.connect()

        with self.progress("Loading Alpaca bar data"):
            df = con.execute(
                f"""
                SELECT
                    symbol,
                    timestamp,
                    close
                FROM '{self.bars_dir}/*.parquet'
                ORDER BY symbol, timestamp
                """
            ).df()

        if df.empty:
            raise FileNotFoundError(f"No bar data found in {self.bars_dir}. Run the alpaca_bars indexer first.")

        summary = self._compute_drawdown_summary(df)
        fig = self._create_figure(summary)
        chart = self._create_chart(summary)
        return AnalysisOutput(figure=fig, data=summary, chart=chart)

    def _compute_drawdown_summary(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute drawdown metrics per symbol."""
        rows: list[dict[str, str | float | int | None]] = []

        for symbol, group in df.groupby("symbol"):
            series = group.sort_values("timestamp").reset_index(drop=True).copy()
            series["timestamp"] = pd.to_datetime(series["timestamp"])

            running_peak = series["close"].cummax()
            drawdown = series["close"] / running_peak - 1.0

            trough_idx = int(drawdown.idxmin())
            trough_drawdown = float(drawdown.iloc[trough_idx])
            trough_date = series.loc[trough_idx, "timestamp"]

            peak_price = float(running_peak.iloc[trough_idx])
            pre_trough = series.iloc[: trough_idx + 1]
            peak_candidates = pre_trough.index[pre_trough["close"] >= peak_price]
            peak_idx = int(peak_candidates[-1]) if len(peak_candidates) > 0 else 0
            peak_date = series.loc[peak_idx, "timestamp"]

            duration_days = int((trough_date - peak_date).days)
            duration_trading_days = int(trough_idx - peak_idx)

            recovery_candidates = series.iloc[trough_idx + 1 :]
            recovery_hit = recovery_candidates[recovery_candidates["close"] >= peak_price]
            if recovery_hit.empty:
                recovery_date = None
                recovery_days = None
                recovery_trading_days = None
            else:
                recovery_date = pd.to_datetime(recovery_hit.iloc[0]["timestamp"])
                recovery_idx = int(recovery_hit.index[0])
                recovery_days = int((recovery_date - trough_date).days)
                recovery_trading_days = int(recovery_idx - trough_idx)

            rows.append(
                {
                    "symbol": symbol,
                    "max_drawdown_pct": round(trough_drawdown * 100, 2),
                    "peak_date": peak_date.strftime("%Y-%m-%d"),
                    "trough_date": trough_date.strftime("%Y-%m-%d"),
                    "drawdown_duration_days": duration_days,
                    "drawdown_duration_trading_days": duration_trading_days,
                    "recovery_date": recovery_date.strftime("%Y-%m-%d") if recovery_date is not None else None,
                    "recovery_time_days": recovery_days,
                    "recovery_time_trading_days": recovery_trading_days,
                }
            )

        return pd.DataFrame(rows).sort_values("max_drawdown_pct").reset_index(drop=True)

    def _create_figure(self, summary: pd.DataFrame) -> plt.Figure:
        """Create drawdown bars and duration comparison panel."""
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))

        # Max drawdown by symbol
        ax = axes[0]
        colors = ["#d62728" if val < 0 else "#2ca02c" for val in summary["max_drawdown_pct"]]
        ax.barh(summary["symbol"], summary["max_drawdown_pct"], color=colors)
        ax.axvline(0, color="gray", linewidth=0.8)
        ax.set_xlabel("Max Drawdown (%)")
        ax.set_title("Maximum Drawdown by Symbol")

        # Drawdown duration and recovery time
        ax = axes[1]
        duration = summary["drawdown_duration_trading_days"].astype(float)
        recovery = summary["recovery_time_trading_days"].astype(float)
        y_pos = range(len(summary))
        width = 0.4

        ax.barh([y - width / 2 for y in y_pos], duration, height=width, label="Peak to Trough", color="#1f77b4")
        ax.barh([y + width / 2 for y in y_pos], recovery, height=width, label="Trough to Recovery", color="#ff7f0e")
        ax.set_yticks(list(y_pos))
        ax.set_yticklabels(summary["symbol"])
        ax.set_xlabel("Trading Days")
        ax.set_title("Drawdown Duration vs Recovery Time")
        ax.legend(loc="lower right")

        fig.suptitle("Alpaca Drawdown Analysis", fontsize=14, fontweight="bold")
        plt.tight_layout()
        return fig

    def _create_chart(self, summary: pd.DataFrame) -> ChartConfig:
        """Create a compact chart config for max drawdown values."""
        chart_data = [
            {
                "symbol": row["symbol"],
                "max_drawdown_pct": row["max_drawdown_pct"],
            }
            for _, row in summary.iterrows()
        ]

        return ChartConfig(
            type=ChartType.BAR,
            data=chart_data,
            xKey="symbol",
            yKeys=["max_drawdown_pct"],
            yUnit=UnitType.PERCENT,
            title="Max Drawdown by Symbol",
            xLabel="Symbol",
            yLabel="Drawdown (%)",
        )
