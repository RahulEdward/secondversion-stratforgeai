"""Percentage Price Oscillator."""

from __future__ import annotations

import pandas as pd


DESCRIPTION = "Percentage Price Oscillator (MACD as percent)."
PARAMS = {"fast": 12, "slow": 26, "signal": 9, "column": "close"}


def compute(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9, column: str = "close") -> pd.DataFrame:
    s = df[column].astype(float)
    f = s.ewm(span=fast, adjust=False).mean()
    sl = s.ewm(span=slow, adjust=False).mean()
    line = 100 * (f - sl) / sl
    sig = line.ewm(span=signal, adjust=False).mean()
    return pd.DataFrame({"ppo": line, "signal": sig, "hist": line - sig}, index=df.index)
