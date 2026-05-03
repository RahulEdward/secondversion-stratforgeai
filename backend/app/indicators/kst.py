"""Know Sure Thing."""

from __future__ import annotations

import pandas as pd


DESCRIPTION = "Know Sure Thing momentum + signal."
PARAMS = {"column": "close"}


def compute(df: pd.DataFrame, column: str = "close") -> pd.DataFrame:
    """Know Sure Thing."""
    s = df[column].astype(float)
    rocma = lambda r, m: s.pct_change(r).rolling(m).mean()
    line = (rocma(10, 10) * 1 + rocma(15, 10) * 2 + rocma(20, 10) * 3 + rocma(30, 15) * 4) * 100
    sig = line.rolling(9).mean()
    return pd.DataFrame({"kst": line, "signal": sig}, index=df.index)
