"""Ichimoku Cloud."""

from __future__ import annotations

import pandas as pd

from ._utils import require


DESCRIPTION = "Ichimoku Cloud — conversion, base, span A/B, lagging."
PARAMS = {"tenkan": 9, "kijun": 26, "senkou_b": 52}


def compute(
    df: pd.DataFrame,
    tenkan: int = 9,
    kijun: int = 26,
    senkou_b: int = 52,
) -> pd.DataFrame:
    require(df, ["high", "low", "close"], "Ichimoku")
    h, l_ = df["high"], df["low"]
    conv = (h.rolling(tenkan).max() + l_.rolling(tenkan).min()) / 2
    base = (h.rolling(kijun).max() + l_.rolling(kijun).min()) / 2
    span_a = ((conv + base) / 2).shift(kijun)
    span_b = ((h.rolling(senkou_b).max() + l_.rolling(senkou_b).min()) / 2).shift(
        kijun
    )
    lagging = df["close"].shift(-kijun)
    return pd.DataFrame(
        {
            "conversion": conv,
            "base": base,
            "span_a": span_a,
            "span_b": span_b,
            "lagging": lagging,
        },
        index=df.index,
    )
