# Writing Analysis Scripts

Analysis scripts live in:
- `src/analysis/alpaca/`
- `src/analysis/kalshi/`
- `src/analysis/polymarket/`
- `src/analysis/comparison/`

All analyses should extend `Analysis` and return `AnalysisOutput`.

## Running Analyses

Interactive menu:

```bash
make analyze
```

Run one analysis directly:

```bash
uv run main.py analyze <analysis_name>
```

Run all analyses:

```bash
uv run main.py analyze all
```

Outputs are saved in `output/`.

## Alpaca Quickstart

```bash
# 1) Install deps
uv sync

# 2) Ensure .env has ALPACA_API_KEY and ALPACA_SECRET_KEY

# 3) Index bars (interactive menu -> select alpaca_bars)
make index

# 4) Run Alpaca analysis
uv run main.py analyze alpaca_bar_metrics
# or: make analyze (then pick alpaca_bar_metrics)
```

Alpaca bars are written to `data/alpaca/bars/`, and analysis outputs are written to `output/`.

## Basic Template

```python
"""Brief description of what this analysis does."""

from __future__ import annotations

from pathlib import Path

import duckdb
import matplotlib.pyplot as plt

from src.common.analysis import Analysis, AnalysisOutput
from src.common.interfaces.chart import ChartConfig, ChartType


class MyAnalysis(Analysis):
    """Example analysis."""

    def __init__(self, trades_dir: Path | str | None = None):
        super().__init__(
            name="my_analysis",
            description="Brief description of what this analysis does",
        )
        base_dir = Path(__file__).parent.parent.parent.parent
        self.trades_dir = Path(trades_dir or base_dir / "data" / "kalshi" / "trades")

    def run(self) -> AnalysisOutput:
        con = duckdb.connect()

        with self.progress("Loading data"):
            df = con.execute(
                f"""
                SELECT yes_price, count
                FROM '{self.trades_dir}/*.parquet'
                WHERE yes_price BETWEEN 1 AND 99
                """
            ).df()

        fig, ax = plt.subplots(figsize=(10, 6))
        ax.hist(df["yes_price"], bins=20)
        ax.set_title("My Analysis")
        ax.set_xlabel("Price")
        ax.set_ylabel("Frequency")
        plt.tight_layout()

        chart = ChartConfig(
            type=ChartType.BAR,
            data=df.head(100).to_dict("records"),
            xKey="yes_price",
            yKeys=["count"],
            title="My Analysis",
        )

        return AnalysisOutput(
            figure=fig,
            data=df,
            chart=chart,
        )
```

## Alpaca Query Pattern (OHLCV bars)

```sql
SELECT
    symbol,
    timestamp,
    open,
    high,
    low,
    close,
    volume,
    vwap
FROM 'data/alpaca/bars/*.parquet'
ORDER BY symbol, timestamp
```

Common derived metrics:
- Cumulative return: `(last_close / first_close - 1) * 100`
- Daily return series: `close.pct_change()`
- Annualized volatility: `std(daily_returns) * sqrt(252)`

## Kalshi Query Patterns

### Join trades with market outcomes

```sql
WITH resolved_markets AS (
    SELECT ticker, result
    FROM 'data/kalshi/markets/*.parquet'
    WHERE status = 'finalized'
      AND result IN ('yes', 'no')
)
SELECT
    t.yes_price,
    t.count,
    t.taker_side,
    m.result,
    CASE WHEN t.taker_side = m.result THEN 1 ELSE 0 END AS taker_won
FROM 'data/kalshi/trades/*.parquet' t
INNER JOIN resolved_markets m ON t.ticker = m.ticker
```

### Analyze both taker and maker positions

```sql
WITH all_positions AS (
    -- Taker positions
    SELECT
        CASE WHEN taker_side = 'yes' THEN yes_price ELSE no_price END AS price,
        count,
        'taker' AS role
    FROM 'data/kalshi/trades/*.parquet'

    UNION ALL

    -- Maker positions (counterparty)
    SELECT
        CASE WHEN taker_side = 'yes' THEN no_price ELSE yes_price END AS price,
        count,
        'maker' AS role
    FROM 'data/kalshi/trades/*.parquet'
)
SELECT price, role, SUM(count) AS total_contracts
FROM all_positions
GROUP BY price, role
ORDER BY price
```

## Polymarket Query Pattern

```sql
SELECT
    block_number,
    maker_asset_id,
    taker_asset_id,
    maker_amount,
    taker_amount
FROM 'data/polymarket/trades/*.parquet'
```

Tip: join against `data/polymarket/blocks/*.parquet` for time-based aggregations.

## Using the Categories Utility (Kalshi)

For grouping markets into high-level categories:

```python
from src.analysis.kalshi.util.categories import get_group, get_hierarchy, GROUP_COLORS

group = get_group("NFLGAME")
hierarchy = get_hierarchy("NFLGAME")
color = GROUP_COLORS["Sports"]
```

## Progress Indicator

Use `self.progress()` for expensive loading/compute steps:

```python
with self.progress("Loading trades data"):
    df = con.execute("SELECT * FROM ...").df()

with self.progress("Computing aggregates"):
    result = df.groupby(...).agg(...)
```

## Output Conventions

`Analysis.save()` supports:
- Figure: `png`, `pdf`, `svg`, `gif` (animated only)
- Data: `csv`
- Web chart config: `json`

Default save path is `output/` with filename `<analysis_name>.<ext>`.

## Dependencies

Analyses can use these project dependencies:
- `duckdb`
- `pandas`
- `matplotlib`
- `scipy`
- `brokenaxes`
- `squarify`
