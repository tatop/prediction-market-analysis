"""Compare basic OHLCV metrics across Alpaca symbols."""

from __future__ import annotations

from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import pandas as pd

from src.common.analysis import Analysis, AnalysisOutput
from src.common.interfaces.chart import ChartConfig, ChartType, ScaleType, UnitType


class AlpacaBarMetricsAnalysis(Analysis):
    """Compare basic financial metrics across symbols from Alpaca bar data."""

    def __init__(self, bars_dir: Path | str | None = None):
        super().__init__(
            name="alpaca_bar_metrics",
            description="Compares cumulative return, volatility, and volume across Alpaca symbols",
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
                    open,
                    high,
                    low,
                    close,
                    volume,
                    vwap
                FROM '{self.bars_dir}/*.parquet'
                ORDER BY symbol, timestamp
                """
            ).df()

        if df.empty:
            raise FileNotFoundError(f"No bar data found in {self.bars_dir}. Run the alpaca_bars indexer first.")

        summary = self._compute_summary(df)
        fig = self._create_figure(df, summary)
        chart = self._create_chart(summary)

        return AnalysisOutput(figure=fig, data=summary, chart=chart)

    def _compute_summary(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute per-symbol summary metrics."""
        records = []
        for symbol, group in df.groupby("symbol"):
            group = group.sort_values("timestamp")
            closes = group["close"]
            daily_returns = closes.pct_change().dropna()

            cumulative_return = (closes.iloc[-1] / closes.iloc[0] - 1) * 100 if len(closes) > 1 else 0.0
            annualized_vol = daily_returns.std() * (252**0.5) * 100 if len(daily_returns) > 1 else 0.0
            avg_daily_volume = group["volume"].mean()
            avg_spread = ((group["high"] - group["low"]) / group["close"]).mean() * 100
            avg_vwap_deviation = ((group["close"] - group["vwap"]).abs() / group["vwap"]).mean() * 100
            trading_days = len(group)

            records.append(
                {
                    "symbol": symbol,
                    "cumulative_return_pct": round(cumulative_return, 2),
                    "annualized_volatility_pct": round(annualized_vol, 2),
                    "avg_daily_volume": int(avg_daily_volume),
                    "avg_daily_range_pct": round(avg_spread, 2),
                    "avg_vwap_deviation_pct": round(avg_vwap_deviation, 4),
                    "trading_days": trading_days,
                }
            )

        return pd.DataFrame(records).sort_values("cumulative_return_pct", ascending=False).reset_index(drop=True)

    def _create_figure(self, df: pd.DataFrame, summary: pd.DataFrame) -> plt.Figure:
        """Create a 2x2 panel comparing metrics across symbols."""
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        colors = plt.cm.tab10.colors

        # Panel 1: Cumulative return
        ax = axes[0, 0]
        sorted_ret = summary.sort_values("cumulative_return_pct", ascending=True)
        bar_colors = ["#e74c3c" if v < 0 else "#2ecc71" for v in sorted_ret["cumulative_return_pct"]]
        ax.barh(sorted_ret["symbol"], sorted_ret["cumulative_return_pct"], color=bar_colors)
        ax.set_xlabel("Cumulative Return (%)")
        ax.set_title("Cumulative Return by Symbol")
        ax.axvline(0, color="gray", linewidth=0.5)

        # Panel 2: Annualized volatility
        ax = axes[0, 1]
        sorted_vol = summary.sort_values("annualized_volatility_pct", ascending=True)
        ax.barh(sorted_vol["symbol"], sorted_vol["annualized_volatility_pct"], color="#4C72B0")
        ax.set_xlabel("Annualized Volatility (%)")
        ax.set_title("Annualized Volatility by Symbol")

        # Panel 3: Average daily volume
        ax = axes[1, 0]
        sorted_dvol = summary.sort_values("avg_daily_volume", ascending=True)
        ax.barh(sorted_dvol["symbol"], sorted_dvol["avg_daily_volume"] / 1e6, color="#e67e22")
        ax.set_xlabel("Avg Daily Volume (millions)")
        ax.set_title("Average Daily Volume by Symbol")

        # Panel 4: Return vs Volatility scatter
        ax = axes[1, 1]
        for i, (_, row) in enumerate(summary.iterrows()):
            color = colors[i % len(colors)]
            ax.scatter(row["annualized_volatility_pct"], row["cumulative_return_pct"], color=color, s=80, zorder=3)
            ax.annotate(row["symbol"], (row["annualized_volatility_pct"], row["cumulative_return_pct"]),
                        fontsize=8, ha="left", va="bottom", xytext=(4, 4), textcoords="offset points")
        ax.set_xlabel("Annualized Volatility (%)")
        ax.set_ylabel("Cumulative Return (%)")
        ax.set_title("Return vs Volatility")
        ax.axhline(0, color="gray", linewidth=0.5)
        ax.grid(True, alpha=0.3)

        fig.suptitle("Alpaca Bar Metrics Comparison", fontsize=14, fontweight="bold")
        plt.tight_layout()
        return fig

    def _create_chart(self, summary: pd.DataFrame) -> ChartConfig:
        """Create the chart configuration for web display."""
        chart_data = [
            {
                "symbol": row["symbol"],
                "cumulative_return_pct": row["cumulative_return_pct"],
                "annualized_volatility_pct": row["annualized_volatility_pct"],
            }
            for _, row in summary.iterrows()
        ]

        return ChartConfig(
            type=ChartType.BAR,
            data=chart_data,
            xKey="symbol",
            yKeys=["cumulative_return_pct", "annualized_volatility_pct"],
            title="Alpaca Bar Metrics by Symbol",
            xLabel="Symbol",
            yLabel="Percentage (%)",
        )
