"""Pairwise return correlation matrix for Alpaca symbols."""

from __future__ import annotations

from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.common.analysis import Analysis, AnalysisOutput
from src.common.interfaces.chart import ChartConfig, ChartType


class AlpacaReturnCorrelationMatrixAnalysis(Analysis):
    """Compute and visualize pairwise daily-return correlations across symbols."""

    def __init__(self, bars_dir: Path | str | None = None):
        super().__init__(
            name="alpaca_return_correlation_matrix",
            description="Computes pairwise correlations of daily returns across symbols",
        )
        base_dir = Path(__file__).parent.parent.parent.parent
        self.bars_dir = Path(bars_dir or base_dir / "data" / "alpaca" / "bars")

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

        with self.progress("Computing return correlations"):
            corr_matrix = self._compute_correlation_matrix(df)

        fig = self._create_heatmap(corr_matrix)
        corr_long = self._flatten_matrix(corr_matrix)
        chart = self._create_chart(corr_long)
        return AnalysisOutput(figure=fig, data=corr_long, chart=chart)

    def _compute_correlation_matrix(self, df: pd.DataFrame) -> pd.DataFrame:
        """Build symbol-by-symbol correlation matrix from daily returns."""
        prices = (
            df.assign(date=pd.to_datetime(df["date"]))
            .pivot_table(index="date", columns="symbol", values="close", aggfunc="last")
            .sort_index()
        )

        returns = prices.pct_change().dropna(how="all")
        if returns.empty:
            raise ValueError("Insufficient data to compute daily returns.")

        return returns.corr(method="pearson")

    def _create_heatmap(self, corr_matrix: pd.DataFrame) -> plt.Figure:
        """Plot correlation matrix as a heatmap with value annotations."""
        symbols = corr_matrix.columns.tolist()
        values = corr_matrix.values

        fig, ax = plt.subplots(figsize=(8, 7))
        im = ax.imshow(values, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")

        ax.set_xticks(np.arange(len(symbols)))
        ax.set_yticks(np.arange(len(symbols)))
        ax.set_xticklabels(symbols, rotation=45, ha="right")
        ax.set_yticklabels(symbols)
        ax.set_title("Daily Return Correlation Matrix")

        for i in range(values.shape[0]):
            for j in range(values.shape[1]):
                text_color = "white" if abs(values[i, j]) > 0.5 else "black"
                ax.text(j, i, f"{values[i, j]:.2f}", ha="center", va="center", color=text_color, fontsize=8)

        cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cbar.set_label("Correlation")

        fig.suptitle("Alpaca Symbol Correlation", fontsize=14, fontweight="bold")
        plt.tight_layout()
        return fig

    def _flatten_matrix(self, corr_matrix: pd.DataFrame) -> pd.DataFrame:
        """Convert a square correlation matrix into long-form rows."""
        rows = []
        for symbol_x in corr_matrix.index:
            for symbol_y in corr_matrix.columns:
                rows.append(
                    {
                        "symbol_x": symbol_x,
                        "symbol_y": symbol_y,
                        "correlation": round(float(corr_matrix.loc[symbol_x, symbol_y]), 6),
                    }
                )
        return pd.DataFrame(rows)

    def _create_chart(self, corr_long: pd.DataFrame) -> ChartConfig:
        """Create heatmap chart payload for frontend consumers."""
        chart_data = [
            {
                "x": row["symbol_x"],
                "y": row["symbol_y"],
                "value": row["correlation"],
            }
            for _, row in corr_long.iterrows()
        ]

        return ChartConfig(
            type=ChartType.HEATMAP,
            data=chart_data,
            xKey="x",
            yKey="y",
            valueKey="value",
            title="Daily Return Correlation Matrix",
            xLabel="Symbol",
            yLabel="Symbol",
        )
