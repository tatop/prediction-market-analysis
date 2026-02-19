from dataclasses import dataclass
from datetime import datetime


@dataclass
class Bar:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    trade_count: int
    vwap: float

    @classmethod
    def from_alpaca(cls, symbol: str, bar) -> "Bar":
        """Create a Bar from an alpaca-py Bar object."""
        return cls(
            symbol=symbol,
            timestamp=bar.timestamp,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
            trade_count=bar.trade_count,
            vwap=bar.vwap,
        )
