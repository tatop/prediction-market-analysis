from __future__ import annotations

import pandas as pd
import pytest

from src.analysis.alpaca.excess_returns_vs_spy import AlpacaExcessReturnsVsSpyAnalysis
from src.analysis.alpaca.return_correlation_matrix import AlpacaReturnCorrelationMatrixAnalysis
from src.analysis.alpaca.risk_adjusted_returns import AlpacaRiskAdjustedReturnsAnalysis
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


def test_excess_returns_vs_spy_computes_expected_cumulative_values() -> None:
    analysis = AlpacaExcessReturnsVsSpyAnalysis()
    df = pd.DataFrame(
        [
            {"symbol": "SPY", "date": "2024-01-01", "close": 100.0},
            {"symbol": "SPY", "date": "2024-01-02", "close": 102.0},
            {"symbol": "SPY", "date": "2024-01-03", "close": 101.0},
            {"symbol": "QQQ", "date": "2024-01-01", "close": 100.0},
            {"symbol": "QQQ", "date": "2024-01-02", "close": 103.0},
            {"symbol": "QQQ", "date": "2024-01-03", "close": 104.0},
            {"symbol": "IWM", "date": "2024-01-01", "close": 100.0},
            {"symbol": "IWM", "date": "2024-01-02", "close": 99.0},
            {"symbol": "IWM", "date": "2024-01-03", "close": 101.0},
        ]
    )

    cumulative, summary = analysis._compute_excess_returns(df)

    assert list(cumulative.columns) == ["date", "IWM", "QQQ"]
    assert cumulative["date"].tolist() == ["2024-01-02", "2024-01-03"]
    assert cumulative["QQQ"].iloc[-1] == pytest.approx(2.95, abs=0.01)
    assert cumulative["IWM"].iloc[-1] == pytest.approx(0.00, abs=0.01)
    assert set(summary["symbol"]) == {"QQQ", "IWM"}


def test_excess_returns_vs_spy_requires_spy_series() -> None:
    analysis = AlpacaExcessReturnsVsSpyAnalysis()
    df = pd.DataFrame(
        [
            {"symbol": "QQQ", "date": "2024-01-01", "close": 100.0},
            {"symbol": "QQQ", "date": "2024-01-02", "close": 103.0},
        ]
    )

    with pytest.raises(ValueError, match="Benchmark symbol SPY not found"):
        analysis._compute_excess_returns(df)


def test_risk_adjusted_returns_handles_symbols_with_too_few_rows() -> None:
    analysis = AlpacaRiskAdjustedReturnsAnalysis()
    df = pd.DataFrame(
        [
            {"symbol": "SPY", "timestamp": "2024-01-01", "close": 100.0},
            {"symbol": "SPY", "timestamp": "2024-01-02", "close": 101.0},
            {"symbol": "QQQ", "timestamp": "2024-01-01", "close": 200.0},
            {"symbol": "IWM", "timestamp": "2024-01-01", "close": 50.0},
            {"symbol": "IWM", "timestamp": "2024-01-02", "close": 49.0},
        ]
    )

    summary = analysis._compute_summary(df)

    assert summary.empty
    assert list(summary.columns) == [
        "symbol",
        "annualized_sharpe",
        "annualized_sortino",
        "mean_daily_return_pct",
        "daily_volatility_pct",
        "downside_volatility_pct",
        "trading_days",
    ]
