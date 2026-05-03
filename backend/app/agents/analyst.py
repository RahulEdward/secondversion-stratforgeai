"""DataAnalyst agent — profiles a dataset via direct indicator computation.

No LLM call needed: we load the parquet once, compute 5-6 indicators in-
process, and return a :class:`DataProfile` with regime / trend / volatility
classification.  This runs in ~200 ms — much faster than an LLM round-trip.
"""

from __future__ import annotations

import asyncio
import math
from typing import Optional

import numpy as np
import pandas as pd

from .base import DataProfile


class DataAnalyst:
    """Compute key indicators and classify the dataset regime."""

    async def analyze(self, dataset_id: str) -> DataProfile:
        """Load dataset, compute indicators, return profile."""
        return await asyncio.to_thread(self._analyze_sync, dataset_id)

    # ------------------------------------------------------------------ #

    def _analyze_sync(self, dataset_id: str) -> DataProfile:
        from ..data import load_dataset
        from .. import storage
        from ..indicators import compute as compute_indicator

        # Resolve dataset path
        found = storage._find_dataset_project(dataset_id)
        if found is None:
            raise ValueError(f"Dataset {dataset_id} not found")
        project_id, _ = found
        path = storage.dataset_path(project_id, dataset_id)
        if not path.exists():
            raise FileNotFoundError(f"Dataset parquet missing: {path}")

        df = load_dataset(path)
        if "time" in df.columns:
            df = df.set_index(pd.to_datetime(df["time"]))
        profile = DataProfile()
        profile.n_bars = len(df)

        # Date range
        if isinstance(df.index, pd.DatetimeIndex) and len(df) > 0:
            profile.date_range = (
                f"{df.index[0].strftime('%Y-%m-%d %H:%M')} → "
                f"{df.index[-1].strftime('%Y-%m-%d %H:%M')}"
            )

        # Latest close
        if "close" in df.columns:
            profile.latest_close = float(df["close"].iloc[-1])

        # RSI(14)
        try:
            rsi_df = compute_indicator(df, "rsi", {"period": 14})
            rsi_vals = rsi_df.iloc[:, 0].dropna()
            if len(rsi_vals) > 0:
                profile.latest_rsi = float(rsi_vals.iloc[-1])
        except Exception:
            pass

        # ATR(14)
        try:
            atr_df = compute_indicator(df, "atr", {"period": 14})
            atr_vals = atr_df.iloc[:, 0].dropna()
            if len(atr_vals) > 0:
                profile.avg_atr = float(atr_vals.tail(50).mean())
                if profile.latest_close > 0:
                    profile.atr_pct = (profile.avg_atr / profile.latest_close) * 100
        except Exception:
            pass

        # ADX(14)
        try:
            adx_df = compute_indicator(df, "adx", {"period": 14})
            adx_col = [c for c in adx_df.columns if "adx" in c.lower()]
            if adx_col:
                adx_vals = adx_df[adx_col[0]].dropna()
                if len(adx_vals) > 0:
                    profile.avg_adx = float(adx_vals.tail(50).mean())
        except Exception:
            pass

        # Bollinger Bands(20, 2)
        try:
            bb_df = compute_indicator(df, "bollinger_bands", {"period": 20, "std_dev": 2.0})
            upper_col = [c for c in bb_df.columns if "upper" in c.lower()]
            lower_col = [c for c in bb_df.columns if "lower" in c.lower()]
            if upper_col and lower_col:
                upper = bb_df[upper_col[0]].dropna()
                lower = bb_df[lower_col[0]].dropna()
                if len(upper) > 0 and profile.latest_close > 0:
                    width = float((upper.tail(50) - lower.tail(50)).mean())
                    profile.bb_width_pct = (width / profile.latest_close) * 100
        except Exception:
            pass

        # EMA(50) and EMA(200)
        try:
            ema50_df = compute_indicator(df, "ema", {"period": 50})
            ema50_vals = ema50_df.iloc[:, 0].dropna()
            if len(ema50_vals) > 0:
                profile.ema50 = float(ema50_vals.iloc[-1])
        except Exception:
            pass

        try:
            ema200_df = compute_indicator(df, "ema", {"period": 200})
            ema200_vals = ema200_df.iloc[:, 0].dropna()
            if len(ema200_vals) > 0:
                profile.ema200 = float(ema200_vals.iloc[-1])
        except Exception:
            pass

        # Classify regime
        profile.regime = self._classify_regime(profile)
        profile.trend_direction = self._classify_trend(profile)
        return profile

    # ------------------------------------------------------------------ #

    @staticmethod
    def _classify_regime(p: DataProfile) -> str:
        """Trending / ranging / volatile based on ADX + BB width."""
        if p.avg_adx >= 25:
            return "trending"
        if p.bb_width_pct > 3.0:
            return "volatile"
        return "ranging"

    @staticmethod
    def _classify_trend(p: DataProfile) -> str:
        """Bullish / bearish / neutral from price vs EMAs."""
        if p.latest_close <= 0:
            return "neutral"
        above_50 = p.latest_close > p.ema50 if p.ema50 > 0 else False
        above_200 = p.latest_close > p.ema200 if p.ema200 > 0 else False
        if above_50 and above_200:
            return "bullish"
        if not above_50 and not above_200:
            return "bearish"
        return "neutral"
