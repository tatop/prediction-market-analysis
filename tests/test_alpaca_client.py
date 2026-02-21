from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest
from alpaca.data.enums import Adjustment

from src.indexers.alpaca.client import AlpacaClient


def test_get_bars_defaults_to_split_adjustment() -> None:
    captured_request = None

    class FakeStockClient:
        def get_stock_bars(self, request):
            nonlocal captured_request
            captured_request = request
            return SimpleNamespace(data={})

    client = AlpacaClient.__new__(AlpacaClient)
    client.client = FakeStockClient()

    bars = client.get_bars(symbols=["AAPL"], timeframe="1Day", start=datetime(2024, 1, 1))

    assert bars == []
    assert captured_request is not None
    assert captured_request.adjustment == Adjustment.SPLIT


def test_normalize_adjustment_accepts_string_values() -> None:
    assert AlpacaClient._normalize_adjustment("split") == Adjustment.SPLIT
    assert AlpacaClient._normalize_adjustment("ALL") == Adjustment.ALL


def test_normalize_adjustment_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="Unknown adjustment"):
        AlpacaClient._normalize_adjustment("bogus")
