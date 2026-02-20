"""Rolling momentum analysis across Alpaca symbols."""

from __future__ import annotations

from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import pandas as pd

from src.common.analysis import Analysis, AnalysisOutput
from src.common.interfaces.chart import ChartConfig, ChartType, UnitType

MOMENTUM_WINDOWS = {"1W": 5, "1M": 21, "3M": 63}


class AlpacaMomentumAnalysis(Analysis):
    """Compute rolling momentum (returns over 1W, 1M, 3M) and rank symbols."""

    def __init__(self, bars_dir: Path | str | None = None):
        super().__init__(
            name="alpaca_momentum",
            description="Rolling momentum returns (1W, 1M, 3M) ranked across Alpaca symbols",
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

        momentum_ts = self._compute_rolling_momentum(df)
        snapshot = self._latest_snapshot(momentum_ts)
        fig = self._create_figure(momentum_ts, snapshot)
        chart = self._create_chart(snapshot)

        return AnalysisOutput(figure=fig, data=snapshot, chart=chart)

    def _compute_rolling_momentum(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute rolling return for each window per symbol."""
        frames = []
        for symbol, group in df.groupby("symbol"):
            group = group.sort_values("timestamp").set_index("timestamp")
            close = group["close"]
            row = pd.DataFrame({"symbol": symbol, "close": close})
            for label, days in MOMENTUM_WINDOWS.items():
                row[f"mom_{label}"] = close.pct_change(periods=days) * 100
            frames.append(row)
        return pd.concat(frames).reset_index()

    def _latest_snapshot(self, momentum_ts: pd.DataFrame) -> pd.DataFrame:
        """Get the most recent momentum values per symbol, plus rank."""
        latest = momentum_ts.dropna(subset=[f"mom_{label}" for label in MOMENTUM_WINDOWS])
        latest = latest.sort_values("timestamp").groupby("symbol").tail(1)

        cols = ["symbol"] + [f"mom_{label}" for label in MOMENTUM_WINDOWS]
        snapshot = latest[cols].copy().reset_index(drop=True)

        # Composite score: average of z-scores across windows
        for label in MOMENTUM_WINDOWS:
            col = f"mom_{label}"
            mean = snapshot[col].mean()
            std = snapshot[col].std()
            snapshot[f"z_{label}"] = (snapshot[col] - mean) / std if std > 0 else 0.0

        z_cols = [f"z_{label}" for label in MOMENTUM_WINDOWS]
        snapshot["composite_score"] = snapshot[z_cols].mean(axis=1).round(2)
        snapshot["rank"] = snapshot["composite_score"].rank(ascending=False).astype(int)
        snapshot = snapshot.drop(columns=z_cols)

        # Round momentum columns
        for label in MOMENTUM_WINDOWS:
            snapshot[f"mom_{label}"] = snapshot[f"mom_{label}"].round(2)

        return snapshot.sort_values("rank").reset_index(drop=True)

    def _create_figure(self, momentum_ts: pd.DataFrame, snapshot: pd.DataFrame) -> plt.Figure:
        """Create a 2x2 panel: 3 rolling momentum time-series + ranked bar chart."""
        fig, axes = plt.subplots(2, 2, figsize=(16, 11))
        colors = plt.cm.tab10.colors

        all_symbols = sorted(momentum_ts["symbol"].unique())
        symbol_colors = {sym: colors[i % len(colors)] for i, sym in enumerate(all_symbols)}

        # Panels 0-2: rolling momentum time-series per window
        for idx, (label, _) in enumerate(MOMENTUM_WINDOWS.items()):
            ax = axes[idx // 2, idx % 2]
            col = f"mom_{label}"
            for symbol, group in momentum_ts.groupby("symbol"):
                g = group.dropna(subset=[col]).sort_values("timestamp")
                ax.plot(g["timestamp"], g[col], label=symbol, color=symbol_colors[symbol], linewidth=0.8)
            ax.axhline(0, color="gray", linewidth=0.5)
            ax.set_title(f"{label} Rolling Return")
            ax.set_ylabel("Return (%)")
            ax.legend(fontsize=6, ncol=2, loc="upper left")
            ax.grid(True, alpha=0.3)

        # Panel 3: latest composite momentum ranking
        ax = axes[1, 1]
        sorted_snap = snapshot.sort_values("composite_score", ascending=True)
        bar_colors = ["#e74c3c" if v < 0 else "#2ecc71" for v in sorted_snap["composite_score"]]
        ax.barh(sorted_snap["symbol"], sorted_snap["composite_score"], color=bar_colors)
        ax.set_xlabel("Composite Momentum Score (avg z-score)")
        ax.set_title("Current Momentum Ranking")
        ax.axvline(0, color="gray", linewidth=0.5)

        fig.suptitle("Alpaca Momentum Analysis", fontsize=14, fontweight="bold")
        plt.tight_layout()
        return fig

    def _create_chart(self, snapshot: pd.DataFrame) -> ChartConfig:
        """Create chart config for web display."""
        chart_data = [
            {
                "symbol": row["symbol"],
                "mom_1W": row["mom_1W"],
                "mom_1M": row["mom_1M"],
                "mom_3M": row["mom_3M"],
                "composite_score": row["composite_score"],
            }
            for _, row in snapshot.iterrows()
        ]

        return ChartConfig(
            type=ChartType.BAR,
            data=chart_data,
            xKey="symbol",
            yKeys=["mom_1W", "mom_1M", "mom_3M"],
            title="Momentum by Symbol (Rolling Returns %)",
            xLabel="Symbol",
            yLabel="Return (%)",
            yUnit=UnitType.PERCENT,
        )
