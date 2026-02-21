from __future__ import annotations

import pandas as pd

from src.analysis.alpaca.return_correlation_matrix import AlpacaReturnCorrelationMatrixAnalysis
from src.indexers.alpaca.bars import DEFAULT_SYMBOLS


def test_default_alpaca_symbols_include_spy_and_qqq() -> None:
    assert "SPY" in DEFAULT_SYMBOLS
    assert "QQQ" in DEFAULT_SYMBOLS


def test_return_correlation_heatmap_uses_value_key() -> None:
    analysis = AlpacaReturnCorrelationMatrixAnalysis()
    corr_long = pd.DataFrame(
        [
            {"symbol_x": "SPY", "symbol_y": "SPY", "correlation": 1.0},
            {"symbol_x": "SPY", "symbol_y": "QQQ", "correlation": 0.9},
        ]
    )

    chart_dict = analysis._create_chart(corr_long).to_dict()

    assert chart_dict["type"] == "heatmap"
    assert chart_dict["valueKey"] == "value"
    assert "zKey" not in chart_dict
