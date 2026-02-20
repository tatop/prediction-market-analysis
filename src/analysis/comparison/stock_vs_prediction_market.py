"""Correlation between stock market moves and prediction market activity."""

from __future__ import annotations

from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.common.analysis import Analysis, AnalysisOutput
from src.common.interfaces.chart import ChartConfig, ChartType

ROLLING_WINDOW = 30
BLOCK_BUCKET_SIZE = 10800


class StockVsPredictionMarketAnalysis(Analysis):
    """Correlate daily SPY/QQQ returns with Kalshi & Polymarket trading activity."""

    def __init__(
        self,
        bars_dir: Path | str | None = None,
        kalshi_trades_dir: Path | str | None = None,
        polymarket_trades_dir: Path | str | None = None,
        polymarket_legacy_trades_dir: Path | str | None = None,
        polymarket_blocks_dir: Path | str | None = None,
    ):
        super().__init__(
            name="stock_vs_prediction_market",
            description="Correlates stock returns (SPY/QQQ) with prediction market trading volume",
        )
        base_dir = Path(__file__).parent.parent.parent.parent
        self.bars_dir = Path(bars_dir or base_dir / "data" / "alpaca" / "bars")
        self.kalshi_trades_dir = Path(kalshi_trades_dir or base_dir / "data" / "kalshi" / "trades")
        self.polymarket_trades_dir = Path(polymarket_trades_dir or base_dir / "data" / "polymarket" / "trades")
        self.polymarket_legacy_trades_dir = Path(
            polymarket_legacy_trades_dir or base_dir / "data" / "polymarket" / "legacy_trades"
        )
        self.polymarket_blocks_dir = Path(polymarket_blocks_dir or base_dir / "data" / "polymarket" / "blocks")

    def run(self) -> AnalysisOutput:
        con = duckdb.connect()

        with self.progress("Loading Alpaca stock data"):
            stocks = self._load_stock_returns(con)

        with self.progress("Loading prediction market volume"):
            pm_volume = self._load_prediction_market_volume(con)

        if stocks.empty:
            raise FileNotFoundError(f"No bar data found in {self.bars_dir}. Run the alpaca_bars indexer first.")

        if pm_volume.empty:
            raise FileNotFoundError(
                "No prediction market trade data found. Run the kalshi_trades or polymarket indexers first."
            )

        with self.progress("Computing correlations"):
            merged = self._merge_and_correlate(stocks, pm_volume)

        fig = self._create_figure(merged)
        chart = self._create_chart(merged)

        return AnalysisOutput(figure=fig, data=merged, chart=chart)

    def _load_stock_returns(self, con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
        """Load daily returns for SPY and QQQ from Alpaca bars."""
        spy_path = self.bars_dir / "SPY_1Day.parquet"
        qqq_path = self.bars_dir / "QQQ_1Day.parquet"

        parts = []
        for path, symbol in [(spy_path, "SPY"), (qqq_path, "QQQ")]:
            if not path.exists():
                continue
            df = con.execute(
                f"""
                SELECT
                    timestamp::DATE AS date,
                    close
                FROM '{path}'
                ORDER BY timestamp
                """
            ).df()
            df["daily_return"] = df["close"].pct_change() * 100
            df["abs_return"] = df["daily_return"].abs()
            df = df.dropna(subset=["daily_return"])
            df["symbol"] = symbol
            parts.append(df[["date", "symbol", "daily_return", "abs_return"]])

        if not parts:
            return pd.DataFrame()

        result = pd.concat(parts, ignore_index=True)
        result["date"] = pd.to_datetime(result["date"])
        return result

    def _load_prediction_market_volume(self, con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
        """Load daily trade volume from Kalshi and Polymarket."""
        parts = []

        # Kalshi
        if self.kalshi_trades_dir.exists() and any(self.kalshi_trades_dir.glob("*.parquet")):
            kalshi = con.execute(
                f"""
                SELECT
                    created_time::DATE AS date,
                    SUM(count) AS trade_volume,
                    COUNT(*) AS trade_count
                FROM '{self.kalshi_trades_dir}/*.parquet'
                GROUP BY date
                ORDER BY date
                """
            ).df()
            kalshi["platform"] = "kalshi"
            kalshi["date"] = pd.to_datetime(kalshi["date"])
            parts.append(kalshi)

        # Polymarket CTF trades (need block → timestamp mapping)
        if (
            self.polymarket_trades_dir.exists()
            and any(self.polymarket_trades_dir.glob("*.parquet"))
            and self.polymarket_blocks_dir.exists()
            and any(self.polymarket_blocks_dir.glob("*.parquet"))
        ):
            con.execute(
                f"""
                CREATE OR REPLACE TABLE pm_blocks AS
                SELECT
                    block_number // {BLOCK_BUCKET_SIZE} AS bucket,
                    FIRST(timestamp::TIMESTAMP) AS timestamp
                FROM '{self.polymarket_blocks_dir}/*.parquet'
                GROUP BY bucket
                """
            )

            poly_query = f"""
                SELECT
                    b.timestamp::DATE AS date,
                    COUNT(*) AS trade_count,
                    SUM(
                        CASE
                            WHEN t.maker_asset_id = '0' THEN t.taker_amount
                            WHEN t.taker_asset_id = '0' THEN t.maker_amount
                            ELSE 0
                        END
                    ) / 1e6 AS trade_volume
                FROM '{self.polymarket_trades_dir}/*.parquet' t
                JOIN pm_blocks b ON t.block_number // {BLOCK_BUCKET_SIZE} = b.bucket
                WHERE t.maker_asset_id = '0' OR t.taker_asset_id = '0'
                GROUP BY date
                ORDER BY date
            """

            # Add legacy trades if available
            if self.polymarket_legacy_trades_dir.exists() and any(
                self.polymarket_legacy_trades_dir.glob("*.parquet")
            ):
                poly_query = f"""
                    WITH all_trades AS (
                        SELECT
                            b.timestamp::DATE AS date,
                            CASE
                                WHEN t.maker_asset_id = '0' THEN t.taker_amount
                                WHEN t.taker_asset_id = '0' THEN t.maker_amount
                                ELSE 0
                            END / 1e6 AS trade_volume
                        FROM '{self.polymarket_trades_dir}/*.parquet' t
                        JOIN pm_blocks b ON t.block_number // {BLOCK_BUCKET_SIZE} = b.bucket
                        WHERE t.maker_asset_id = '0' OR t.taker_asset_id = '0'

                        UNION ALL

                        SELECT
                            b.timestamp::DATE AS date,
                            t.amount::DOUBLE / 1e6 AS trade_volume
                        FROM '{self.polymarket_legacy_trades_dir}/*.parquet' t
                        JOIN pm_blocks b ON t.block_number // {BLOCK_BUCKET_SIZE} = b.bucket
                    )
                    SELECT date, COUNT(*) AS trade_count, SUM(trade_volume) AS trade_volume
                    FROM all_trades
                    GROUP BY date
                    ORDER BY date
                """

            poly = con.execute(poly_query).df()
            poly["platform"] = "polymarket"
            poly["date"] = pd.to_datetime(poly["date"])
            parts.append(poly)

        if not parts:
            return pd.DataFrame()

        return pd.concat(parts, ignore_index=True)

    def _merge_and_correlate(self, stocks: pd.DataFrame, pm_volume: pd.DataFrame) -> pd.DataFrame:
        """Merge stock returns with prediction market volume and compute rolling correlation."""
        # Pivot stock returns: one column per symbol
        spy = stocks[stocks["symbol"] == "SPY"][["date", "daily_return", "abs_return"]].rename(
            columns={"daily_return": "spy_return", "abs_return": "spy_abs_return"}
        )

        # Aggregate prediction market volume across platforms
        pm_daily = pm_volume.groupby("date").agg(
            pm_trade_count=("trade_count", "sum"),
            pm_trade_volume=("trade_volume", "sum"),
        ).reset_index()

        # Merge on date
        merged = spy.merge(pm_daily, on="date", how="inner").sort_values("date").reset_index(drop=True)

        if len(merged) < ROLLING_WINDOW:
            merged["rolling_corr_return"] = np.nan
            merged["rolling_corr_abs_return"] = np.nan
        else:
            # Rolling correlation: SPY return vs PM volume
            merged["rolling_corr_return"] = (
                merged["spy_return"]
                .rolling(ROLLING_WINDOW)
                .corr(merged["pm_trade_volume"])
            )
            # Rolling correlation: SPY absolute return (volatility) vs PM volume
            merged["rolling_corr_abs_return"] = (
                merged["spy_abs_return"]
                .rolling(ROLLING_WINDOW)
                .corr(merged["pm_trade_volume"])
            )

        # Add per-platform columns for the output
        for platform in pm_volume["platform"].unique():
            platform_data = pm_volume[pm_volume["platform"] == platform][["date", "trade_volume"]].rename(
                columns={"trade_volume": f"{platform}_volume"}
            )
            merged = merged.merge(platform_data, on="date", how="left")

        return merged

    def _create_figure(self, merged: pd.DataFrame) -> plt.Figure:
        """Create a 2x2 panel: time-series, scatter, rolling correlation, volume comparison."""
        fig, axes = plt.subplots(2, 2, figsize=(16, 11))

        # Panel 1: Dual-axis time-series (SPY return + PM volume)
        ax1 = axes[0, 0]
        ax1.plot(merged["date"], merged["spy_return"], color="#3B82F6", linewidth=0.5, alpha=0.6, label="SPY Return")
        ax1.set_ylabel("SPY Daily Return (%)", color="#3B82F6")
        ax1.axhline(0, color="gray", linewidth=0.5)
        ax1.tick_params(axis="y", labelcolor="#3B82F6")
        ax1.set_title("SPY Returns vs Prediction Market Volume")

        ax1_twin = ax1.twinx()
        ax1_twin.fill_between(
            merged["date"], merged["pm_trade_volume"], alpha=0.3, color="#10B981", label="PM Volume"
        )
        ax1_twin.set_ylabel("PM Trade Volume", color="#10B981")
        ax1_twin.tick_params(axis="y", labelcolor="#10B981")

        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax1_twin.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=7)

        # Panel 2: Scatter (absolute return vs PM volume)
        ax2 = axes[0, 1]
        ax2.scatter(merged["spy_abs_return"], merged["pm_trade_volume"], alpha=0.3, s=10, color="#8B5CF6")
        # Trend line
        mask = merged[["spy_abs_return", "pm_trade_volume"]].dropna().index
        if len(mask) > 10:
            x = merged.loc[mask, "spy_abs_return"]
            y = merged.loc[mask, "pm_trade_volume"]
            z = np.polyfit(x, y, 1)
            p = np.poly1d(z)
            x_sorted = np.sort(x)
            ax2.plot(x_sorted, p(x_sorted), color="#EF4444", linewidth=1.5, label=f"slope={z[0]:.0f}")
            corr = x.corr(y)
            ax2.set_title(f"|SPY Return| vs PM Volume (r={corr:.3f})")
            ax2.legend(fontsize=8)
        else:
            ax2.set_title("|SPY Return| vs PM Volume")
        ax2.set_xlabel("|SPY Daily Return| (%)")
        ax2.set_ylabel("PM Trade Volume")
        ax2.grid(True, alpha=0.3)

        # Panel 3: Rolling correlation
        ax3 = axes[1, 0]
        corr_return = merged.dropna(subset=["rolling_corr_return"])
        corr_abs = merged.dropna(subset=["rolling_corr_abs_return"])
        if not corr_return.empty:
            ax3.plot(
                corr_return["date"], corr_return["rolling_corr_return"],
                color="#3B82F6", linewidth=1, label="Return vs Volume",
            )
        if not corr_abs.empty:
            ax3.plot(
                corr_abs["date"], corr_abs["rolling_corr_abs_return"],
                color="#EF4444", linewidth=1, label="|Return| vs Volume",
            )
        ax3.axhline(0, color="gray", linewidth=0.5)
        ax3.set_ylabel("Correlation")
        ax3.set_title(f"{ROLLING_WINDOW}-Day Rolling Correlation")
        ax3.set_ylim(-1, 1)
        ax3.legend(fontsize=8)
        ax3.grid(True, alpha=0.3)

        # Panel 4: Per-platform volume breakdown (if multiple platforms)
        ax4 = axes[1, 1]
        platform_cols = [c for c in merged.columns if c.endswith("_volume") and c != "pm_trade_volume"]
        if platform_cols:
            for col in platform_cols:
                label = col.replace("_volume", "").title()
                rolling = merged.set_index("date")[col].rolling("30D").mean()
                ax4.plot(rolling.index, rolling.values, linewidth=1.2, label=f"{label} (30d avg)")
            ax4.set_ylabel("Trade Volume (30d rolling avg)")
            ax4.set_title("Platform Volume Over Time")
            ax4.legend(fontsize=8)
            ax4.grid(True, alpha=0.3)
        else:
            # Single platform — show volume distribution by SPY return buckets
            if not merged.empty:
                merged["return_bucket"] = pd.cut(merged["spy_return"], bins=10)
                bucket_vol = merged.groupby("return_bucket", observed=True)["pm_trade_volume"].mean().reset_index()
                bucket_vol["label"] = bucket_vol["return_bucket"].astype(str)
                ax4.bar(range(len(bucket_vol)), bucket_vol["pm_trade_volume"], color="#10B981")
                ax4.set_xticks(range(len(bucket_vol)))
                ax4.set_xticklabels(bucket_vol["label"], rotation=45, fontsize=6, ha="right")
                ax4.set_ylabel("Avg PM Volume")
                ax4.set_title("Avg PM Volume by SPY Return Bucket")

        fig.suptitle("Stock Market vs Prediction Market Correlation", fontsize=14, fontweight="bold")
        plt.tight_layout()
        return fig

    def _create_chart(self, merged: pd.DataFrame) -> ChartConfig:
        """Create chart config for web display."""
        # Sample to avoid massive JSON — take weekly averages
        weekly = merged.set_index("date").resample("W").agg({
            "spy_return": "mean",
            "spy_abs_return": "mean",
            "pm_trade_volume": "sum",
            "rolling_corr_abs_return": "last",
        }).dropna(subset=["spy_return"]).reset_index()

        chart_data = [
            {
                "date": row["date"].strftime("%Y-%m-%d"),
                "rolling_correlation": round(row["rolling_corr_abs_return"], 3)
                if pd.notna(row["rolling_corr_abs_return"]) else None,
            }
            for _, row in weekly.iterrows()
        ]

        return ChartConfig(
            type=ChartType.LINE,
            data=chart_data,
            xKey="date",
            yKeys=["rolling_correlation"],
            title=f"Stock Volatility vs PM Volume ({ROLLING_WINDOW}-Day Rolling Correlation)",
            xLabel="Date",
            yLabel="Correlation",
        )
