"""StratForge dataset loader — THE ONLY data source for StratForge AI.

Reads uploaded parquet files that the user ingested through the desktop
app's sidebar (CSV / XLSX normalized to parquet under
``<workspace>/<project_id>/data/<dataset_id>.parquet``).

Usage in config.json:

    {
        "source": "stratforge",
        "codes":  ["ds_abcdef123456"],   # dataset_id from StratForge
        "start_date": "2020-01-01",
        "end_date":   "2025-12-31",
        "interval":   "1D"
    }

Each dataset_id becomes a symbol. Loader opens the parquet, canonicalizes
column names to OHLCV, filters by date, and returns a DataFrame with a
DatetimeIndex — the shape every backtest engine expects.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from app.backtest_engine.loaders.base import validate_date_range
from app.backtest_engine.loaders.registry import register

logger = logging.getLogger(__name__)


# Column name aliases — cover plain lowercase, MT4/MT5 bracketed, Yahoo-style headers.
_COL_ALIASES = {
    "open":   {"open", "o", "<open>", "opening_price", "price_open"},
    "high":   {"high", "h", "<high>", "highest", "price_high"},
    "low":    {"low", "l", "<low>", "lowest", "price_low"},
    "close":  {"close", "c", "<close>", "closing_price", "price_close", "last"},
    "volume": {"volume", "vol", "<vol>", "<tickvol>", "tick_volume", "qty"},
}

_DATE_ALIASES = {"date", "datetime", "timestamp", "time", "<date>", "trade_date"}


def _canonicalize(df: pd.DataFrame) -> pd.DataFrame:
    """Rename columns to lowercase OHLCV + promote date-like column to index."""
    lower = {str(c).strip().lower(): c for c in df.columns}

    # Promote date column to index (if there's an obvious one)
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
        try:
            df.index = pd.to_datetime(df.index, errors="coerce")
            df = df[df.index.notna()].sort_index()
        except Exception:
            pass

    # Rename OHLCV columns to canonical lowercase
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

    # Ensure volume exists even if source didn't carry it
    if "volume" not in df.columns:
        df["volume"] = 0.0

    return df


def _find_dataset_parquet(dataset_id: str) -> Path | None:
    """Resolve ``dataset_id`` to its parquet path on disk.

    Uses StratForge's storage module as the source of truth. Falls back to
    a filesystem walk if the storage module isn't importable (e.g. loader
    invoked directly without the FastAPI stack).
    """
    # Primary path — StratForge's storage registry
    try:
        from app import storage as _storage
        found = _storage._find_dataset_project(dataset_id)
        if found is not None:
            project_id, _row = found
            return _storage.dataset_path(project_id, dataset_id)
    except Exception as exc:  # noqa: BLE001
        logger.debug("StratForge storage lookup failed: %s", exc)

    # Fallback — walk the workspace layout by convention
    search_roots = [
        Path.home() / ".stratforge",
        Path.cwd(),
        Path(__file__).resolve().parents[4],  # project root when running from backend/app/...
    ]
    for root in search_roots:
        if not root.exists():
            continue
        for candidate in root.rglob(f"{dataset_id}.parquet"):
            return candidate
    return None


@register
class StratForgeLoader:
    """THE loader for StratForge AI. Reads uploaded parquet datasets."""

    name = "stratforge"
    markets = {
        "forex", "crypto", "us_equity", "a_share", "hk_equity",
        "futures", "commodities", "macro", "fund",
    }
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
        """Load each dataset_id from disk and return {symbol: DataFrame}."""
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

            # Filter to requested date range (inclusive)
            if isinstance(df.index, pd.DatetimeIndex):
                try:
                    df = df.loc[pd.Timestamp(start_date):pd.Timestamp(end_date)]
                except Exception:
                    pass

            keep = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
            if not keep:
                logger.warning("Dataset %s has no OHLCV columns after canonicalization", code)
                continue
            df = df[keep].dropna(subset=[c for c in ("open", "close") if c in keep])

            if not df.empty:
                out[code] = df

        return out
