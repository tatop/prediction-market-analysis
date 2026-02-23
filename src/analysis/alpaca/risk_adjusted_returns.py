"""Risk-adjusted return analysis (Sharpe & Sortino ratios) across Alpaca symbols."""

from __future__ import annotations

from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.common.analysis import Analysis, AnalysisOutput
from src.common.interfaces.chart import ChartConfig, ChartType

ROLLING_WINDOW = 63  # ~3 months of trading days
ANNUALIZATION_FACTOR = 252
RISK_FREE_RATE = 0.0  # daily; adjust if needed
SUMMARY_COLUMNS = [
    "symbol",
    "annualized_sharpe",
    "annualized_sortino",
    "mean_daily_return_pct",
    "daily_volatility_pct",
    "downside_volatility_pct",
    "trading_days",
]


class AlpacaRiskAdjustedReturnsAnalysis(Analysis):
    """Compute rolling and cumulative Sharpe & Sortino ratios, ranked across symbols."""

    def __init__(self, bars_dir: Path | str | None = None):
        super().__init__(
            name="alpaca_risk_adjusted_returns",
            description="Rolling and cumulative Sharpe & Sortino ratios ranked across Alpaca symbols",
        )
        base_dir = Path(__file__).parent.parent.parent.parent
        self.bars_dir = Path(bars_dir or base_dir / "data" / "alpaca" / "bars")

    def run(self) -> AnalysisOutput:
        con = duckdb.connect()

        with self.progress("Loading Alpaca bar data"):
            df = con.execute(
                f"""
                SELECT symbol, timestamp, close
                FROM '{self.bars_dir}/*.parquet'
                ORDER BY symbol, timestamp
                """
            ).df()

        if df.empty:
            raise FileNotFoundError(f"No bar data found in {self.bars_dir}. Run the alpaca_bars indexer first.")

        summary = self._compute_summary(df)
        rolling = self._compute_rolling(df)
        fig = self._create_figure(rolling, summary)
        chart = self._create_chart(summary)

        return AnalysisOutput(figure=fig, data=summary, chart=chart)

    def _compute_summary(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute per-symbol annualized Sharpe and Sortino ratios."""
        records = []
        for symbol, group in df.groupby("symbol"):
            group = group.sort_values("timestamp")
            daily_returns = group["close"].pct_change().dropna()

            if len(daily_returns) < 2:
                continue

            excess = daily_returns - RISK_FREE_RATE
            mean_excess = excess.mean()
            std = excess.std()

            downside = excess[excess < 0]
            downside_std = np.sqrt((downside**2).mean()) if len(downside) > 0 else 0.0

            sharpe = (mean_excess / std * np.sqrt(ANNUALIZATION_FACTOR)) if std > 0 else 0.0
            sortino = (mean_excess / downside_std * np.sqrt(ANNUALIZATION_FACTOR)) if downside_std > 0 else 0.0

            records.append(
                {
                    "symbol": symbol,
                    "annualized_sharpe": round(sharpe, 3),
                    "annualized_sortino": round(sortino, 3),
                    "mean_daily_return_pct": round(float(mean_excess) * 100, 4),
                    "daily_volatility_pct": round(float(std) * 100, 4),
                    "downside_volatility_pct": round(float(downside_std) * 100, 4),
                    "trading_days": len(daily_returns),
                }
            )

        if not records:
            return pd.DataFrame(columns=SUMMARY_COLUMNS)

        return pd.DataFrame(records, columns=SUMMARY_COLUMNS).sort_values(
            "annualized_sharpe", ascending=False
        ).reset_index(drop=True)

    def _compute_rolling(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute rolling Sharpe and Sortino over a fixed window per symbol."""
        frames = []
        for symbol, group in df.groupby("symbol"):
            group = group.sort_values("timestamp").copy()
            daily_returns = group["close"].pct_change()
            excess = daily_returns - RISK_FREE_RATE

            roll_mean = excess.rolling(ROLLING_WINDOW).mean()
            roll_std = excess.rolling(ROLLING_WINDOW).std()

            downside_sq = excess.clip(upper=0) ** 2
            roll_downside_std = downside_sq.rolling(ROLLING_WINDOW).mean().apply(np.sqrt)

            rolling = pd.DataFrame(
                {
                    "symbol": symbol,
                    "timestamp": group["timestamp"],
                    "rolling_sharpe": (roll_mean / roll_std * np.sqrt(ANNUALIZATION_FACTOR)),
                    "rolling_sortino": (roll_mean / roll_downside_std * np.sqrt(ANNUALIZATION_FACTOR)),
                }
            )
            frames.append(rolling.dropna())

        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def _create_figure(self, rolling: pd.DataFrame, summary: pd.DataFrame) -> plt.Figure:
        """Create a 2x2 panel: rolling Sharpe, rolling Sortino, bar comparison, scatter."""
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        colors = plt.cm.tab10.colors

        # Panel 1: Rolling Sharpe
        ax = axes[0, 0]
        for i, (symbol, group) in enumerate(rolling.groupby("symbol")):
            ax.plot(group["timestamp"], group["rolling_sharpe"], label=symbol, color=colors[i % len(colors)])
        ax.axhline(0, color="gray", linewidth=0.5)
        ax.set_ylabel("Sharpe Ratio")
        ax.set_title(f"Rolling Sharpe ({ROLLING_WINDOW}d)")
        if not rolling.empty:
            ax.legend(fontsize=7)
        ax.grid(True, alpha=0.3)

        # Panel 2: Rolling Sortino
        ax = axes[0, 1]
        for i, (symbol, group) in enumerate(rolling.groupby("symbol")):
            ax.plot(group["timestamp"], group["rolling_sortino"], label=symbol, color=colors[i % len(colors)])
        ax.axhline(0, color="gray", linewidth=0.5)
        ax.set_ylabel("Sortino Ratio")
        ax.set_title(f"Rolling Sortino ({ROLLING_WINDOW}d)")
        if not rolling.empty:
            ax.legend(fontsize=7)
        ax.grid(True, alpha=0.3)

        # Panel 3: Annualized Sharpe vs Sortino bar chart
        ax = axes[1, 0]
        x = range(len(summary))
        width = 0.35
        ax.bar([i - width / 2 for i in x], summary["annualized_sharpe"], width, label="Sharpe", color="#4C72B0")
        ax.bar([i + width / 2 for i in x], summary["annualized_sortino"], width, label="Sortino", color="#2ecc71")
        ax.set_xticks(list(x))
        ax.set_xticklabels(summary["symbol"])
        ax.set_ylabel("Ratio")
        ax.set_title("Annualized Sharpe vs Sortino")
        ax.axhline(0, color="gray", linewidth=0.5)
        ax.legend()
        ax.grid(True, alpha=0.3, axis="y")

        # Panel 4: Return vs Downside vol scatter
        ax = axes[1, 1]
        for i, (_, row) in enumerate(summary.iterrows()):
            color = colors[i % len(colors)]
            ax.scatter(row["downside_volatility_pct"], row["mean_daily_return_pct"], color=color, s=80, zorder=3)
            ax.annotate(
                row["symbol"],
                (row["downside_volatility_pct"], row["mean_daily_return_pct"]),
                fontsize=8,
                ha="left",
                va="bottom",
                xytext=(4, 4),
                textcoords="offset points",
            )
        ax.set_xlabel("Downside Volatility (%)")
        ax.set_ylabel("Mean Daily Return (%)")
        ax.set_title("Return vs Downside Risk")
        ax.axhline(0, color="gray", linewidth=0.5)
        ax.grid(True, alpha=0.3)

        fig.suptitle("Alpaca Risk-Adjusted Returns", fontsize=14, fontweight="bold")
        plt.tight_layout()
        return fig

    def _create_chart(self, summary: pd.DataFrame) -> ChartConfig:
        """Create the chart configuration for web display."""
        chart_data = [
            {
                "symbol": row["symbol"],
                "annualized_sharpe": row["annualized_sharpe"],
                "annualized_sortino": row["annualized_sortino"],
            }
            for _, row in summary.iterrows()
        ]

        return ChartConfig(
            type=ChartType.BAR,
            data=chart_data,
            xKey="symbol",
            yKeys=["annualized_sharpe", "annualized_sortino"],
            title="Risk-Adjusted Returns by Symbol",
            xLabel="Symbol",
            yLabel="Ratio",
        )
