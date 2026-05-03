"""MACD — Moving Average Convergence Divergence."""

from __future__ import annotations

import pandas as pd

from ._utils import require


DESCRIPTION = "MACD line, signal line, and histogram."
PARAMS = {"fast": 12, "slow": 26, "signal": 9, "column": "close"}


def compute(
    df: pd.DataFrame,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
    column: str = "close",
) -> pd.DataFrame:
    require(df, [column], "MACD")
    fast_ema = df[column].ewm(span=fast, adjust=False).mean()
    slow_ema = df[column].ewm(span=slow, adjust=False).mean()
    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return pd.DataFrame(
        {"macd": macd_line, "signal": signal_line, "hist": hist}, index=df.index
    )
