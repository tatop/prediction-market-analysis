"""Excess-return analysis for Alpaca symbols versus SPY."""

from __future__ import annotations

from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.common.analysis import Analysis, AnalysisOutput
from src.common.interfaces.chart import ChartConfig, ChartType, UnitType


class AlpacaExcessReturnsVsSpyAnalysis(Analysis):
    """Measure each symbol's return in excess of SPY."""

    def __init__(
        self,
        bars_dir: Path | str | None = None,
        benchmark_symbol: str = "SPY",
    ):
        super().__init__(
            name="alpaca_excess_returns_vs_spy",
            description="Computes cumulative and annualized excess returns relative to SPY",
        )
        base_dir = Path(__file__).parent.parent.parent.parent
        self.bars_dir = Path(bars_dir or base_dir / "data" / "alpaca" / "bars")
        self.benchmark_symbol = benchmark_symbol.upper()

    def run(self) -> AnalysisOutput:
        con = duckdb.connect()

        with self.progress("Loading Alpaca bar closes"):
            df = con.execute(
                f"""
                SELECT
                    symbol,
                    timestamp::DATE AS date,
                    close
                FROM '{self.bars_dir}/*.parquet'
                ORDER BY symbol, date
                """
            ).df()

        if df.empty:
            raise FileNotFoundError(f"No bar data found in {self.bars_dir}. Run the alpaca_bars indexer first.")

        with self.progress(f"Computing excess returns vs {self.benchmark_symbol}"):
            cumulative_excess, summary = self._compute_excess_returns(df)

        fig = self._create_figure(cumulative_excess, summary)
        chart = self._create_chart(cumulative_excess)
        return AnalysisOutput(figure=fig, data=summary, chart=chart)

    def _compute_excess_returns(self, df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Compute daily excess returns and summary statistics versus benchmark."""
        prices = (
            df.assign(date=pd.to_datetime(df["date"]))
            .pivot_table(index="date", columns="symbol", values="close", aggfunc="last")
            .sort_index()
        )

        if self.benchmark_symbol not in prices.columns:
            raise ValueError(f"Benchmark symbol {self.benchmark_symbol} not found in bar data.")

        returns = prices.pct_change().dropna(how="all")
        if returns.empty:
            raise ValueError("Insufficient data to compute daily returns.")

        benchmark_returns = returns[self.benchmark_symbol]
        excess_returns = returns.sub(benchmark_returns, axis=0)
        excess_returns = excess_returns.drop(columns=[self.benchmark_symbol], errors="ignore")

        if excess_returns.empty:
            raise ValueError(f"No symbols available besides benchmark {self.benchmark_symbol}.")

        cumulative_excess = (excess_returns.cumsum() * 100).reset_index()
        cumulative_excess["date"] = cumulative_excess["date"].dt.strftime("%Y-%m-%d")

        annualized_excess_return = excess_returns.mean() * 252 * 100
        tracking_error = excess_returns.std(ddof=0) * np.sqrt(252) * 100
        information_ratio = annualized_excess_return / tracking_error.replace(0, np.nan)

        summary = pd.DataFrame(
            {
                "symbol": excess_returns.columns,
                "mean_daily_excess_bps": excess_returns.mean().values * 10000,
                "annualized_excess_return_pct": annualized_excess_return.values,
                "tracking_error_pct": tracking_error.values,
                "information_ratio": information_ratio.values,
                "final_cumulative_excess_return_pct": excess_returns.cumsum().iloc[-1].values * 100,
                "observations": excess_returns.count().values,
            }
        )

        summary = summary.round(
            {
                "mean_daily_excess_bps": 3,
                "annualized_excess_return_pct": 2,
                "tracking_error_pct": 2,
                "information_ratio": 3,
                "final_cumulative_excess_return_pct": 2,
            }
        )

        summary = summary.sort_values("annualized_excess_return_pct", ascending=False).reset_index(drop=True)
        return cumulative_excess, summary

    def _create_figure(self, cumulative_excess: pd.DataFrame, summary: pd.DataFrame) -> plt.Figure:
        """Create cumulative excess-return lines plus annualized ranking bars."""
        fig, axes = plt.subplots(1, 2, figsize=(15, 6))

        left_ax = axes[0]
        for symbol in [c for c in cumulative_excess.columns if c != "date"]:
            left_ax.plot(cumulative_excess["date"], cumulative_excess[symbol], linewidth=1.2, label=symbol)

        left_ax.axhline(0, color="gray", linewidth=0.7)
        left_ax.set_title(f"Cumulative Excess Return vs {self.benchmark_symbol}")
        left_ax.set_xlabel("Date")
        left_ax.set_ylabel("Excess Return (percentage points)")
        left_ax.tick_params(axis="x", rotation=45)
        left_ax.grid(True, alpha=0.3)
        left_ax.legend(fontsize=8)

        right_ax = axes[1]
        ranked = summary.sort_values("annualized_excess_return_pct", ascending=True)
        colors = ["#d62728" if v < 0 else "#2ca02c" for v in ranked["annualized_excess_return_pct"]]
        right_ax.barh(ranked["symbol"], ranked["annualized_excess_return_pct"], color=colors)
        right_ax.axvline(0, color="gray", linewidth=0.7)
        right_ax.set_title(f"Annualized Excess Return vs {self.benchmark_symbol}")
        right_ax.set_xlabel("Annualized Excess Return (%)")

        fig.suptitle("Alpaca Excess Returns Relative to SPY", fontsize=14, fontweight="bold")
        plt.tight_layout()
        return fig

    def _create_chart(self, cumulative_excess: pd.DataFrame) -> ChartConfig:
        """Create line chart payload for cumulative excess-return series."""
        y_keys = [c for c in cumulative_excess.columns if c != "date"]
        chart_data = cumulative_excess.to_dict("records")

        return ChartConfig(
            type=ChartType.LINE,
            data=chart_data,
            xKey="date",
            yKeys=y_keys,
            yUnit=UnitType.PERCENT,
            title=f"Cumulative Excess Returns vs {self.benchmark_symbol}",
            xLabel="Date",
            yLabel="Excess Return (percentage points)",
        )
