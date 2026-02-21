from __future__ import annotations

import os
from collections.abc import Generator
from datetime import datetime

from alpaca.data.enums import Adjustment
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from dotenv import load_dotenv

from src.indexers.alpaca.models import Bar

load_dotenv()

TIMEFRAME_MAP = {
    "1Min": TimeFrame(1, TimeFrameUnit.Minute),
    "5Min": TimeFrame(5, TimeFrameUnit.Minute),
    "15Min": TimeFrame(15, TimeFrameUnit.Minute),
    "30Min": TimeFrame(30, TimeFrameUnit.Minute),
    "1Hour": TimeFrame(1, TimeFrameUnit.Hour),
    "1Day": TimeFrame(1, TimeFrameUnit.Day),
    "1Week": TimeFrame(1, TimeFrameUnit.Week),
    "1Month": TimeFrame(1, TimeFrameUnit.Month),
}


class AlpacaClient:
    def __init__(
        self,
        api_key: str | None = None,
        secret_key: str | None = None,
    ):
        self.api_key = api_key or os.environ["ALPACA_API_KEY"]
        self.secret_key = secret_key or os.environ["ALPACA_SECRET_KEY"]
        self.client = StockHistoricalDataClient(self.api_key, self.secret_key)

    def get_bars(
        self,
        symbols: list[str],
        timeframe: str,
        start: datetime,
        end: datetime | None = None,
        adjustment: Adjustment | str = Adjustment.SPLIT,
    ) -> list[Bar]:
        """Fetch OHLCV bars for the given symbols and time range."""
        tf = TIMEFRAME_MAP.get(timeframe)
        if tf is None:
            raise ValueError(f"Unknown timeframe '{timeframe}'. Valid: {list(TIMEFRAME_MAP)}")

        normalized_adjustment = self._normalize_adjustment(adjustment)

        request = StockBarsRequest(
            symbol_or_symbols=symbols,
            timeframe=tf,
            start=start,
            end=end,
            adjustment=normalized_adjustment,
        )
        barset = self.client.get_stock_bars(request)

        bars: list[Bar] = []
        for symbol, symbol_bars in barset.data.items():
            for bar in symbol_bars:
                bars.append(Bar.from_alpaca(symbol, bar))
        return bars

    def iter_bars(
        self,
        symbols: list[str],
        timeframe: str,
        start: datetime,
        end: datetime | None = None,
        chunk_size: int = 10000,
        adjustment: Adjustment | str = Adjustment.SPLIT,
    ) -> Generator[list[Bar], None, None]:
        """Iterate bars in chunks using Alpaca's built-in pagination."""
        tf = TIMEFRAME_MAP.get(timeframe)
        if tf is None:
            raise ValueError(f"Unknown timeframe '{timeframe}'. Valid: {list(TIMEFRAME_MAP)}")

        normalized_adjustment = self._normalize_adjustment(adjustment)

        request = StockBarsRequest(
            symbol_or_symbols=symbols,
            timeframe=tf,
            start=start,
            end=end,
            limit=chunk_size,
            adjustment=normalized_adjustment,
        )
        barset = self.client.get_stock_bars(request)

        bars: list[Bar] = []
        for symbol, symbol_bars in barset.data.items():
            for bar in symbol_bars:
                bars.append(Bar.from_alpaca(symbol, bar))
                if len(bars) >= chunk_size:
                    yield bars
                    bars = []

        if bars:
            yield bars

    @staticmethod
    def _normalize_adjustment(adjustment: Adjustment | str) -> Adjustment:
        """Convert raw string config into an Alpaca adjustment enum value."""
        if isinstance(adjustment, Adjustment):
            return adjustment

        normalized = adjustment.strip().lower()
        for value in Adjustment:
            if value.value == normalized:
                return value

        valid_values = ", ".join(sorted(value.value for value in Adjustment))
        raise ValueError(f"Unknown adjustment '{adjustment}'. Valid: {valid_values}")
