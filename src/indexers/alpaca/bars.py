"""Indexer for Alpaca OHLCV bar data."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from src.common.indexer import Indexer
from src.indexers.alpaca.client import AlpacaClient

DATA_DIR = Path("data/alpaca/bars")

DEFAULT_SYMBOLS = ["SPY", "QQQ", "IWM", "DIA", "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA"]
DEFAULT_TIMEFRAME = "1Day"
DEFAULT_START = datetime(2020, 1, 1)


class AlpacaBarsIndexer(Indexer):
    """Fetches and stores OHLCV bar data from Alpaca Markets."""

    def __init__(
        self,
        symbols: Optional[list[str]] = None,
        timeframe: str = DEFAULT_TIMEFRAME,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ):
        super().__init__(
            name="alpaca_bars",
            description="Fetches OHLCV bar data from Alpaca Markets to parquet files",
        )
        self._symbols = symbols or DEFAULT_SYMBOLS
        self._timeframe = timeframe
        self._start = start or DEFAULT_START
        self._end = end

    def run(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)

        client = AlpacaClient()
        total = 0

        for chunk in client.iter_bars(
            symbols=self._symbols,
            timeframe=self._timeframe,
            start=self._start,
            end=self._end,
        ):
            records = []
            fetched_at = datetime.utcnow()
            for bar in chunk:
                record = asdict(bar)
                record["timeframe"] = self._timeframe
                record["_fetched_at"] = fetched_at
                records.append(record)

            df = pd.DataFrame(records)
            total += len(df)

            # Partition by symbol for efficient querying
            for symbol, group in df.groupby("symbol"):
                path = DATA_DIR / f"{symbol}_{self._timeframe}.parquet"
                if path.exists():
                    existing = pd.read_parquet(path)
                    combined = pd.concat([existing, group], ignore_index=True)
                    combined.drop_duplicates(subset=["symbol", "timestamp", "timeframe"], keep="last", inplace=True)
                    combined.sort_values("timestamp", inplace=True)
                    combined.to_parquet(path, index=False)
                else:
                    group.sort_values("timestamp", inplace=True)
                    group.to_parquet(path, index=False)

            symbols_in_chunk = df["symbol"].nunique()
            print(f"Stored {len(df)} bars across {symbols_in_chunk} symbols (total: {total})")

        print(f"\nIndexing complete: {total} bars fetched for {len(self._symbols)} symbols")
