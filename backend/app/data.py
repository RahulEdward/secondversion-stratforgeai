"""CSV / Excel ingestion + parquet storage for per-project datasets."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

# Canonical column name -> list of *normalized* aliases users typically use.
# Aliases are matched after stripping every non-alphanumeric character from
# the source header (so ``<OPEN>``, ``[Open]``, ``"Open"``, ``OPEN_PRICE``
# all collapse to the same key). The order within each list is the priority
# — the first alias that resolves wins.
OHLCV_ALIASES: Dict[str, List[str]] = {
    "time": ["time", "datetime", "timestamp", "ts"],
    "open": ["open", "o", "openprice"],
    "high": ["high", "h", "max"],
    "low": ["low", "l", "min"],
    # Real volume preferred over tick-count volume (MT4/MT5 export both).
    "volume": ["volume", "vol", "realvol", "v", "tickvol", "tickvolume"],
    "close": ["close", "c", "closeprice", "adjclose", "last"],
}


_NORM_STRIP = re.compile(r"[^a-z0-9]")


def _norm_header(name: object) -> str:
    """Lowercase + strip everything except alphanumerics.

    Handles MT4/MT5 ``<OPEN>``, Excel ``[Open]``, ``"Open Price"`` →
    ``open``, ``open``, ``openprice`` respectively.
    """
    return _NORM_STRIP.sub("", str(name).lower().strip())


class DataError(ValueError):
    """Raised when an uploaded dataset cannot be parsed or validated."""


def _read_any(path: Path) -> pd.DataFrame:
    """Load a CSV, TSV, or Excel file into a DataFrame with light heuristics."""
    suffix = path.suffix.lower()
    try:
        if suffix in {".xlsx", ".xls"}:
            return pd.read_excel(path)
        if suffix == ".tsv":
            return pd.read_csv(path, sep="\t")
        # Default: CSV — let pandas sniff the separator.
        return pd.read_csv(path, sep=None, engine="python")
    except Exception as exc:  # pandas raises many exception types
        raise DataError(f"Failed to parse file: {exc}") from exc


def _canonicalize_columns(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, str]]:
    """Rename columns to canonical OHLCV names where possible. Return (df, mapping).

    Two passes:

    1. **Date+time merge.** MetaTrader exports use separate ``<DATE>`` and
       ``<TIME>`` columns. If we detect both, concatenate them into a single
       ``time`` datetime column before alias matching.
    2. **Alias rename.** Match each canonical name against its alias list,
       comparing on the normalized form (lowercased + alphanumeric only) so
       angle-bracketed / wrapped headers resolve transparently.
    """
    mapping: Dict[str, str] = {}

    # Build {normalized_header → original_header}, keeping first occurrence.
    norm_to_original: Dict[str, str] = {}
    for col in df.columns:
        n = _norm_header(col)
        if n and n not in norm_to_original:
            norm_to_original[n] = col

    # ── Pass 1: merge separate date + time columns (MT4 / MT5 style) ──────
    has_date = "date" in norm_to_original
    has_time = "time" in norm_to_original
    if has_date and has_time:
        date_col = norm_to_original.pop("date")
        time_col = norm_to_original.pop("time")
        combined = pd.to_datetime(
            df[date_col].astype(str).str.strip()
            + " "
            + df[time_col].astype(str).str.strip(),
            errors="coerce",
        )
        df = df.drop(columns=[date_col, time_col])
        df["time"] = combined
        norm_to_original["time"] = "time"
        mapping[f"{date_col}+{time_col}"] = "time"
    elif has_date and not has_time:
        # Only a date column — promote it to the canonical ``time``.
        date_col = norm_to_original.pop("date")
        norm_to_original["time"] = date_col
        mapping[date_col] = "time"

    # ── Pass 2: alias-match remaining canonicals ──────────────────────────
    rename: Dict[str, str] = {}
    used_originals: set[str] = set()
    for canon, aliases in OHLCV_ALIASES.items():
        if canon in df.columns:
            continue
        for alias in aliases:
            original = norm_to_original.get(alias)
            if original is None or original in used_originals:
                continue
            if original != canon:
                rename[original] = canon
                mapping[original] = canon
            used_originals.add(original)
            break

    if rename:
        df = df.rename(columns=rename)
    return df, mapping


def _parse_time_column(df: pd.DataFrame) -> pd.DataFrame:
    """If a 'time' column exists, parse it to datetime and sort ascending."""
    if "time" not in df.columns:
        return df
    parsed = pd.to_datetime(df["time"], errors="coerce", utc=False)
    # Drop rows where time couldn't be parsed.
    mask = parsed.notna()
    df = df.loc[mask].copy()
    df["time"] = parsed.loc[mask]
    df = df.sort_values("time").reset_index(drop=True)
    return df


def _has_ohlcv(df: pd.DataFrame) -> bool:
    required = {"open", "high", "low", "close"}
    return required.issubset(set(df.columns))


def ingest_dataset(
    source_path: Path,
    dest_path: Path,
) -> Dict[str, object]:
    """Parse a user-uploaded file, canonicalize columns, store as parquet.

    Returns a metadata dict (columns, row count, date range, ohlcv flag, size).
    Raises DataError on failure.
    """
    df = _read_any(source_path)
    if df.empty:
        raise DataError("File is empty")
    if len(df) < 2:
        raise DataError("File must have at least 2 rows")

    # Drop fully-empty columns (common in exported CSVs).
    df = df.dropna(axis=1, how="all")

    df, _renamed = _canonicalize_columns(df)
    df = _parse_time_column(df)

    if df.empty:
        raise DataError("No parseable rows after cleaning")

    # Cast OHLCV numeric columns so downstream indicators are fast.
    for col in ("open", "high", "low", "close", "volume"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Drop rows where any present OHLC column is NaN (volume NaN is OK).
    ohlc_present = [c for c in ("open", "high", "low", "close") if c in df.columns]
    if ohlc_present:
        df = df.dropna(subset=ohlc_present).reset_index(drop=True)

    if df.empty:
        raise DataError("No valid numeric rows after cleaning")

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(dest_path, index=False)

    columns = list(df.columns)
    has_ohlcv = _has_ohlcv(df)

    start_date: Optional[str] = None
    end_date: Optional[str] = None
    if "time" in df.columns and not df["time"].isna().all():
        start_date = df["time"].iloc[0].isoformat()
        end_date = df["time"].iloc[-1].isoformat()

    return {
        "rows": int(len(df)),
        "columns": columns,
        "has_ohlcv": bool(has_ohlcv),
        "start_date": start_date,
        "end_date": end_date,
        "size_bytes": int(dest_path.stat().st_size),
    }


def load_dataset(path: Path) -> pd.DataFrame:
    """Load a stored parquet file and re-canonicalize its columns.

    Re-canonicalizing on load is idempotent for already-normalized files but
    transparently rescues older datasets that were ingested before MT4/MT5
    bracketed-header support landed (``<OPEN>`` etc.). Cost is a single
    dict lookup + optional rename — sub-millisecond on practical sizes.
    """
    df = pd.read_parquet(path)
    df, _ = _canonicalize_columns(df)
    return df


def _json_safe(value: object) -> object:
    """Convert pandas/numpy scalars into JSON-safe primitives."""
    if value is None:
        return None
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(value, (int, bool, str)):
        return value
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    # Fall back to string representation — safe default.
    try:
        if pd.isna(value):  # type: ignore[arg-type]
            return None
    except (TypeError, ValueError):
        pass
    return str(value)


def preview_dataset(path: Path, rows: int = 50) -> List[Dict[str, object]]:
    """Return the first N rows as a list of JSON-safe dicts."""
    df = load_dataset(path).head(rows)
    out: List[Dict[str, object]] = []
    for _, row in df.iterrows():
        out.append({col: _json_safe(row[col]) for col in df.columns})
    return out
