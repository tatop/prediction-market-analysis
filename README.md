# Prediction Market Analysis

A framework for indexing and analyzing prediction market data (Kalshi, Polymarket) plus market benchmark data from Alpaca (OHLCV bars). It provides data collection tools, Parquet-based storage, and analysis scripts that generate figures and statistics.

## Overview

This project enables research and analysis by providing:
- Pre-collected datasets for Kalshi and Polymarket
- Data collection indexers for Kalshi, Polymarket, and Alpaca
- Analysis scripts for platform-specific and cross-symbol metrics

Currently supported features:
- Kalshi market metadata + trade history indexing
- Polymarket market metadata + CTF and legacy FPMM trade indexing
- Alpaca OHLCV bar indexing for configurable stock/ETF symbols
- Parquet-based storage with resumable collection flows
- Extensible analysis framework with PNG/PDF/CSV/JSON outputs

## Installation & Usage

Requires Python 3.9+. Install dependencies with [uv](https://github.com/astral-sh/uv):

```bash
uv sync
```

### Environment Variables

Create a `.env` file for API-backed indexers:

```env
POLYGON_RPC=
POLYMARKET_START_BLOCK=33605403
ALPACA_API_KEY=
ALPACA_SECRET_KEY=
```

- `POLYGON_RPC` is needed for Polymarket blockchain indexers.
- `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` are needed for the Alpaca bars indexer.

### Download Pre-Collected Dataset

Download and extract the pre-collected dataset (Kalshi + Polymarket):

```bash
make setup
```

This downloads `data.tar.zst` from [Cloudflare R2 Storage](https://s3.jbecker.dev/data.tar.zst) and extracts it to `data/`.

## Data Collection

Collect data from APIs/blockchain sources:

```bash
make index
```

This opens an interactive menu to select an indexer (including `alpaca_bars`).

Data is saved under:
- `data/kalshi/`
- `data/polymarket/`
- `data/alpaca/bars/`

For Alpaca bars, files are partitioned by symbol and timeframe (e.g. `SPY_1Day.parquet`).
By default, bars are fetched with Alpaca `split` adjustment so historical prices remain consistent across stock splits.

## Running Analyses

```bash
make analyze
```

This opens an interactive menu to select analyses. Outputs (PNG, PDF, CSV, JSON, GIF when applicable) are saved to `output/`.

The Alpaca analyses currently included are:
- `alpaca_bar_metrics` (cumulative return, annualized volatility, volume, and return-vs-volatility comparison by symbol)
- `alpaca_drawdown_metrics` (max drawdown, drawdown duration, and recovery time per symbol)
- `alpaca_return_correlation_matrix` (pairwise correlation matrix of daily returns across symbols)

You can also run one analysis directly:

```bash
uv run main.py analyze alpaca_bar_metrics
```

## Packaging Data

To compress the data directory for storage/distribution:

```bash
make package
```

This creates a zstd-compressed tar archive (`data.tar.zst`) and removes the `data/` directory.

## Project Structure

```
├── src/
│   ├── analysis/
│   │   ├── alpaca/         # Alpaca analyses (e.g., bar metrics)
│   │   ├── kalshi/         # Kalshi analyses
│   │   ├── polymarket/     # Polymarket analyses
│   │   └── comparison/     # Cross-platform analyses
│   ├── indexers/
│   │   ├── alpaca/         # Alpaca bars client + indexer
│   │   ├── kalshi/         # Kalshi API client + indexers
│   │   └── polymarket/     # Polymarket API/blockchain indexers
│   └── common/             # Shared utilities and interfaces
├── data/
│   ├── alpaca/
│   │   └── bars/
│   ├── kalshi/
│   │   ├── markets/
│   │   └── trades/
│   └── polymarket/
│       ├── blocks/
│       ├── markets/
│       └── trades/
├── docs/                   # Documentation
└── output/                 # Analysis outputs
```

## Documentation

- [Data Schemas](docs/SCHEMAS.md) - Parquet schemas for Kalshi and Polymarket datasets
- [Writing Analyses](docs/ANALYSIS.md) - Guide for writing custom analysis scripts

## Contributing

If you'd like to contribute to this project, please open a pull-request with your changes, as well as detailed information on what is changed, added, or improved.

For more information, see the [contributing guide](CONTRIBUTING.md).

## Issues

If you've found an issue or have a question, please open an issue [here](https://github.com/jon-becker/prediction-market-analysis/issues).

## Research & Citations

- Becker, J. (2026). _The Microstructure of Wealth Transfer in Prediction Markets_. Jbecker. https://jbecker.dev/research/prediction-market-microstructure
- Le, N. A. (2026). _Decomposing Crowd Wisdom: Domain-Specific Calibration Dynamics in Prediction Markets_. arXiv. https://arxiv.org/abs/2602.19520

If you have used or plan to use this dataset in your research, please reach out via [email](mailto:jonathan@jbecker.dev) or [Twitter](https://x.com/BeckerrJon) -- I'd love to hear about what you're using the data for! Additionally, feel free to open a PR and update this section with a link to your paper.
