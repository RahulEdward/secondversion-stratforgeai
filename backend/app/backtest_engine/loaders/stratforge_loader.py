"""StratForge dataset loader — reads uploaded parquet files.

This loader lets Vibe-Trading's backtest engines consume datasets that the
StratForge user uploaded through the desktop app's sidebar (CSV / XLSX
normalized to parquet under ``<workspace>/data/<dataset_id>.parquet``).

Usage in config.json:

    {
        "source": "stratforge",
        "codes":  ["ds_abcdef123456"],   # dataset_id(s) from StratForge
        "start_date": "2020-01-01",
        "end_date":   "2025-12-31",
        "interval":   "1D"
    }

The loader treats each dataset_id as a symbol, loads its parquet, filters
by date range, and returns the DataFrame in the OHLCV format every engine
expects (open/high/low/close/volume with DatetimeIndex).
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from app.backtest_engine.loaders.base import DataLoaderProtocol, validate_date_range
from app.backtest_engine.loaders.registry import register

logger = logging.getLogger(__name__)


# Canonical column aliases — handle the various header shapes StratForge
# ingests (plain lowercase, MT4/MT5 bracketed, Yahoo-style, etc.).
_COL_ALIASES = {
    "open":   {"open", "o", "<open>", "opening_price", "price_open"},
    "high":   {"high", "h", "<high>", "highest", "price_high"},
    "low":    {"low", "l", "<low>", "lowest", "price_low"},
    "close":  {"close", "c", "<close>", "closing_price", "price_close", "last"},
    "volume": {"volume", "vol", "<vol>", "<tickvol>", "tick_volume", "qty"},
}

_DATE_ALIASES = {
    "date", "datetime", "timestamp", "time", "<date>", "trade_date",
}


def _canonicalize(df: pd.DataFrame) -> pd.DataFrame:
    """Rename columns to lowercase OHLCV + promote date-like col to index."""
    lower = {str(c).strip().lower(): c for c in df.columns}

    # Date → index
    date_col = None
    for alias in _DATE_ALIASES:
        if alias in lower:
            date_col = lower[alias]
            break

    if date_col is not None and date_col in df.columns:
        df = df.copy()
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        df = df.dropna(subset=[date_col])
        df = df.set_index(date_col).sort_index()
    elif not isinstance(df.index, pd.DatetimeIndex):
        # Fall back: try to coerce existing index
        try:
            df.index = pd.to_datetime(df.index, errors="coerce")
            df = df[df.index.notna()].sort_index()
        except Exception:
            pass

    # Rename OHLCV columns
    renames: dict[str, str] = {}
    for canonical, aliases in _COL_ALIASES.items():
        for alias in aliases:
            if alias in lower:
                src = lower[alias]
                if src != canonical:
                    renames[src] = canonical
                break

    if renames:
        df = df.rename(columns=renames)

    # Ensure volume column exists even if the dataset didn't carry it
    if "volume" not in df.columns:
        df["volume"] = 0.0

    return df


def _find_dataset_parquet(dataset_id: str) -> Path | None:
    """Locate the parquet file for a dataset_id across all projects.

    StratForge stores datasets under ``<workspace>/<project_id>/data/<dataset_id>.parquet``.
    We import the app's storage module lazily so this loader still works if
    someone consumes ``backtest`` directly without the FastAPI layer.
    """
    try:
        # Prefer StratForge's authoritative lookup when available.
        from app import storage as _storage
        ds = _storage.get_dataset(dataset_id)
        if ds is None:
            return None
        # get_dataset() returns a row; reconstruct the path.
        project_id = _storage._find_dataset_project(dataset_id)
        if project_id is None:
            return None
        return _storage.dataset_path(project_id[0], dataset_id)
    except Exception:
        # Best-effort fallback: walk the usual workspace layout.
        from pathlib import Path as _Path
        candidates = list(_Path.home().glob(f".stratforge/**/data/{dataset_id}.parquet"))
        candidates += list(_Path("D:/startfoge-ai-main").glob(f"**/data/{dataset_id}.parquet"))
        return candidates[0] if candidates else None


@register
class StratForgeLoader:
    """Reads OHLCV from StratForge's uploaded-parquet workspace."""

    name = "stratforge"
    markets = {"forex", "crypto", "us_equity", "a_share", "hk_equity", "futures", "commodities"}
    requires_auth = False

    def is_available(self) -> bool:  # pragma: no cover — always local
        return True

    def fetch(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
        *,
        interval: str = "1D",
        fields: list[str] | None = None,
    ) -> dict[str, pd.DataFrame]:
        """Load each ``dataset_id`` from disk and return an OHLCV frame per symbol."""
        if not codes:
            return {}
        validate_date_range(start_date, end_date)

        out: dict[str, pd.DataFrame] = {}
        for code in codes:
            path = _find_dataset_parquet(code)
            if path is None or not path.exists():
                logger.warning("StratForge dataset %s not found on disk", code)
                continue
            try:
                df = pd.read_parquet(path)
            except Exception as exc:
                logger.warning("Failed to read %s: %s", path, exc)
                continue

            df = _canonicalize(df)

            # Date-range filter — keep inclusive endpoints
            if isinstance(df.index, pd.DatetimeIndex):
                try:
                    df = df.loc[pd.Timestamp(start_date):pd.Timestamp(end_date)]
                except Exception:
                    pass

            # Keep only the columns engines need
            keep = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
            if not keep:
                logger.warning("Dataset %s has no OHLCV columns", code)
                continue
            df = df[keep].dropna(subset=[c for c in ("open", "close") if c in keep])

            if not df.empty:
                out[code] = df

        return out
