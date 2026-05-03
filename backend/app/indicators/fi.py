"""Force Index."""

from __future__ import annotations

import pandas as pd

from ._utils import require


DESCRIPTION = "Force Index — (Δclose × volume) EMA."
PARAMS = {"period": 13}


def compute(df: pd.DataFrame, period: int = 13) -> pd.Series:
    """Force Index."""
    require(df, ["close", "volume"], "fi")
    return (df["close"].astype(float).diff() * df["volume"].astype(float)).ewm(span=period, adjust=False).mean().rename(f"fi_{period}")
