"""Backtest runner (Phase 7, Slice 3).

Public API:
    run_backtest(dataset_id, spec, *, init_cash=10_000.0) -> BacktestResult

Pipeline:
    1. Load parquet for `dataset_id` (resolves project automatically).
    2. Compile entries / exits via `strategies.compile_signals`.
    3. Build sizing series (vol-targeted / kelly-fraction / fixed-pct).
    4. Translate `StopsConfig` into VectorBT-compatible stop arguments
       (percent, ATR-derived, trailing, time-bar).
    5. Run `vbt.Portfolio.from_signals(...)`.
    6. Compute production metrics (Sharpe, Sortino, Max DD, PF, win-rate,
       expectancy, CAGR) plus a Welch-style t-stat on per-trade returns for
       statistical significance.
    7. Persist a JSON summary + equity/trades parquet so Phase 8 reports and
       Phase 6 follow-up tools can re-load the result.

All metrics that VectorBT may emit as NaN/Inf (e.g. Sharpe with <2 trades) are
clipped to JSON-safe values in `_clean_metrics`.
"""

from __future__ import annotations

import json
import math
import secrets
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import vectorbt as vbt
from scipy import stats as _scstats

from . import data as _data
from . import indicators as ind
from . import storage
from .paths import workspace_dir
from .strategies import StopsConfig, StrategySpec, compile_signals, resolve_costs


# ─── Helpers ────────────────────────────────────────────────────────────


def _bt_id() -> str:
    return f"bt_{secrets.token_hex(8)}"


def _robust_freq(idx: pd.Index) -> Optional[Any]:
    """Best-effort frequency for a possibly-gappy DatetimeIndex.

    VectorBT requires a frequency for annualised metrics (Sharpe/CAGR/etc.).
    ``pd.infer_freq`` returns ``None`` whenever the index has any gap — this
    happens routinely with FX/equity OHLC data because of weekends, holidays,
    and session breaks. We fall back to the median bar-to-bar delta, which
    correctly yields ``5min`` for M5, ``1h`` for H1, etc.
    """
    if not isinstance(idx, pd.DatetimeIndex) or len(idx) < 2:
        return None
    inferred = pd.infer_freq(idx)
    if inferred is not None:
        return inferred
    deltas = idx.to_series().diff().dropna()
    if deltas.empty:
        return None
    median = deltas.median()
    # vectorbt accepts a Timedelta directly; passing ``str(median)`` would
    # fail for non-canonical strings on some pandas versions.
    return median if pd.notna(median) and median > pd.Timedelta(0) else None


def _backtests_dir(project_id: str) -> Path:
    p = workspace_dir(project_id) / "backtests"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _bars_per_year(index: pd.DatetimeIndex) -> float:
    """Estimate bars/year for annualisation. Falls back to 252 if irregular."""
    if len(index) < 3:
        return 252.0
    diffs = pd.Series(index).diff().dropna().dt.total_seconds()
    if diffs.empty or diffs.median() <= 0:
        return 252.0
    median_sec = float(diffs.median())
    sec_per_year = 365.25 * 24 * 3600
    return sec_per_year / median_sec


def _clean(v: Any) -> Any:
    """Coerce numpy/pandas scalars, drop NaN/Inf, round floats to 2 dp."""
    if v is None:
        return None
    if isinstance(v, (np.floating, float)):
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
        return round(f, 2)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, pd.Timestamp):
        return v.isoformat()
    return v


def _clean_metrics(m: Dict[str, Any]) -> Dict[str, Any]:
    return {k: _clean(v) for k, v in m.items()}


# ─── Sizing builders ────────────────────────────────────────────────────


def _build_size_series(
    df: pd.DataFrame,
    spec: StrategySpec,
) -> Tuple[pd.Series, str]:
    """Return a per-bar position-fraction series in [0, 1] suitable for VBT
    `size=...` with `size_type='percent'`. Also returns a textual note about
    the sizing actually applied (since some types degrade in v1)."""

    n = len(df)
    idx = df.index
    sizing = spec.sizing
    cap = float(sizing.max_position)

    if sizing.type == "fixed_pct":
        s = pd.Series(min(float(sizing.value), cap), index=idx)
        return s, f"fixed_pct={float(sizing.value)}, max_position={cap}"

    if sizing.type == "vol_target":
        # Annualised realised vol over a 20-bar window; size = target / vol.
        # Shift by 1 to avoid look-ahead (size at t uses vol up to t-1).
        bpy = _bars_per_year(idx) if isinstance(idx, pd.DatetimeIndex) else 252.0
        rets = df["close"].pct_change()
        vol = rets.rolling(20, min_periods=10).std() * math.sqrt(bpy)
        size = (float(sizing.target_vol) / vol).clip(upper=cap).shift(1)
        size = size.fillna(min(float(sizing.value), cap))
        return size.clip(lower=0.0, upper=cap), (
            f"vol_target={sizing.target_vol} cap={cap}"
        )

    if sizing.type == "kelly":
        # v1 simplification: fixed_pct=value scaled by kelly_fraction. Full
        # Kelly requires per-trade edge which we don't have until trades land.
        eff = min(float(sizing.value) * float(sizing.kelly_fraction), cap)
        return pd.Series(eff, index=idx), (
            f"kelly v1 (fixed_pct*kelly_fraction)={eff}"
        )

    # risk_parity — single-asset degenerates to fixed_pct.
    return pd.Series(min(float(sizing.value), cap), index=idx), (
        f"risk_parity (single-asset -> fixed_pct={float(sizing.value)})"
    )


# ─── Stops translation ──────────────────────────────────────────────────


def _stop_args(
    df: pd.DataFrame,
    stops: StopsConfig,
) -> Dict[str, Any]:
    """Translate a `StopsConfig` into kwargs accepted by Portfolio.from_signals.

    Returns a dict with any of: sl_stop, tp_stop, sl_trail (bool), max_duration.
    We always pass percentage stops (VBT's native semantics). ATR-based stops
    are converted to per-bar percentage series using ATR / close.
    """
    kw: Dict[str, Any] = {}

    def _pct_from_atr(period: int, multiplier: float) -> pd.Series:
        atr_df = ind.compute(df, "atr", {"period": period})
        atr_s = atr_df.iloc[:, 0].astype(float)
        return ((atr_s * multiplier) / df["close"]).clip(lower=0.0, upper=0.5)

    if stops.stop_loss is not None:
        sl = stops.stop_loss
        if sl.type == "fixed_pct" and sl.value is not None:
            kw["sl_stop"] = float(sl.value) / 100.0 if sl.value > 1 else float(sl.value)
        elif sl.type == "atr" and sl.multiplier is not None and sl.period is not None:
            kw["sl_stop"] = _pct_from_atr(sl.period, sl.multiplier)
        elif sl.type == "trailing_pct" and sl.value is not None:
            kw["sl_stop"] = float(sl.value) / 100.0 if sl.value > 1 else float(sl.value)
            kw["sl_trail"] = True
        elif sl.type == "trailing_atr" and sl.multiplier is not None and sl.period is not None:
            kw["sl_stop"] = _pct_from_atr(sl.period, sl.multiplier)
            kw["sl_trail"] = True
        # rr_ratio doesn't apply as a stop_loss.

    if stops.take_profit is not None:
        tp = stops.take_profit
        if tp.type == "fixed_pct" and tp.value is not None:
            kw["tp_stop"] = float(tp.value) / 100.0 if tp.value > 1 else float(tp.value)
        elif tp.type == "rr_ratio" and tp.value is not None and "sl_stop" in kw:
            # take_profit at value × stop_loss distance
            sl = kw["sl_stop"]
            if isinstance(sl, pd.Series):
                kw["tp_stop"] = sl * float(tp.value)
            else:
                kw["tp_stop"] = float(sl) * float(tp.value)

    if stops.trailing is not None and "sl_stop" not in kw:
        tr = stops.trailing
        if tr.type == "fixed_pct" and tr.value is not None:
            kw["sl_stop"] = float(tr.value) / 100.0 if tr.value > 1 else float(tr.value)
            kw["sl_trail"] = True
        elif tr.type == "atr" and tr.multiplier is not None and tr.period is not None:
            kw["sl_stop"] = _pct_from_atr(tr.period, tr.multiplier)
            kw["sl_trail"] = True

    if stops.time_stop_bars is not None:
        kw["td_stop"] = int(stops.time_stop_bars)

    return kw


# ─── Result types ───────────────────────────────────────────────────────


@dataclass
class BacktestResult:
    bt_id: str
    project_id: str
    dataset_id: str
    spec_used: Dict[str, Any]
    metrics: Dict[str, Any]
    significance: Dict[str, Any]
    params_used: Dict[str, Any]
    n_bars: int
    start_time: Optional[str]
    end_time: Optional[str]
    created_at: str
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ─── Significance ───────────────────────────────────────────────────────


def _trade_significance(trade_returns: pd.Series) -> Dict[str, Any]:
    """One-sample t-test that mean trade return > 0.

    Returns:
        n_trades, mean_return, std_return, t_stat, p_value (one-sided),
        is_significant_90 (boolean — p < 0.10).
    """
    arr = trade_returns.dropna().to_numpy(dtype=float)
    n = int(arr.size)
    if n < 2 or arr.std(ddof=1) == 0:
        return {
            "n_trades": n,
            "mean_return": _clean(arr.mean()) if n else None,
            "std_return": None,
            "t_stat": None,
            "p_value": None,
            "is_significant_90": False,
            "is_significant_95": False,
        }
    t_stat, p_two = _scstats.ttest_1samp(arr, 0.0)
    # one-sided (mean > 0)
    p_one = float(p_two) / 2.0 if float(t_stat) > 0 else 1.0 - float(p_two) / 2.0
    return {
        "n_trades": n,
        "mean_return": _clean(arr.mean()),
        "std_return": _clean(arr.std(ddof=1)),
        "t_stat": _clean(t_stat),
        "p_value": _clean(p_one),
        "is_significant_90": bool(p_one < 0.10),
        "is_significant_95": bool(p_one < 0.05),
    }


# ─── Main runner ────────────────────────────────────────────────────────


def _normalise_df(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure a unique DatetimeIndex and a `close` column.

    Used by `run_backtest` (after loading from disk) and by `validate.py`
    when running walk-forward on pre-sliced sub-frames.
    """
    if "time" in df.columns and not isinstance(df.index, pd.DatetimeIndex):
        df = df.set_index(pd.to_datetime(df["time"]))
    elif not isinstance(df.index, pd.DatetimeIndex):
        df = df.copy()
        df.index = pd.RangeIndex(len(df))
    if "close" not in df.columns:
        raise ValueError("Dataset is missing required 'close' column")
    return df


def run_backtest_on_df(
    df: pd.DataFrame,
    spec: StrategySpec,
    *,
    project_id: str,
    dataset_id: str,
    init_cash: float = 10_000.0,
    persist: bool = False,
) -> BacktestResult:
    """Run a backtest on an already-loaded DataFrame. Used by walk-forward
    so we can slice without re-reading the parquet for every fold."""
    df = _normalise_df(df)
    return _execute(df, spec, project_id, dataset_id, init_cash, persist)


def run_backtest(
    dataset_id: str,
    spec: StrategySpec,
    *,
    init_cash: float = 10_000.0,
    persist: bool = True,
) -> BacktestResult:
    """Execute one backtest end-to-end and return a structured result."""

    # 1. Resolve project + load data
    found = storage._find_dataset_project(dataset_id)
    if found is None:
        raise ValueError(f"Dataset {dataset_id} not found")
    project_id, _row = found
    path = storage.dataset_path(project_id, dataset_id)
    if not path.exists():
        raise ValueError(f"Dataset parquet missing on disk: {path}")
    df = _data.load_dataset(path)
    df = _normalise_df(df)

    return _execute(df, spec, project_id, dataset_id, init_cash, persist)


def _execute(
    df: pd.DataFrame,
    spec: StrategySpec,
    project_id: str,
    dataset_id: str,
    init_cash: float,
    persist: bool,
) -> BacktestResult:
    # 2. Compile signals
    entries, exits = compile_signals(df, spec)

    # 3. Sizing
    size_series, sizing_note = _build_size_series(df, spec)

    # 4. Costs + stops
    fees, slip = resolve_costs(spec)
    stop_kwargs = _stop_args(df, spec.stops)

    # 5. Run portfolio
    pf = vbt.Portfolio.from_signals(
        close=df["close"].astype(float),
        entries=entries,
        exits=exits,
        size=size_series,
        size_type="percent",
        init_cash=init_cash,
        fees=fees,
        slippage=slip,
        freq=_robust_freq(df.index),
        **stop_kwargs,
    )

    # 6. Metrics
    bpy = _bars_per_year(df.index) if isinstance(df.index, pd.DatetimeIndex) else 252.0
    trades = pf.trades
    n_trades = int(trades.count())
    trade_returns = trades.returns.values if n_trades > 0 else pd.Series(dtype=float)
    if isinstance(trade_returns, np.ndarray):
        trade_returns = pd.Series(trade_returns)

    total_return = float(pf.total_return())
    duration_years = (
        (df.index[-1] - df.index[0]).total_seconds() / (365.25 * 24 * 3600)
        if isinstance(df.index, pd.DatetimeIndex) and len(df.index) >= 2
        else len(df) / bpy
    )
    cagr = (
        (1.0 + total_return) ** (1.0 / duration_years) - 1.0
        if duration_years > 0 and (1.0 + total_return) > 0
        else None
    )

    # Data-usage gauge (diagram's "Must use > 70% of total dataset" rule).
    # Counts bars where the strategy held a position. Total dataset bars is
    # ``len(df)`` because we already loaded the canonicalised parquet.
    # We try three paths in order — first one to yield usable data wins.
    data_usage_pct = 0.0
    if n_trades > 0:
        try:
            # Path 1: cash_flow / asset_value series → non-zero positions
            asset = getattr(pf, "asset_value", None)
            if callable(asset):
                av = asset()
            else:
                av = asset
            if av is not None:
                arr = np.asarray(av).astype(float)
                if arr.ndim == 2:
                    arr = np.abs(arr).sum(axis=1)
                data_usage_pct = float((np.abs(arr) > 1e-9).mean())
        except Exception:
            pass

        if data_usage_pct == 0.0:
            try:
                # Path 2: trade records — index-based bar coverage.
                tr = trades.records_readable
                in_trade = np.zeros(len(df), dtype=bool)
                if hasattr(tr, "iterrows"):
                    cols = {c.lower(): c for c in tr.columns}
                    ent_col = cols.get("entry index") or cols.get("entry idx") or cols.get("entry_idx")
                    ext_col = cols.get("exit index") or cols.get("exit idx") or cols.get("exit_idx")
                    if ent_col and ext_col:
                        for _, row in tr.iterrows():
                            ent = int(row[ent_col])
                            ext = int(row[ext_col])
                            if 0 <= ent < len(in_trade) and 0 <= ext < len(in_trade):
                                in_trade[ent: ext + 1] = True
                if in_trade.any():
                    data_usage_pct = float(in_trade.mean())
            except Exception:
                pass

        if data_usage_pct == 0.0:
            # Path 3: bars-with-trades floor — at least the bars where
            # an entry or exit happened. Conservative lower bound.
            try:
                data_usage_pct = float(min(1.0, n_trades * 2 / max(1, len(df))))
            except Exception:
                data_usage_pct = 0.0

    metrics = _clean_metrics({
        "total_return": total_return,
        "cagr": cagr,
        "sharpe": float(pf.sharpe_ratio()),
        "sortino": float(pf.sortino_ratio()),
        "max_drawdown": float(pf.max_drawdown()),
        "calmar": float(pf.calmar_ratio()),
        "num_trades": n_trades,
        "win_rate": float(trades.win_rate()) if n_trades > 0 else None,
        "profit_factor": float(trades.profit_factor()) if n_trades > 0 else None,
        "avg_trade": float(trade_returns.mean()) if n_trades > 0 else None,
        "expectancy": float(trades.expectancy()) if n_trades > 0 else None,
        "best_trade": float(trade_returns.max()) if n_trades > 0 else None,
        "worst_trade": float(trade_returns.min()) if n_trades > 0 else None,
        "duration_years": duration_years,
        "bars_per_year": bpy,
        # New: data coverage — what fraction of the bar count had open
        # positions. The validation engine vetos < 0.0 (no signal) and
        # the report shows it on the cover.
        "data_usage_pct": data_usage_pct,
        "total_bars": int(len(df)),
    })
    significance = _trade_significance(trade_returns)

    # 7. Persistence
    bt_id = _bt_id()
    created_at = datetime.now(timezone.utc).isoformat()
    notes = [f"sizing: {sizing_note}"]

    result = BacktestResult(
        bt_id=bt_id,
        project_id=project_id,
        dataset_id=dataset_id,
        spec_used=json.loads(spec.model_dump_json()),
        metrics=metrics,
        significance=significance,
        params_used={
            "fees": fees,
            "slippage": slip,
            "init_cash": init_cash,
            "stops_resolved": _serializable_stops(stop_kwargs),
        },
        n_bars=int(len(df)),
        start_time=_clean(df.index[0]) if len(df) else None,
        end_time=_clean(df.index[-1]) if len(df) else None,
        created_at=created_at,
        notes=notes,
    )

    if persist:
        _persist_result(project_id, bt_id, result, pf, df)

    return result


def _serializable_stops(stop_kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """Reduce stop_kwargs (which may include pd.Series) to a JSON-safe summary."""
    out: Dict[str, Any] = {}
    for k, v in stop_kwargs.items():
        if isinstance(v, pd.Series):
            out[k] = {
                "type": "series",
                "mean": _clean(v.mean()),
                "min": _clean(v.min()),
                "max": _clean(v.max()),
            }
        else:
            out[k] = _clean(v)
    return out


def _persist_result(
    project_id: str,
    bt_id: str,
    result: BacktestResult,
    pf: "vbt.Portfolio",
    df: pd.DataFrame,
) -> None:
    out_dir = _backtests_dir(project_id)

    # Summary JSON.
    (out_dir / f"{bt_id}.json").write_text(
        json.dumps(result.to_dict(), indent=2, default=str), encoding="utf-8"
    )

    # Equity + drawdown curves (long parquet).
    try:
        eq = pf.value().rename("equity")
        dd = pf.drawdown().rename("drawdown")
        curve = pd.concat([eq, dd], axis=1)
        curve.index.name = "time"
        curve.reset_index().to_parquet(out_dir / f"{bt_id}_equity.parquet", index=False)
    except Exception:
        # Curve persistence is best-effort — never fail a backtest because of it.
        pass

    # Trade ledger.
    try:
        trades_df = pf.trades.records_readable
        if not trades_df.empty:
            trades_df.to_parquet(out_dir / f"{bt_id}_trades.parquet", index=False)
    except Exception:
        pass


def load_backtest_summary(project_id: str, bt_id: str) -> Optional[Dict[str, Any]]:
    """Re-read a persisted backtest summary JSON (None if missing)."""
    p = _backtests_dir(project_id) / f"{bt_id}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


# ─── CLI smoke ──────────────────────────────────────────────────────────


def _smoke() -> None:
    """`python -m app.backtest` — runs against synthetic data (no FS deps)."""
    from .strategies import CondGroup, Condition

    np.random.seed(7)
    n = 800
    idx = pd.date_range("2024-01-01", periods=n, freq="1h")
    close = pd.Series(100 + np.cumsum(np.random.randn(n) * 0.4), index=idx)
    df = pd.DataFrame({
        "time": idx,
        "open": close.shift(1).fillna(close.iloc[0]),
        "high": close + np.abs(np.random.randn(n) * 0.2),
        "low": close - np.abs(np.random.randn(n) * 0.2),
        "close": close,
        "volume": np.random.randint(1000, 10_000, size=n).astype(float),
    })

    spec = StrategySpec(
        name="rsi_meanrev_smoke",
        market="crypto",
        entries=CondGroup(all_of=[
            Condition(indicator="rsi", params={"period": 14}, op="<", value=30),
        ]),
        exits=CondGroup(all_of=[
            Condition(indicator="rsi", params={"period": 14}, op=">", value=70),
        ]),
    )

    # Fast-path: build everything in-memory (skip storage)
    df_idx = df.set_index(pd.to_datetime(df["time"]))
    entries, exits = compile_signals(df_idx, spec)
    size, _ = _build_size_series(df_idx, spec)
    fees, slip = resolve_costs(spec)

    t0 = time.perf_counter()
    pf = vbt.Portfolio.from_signals(
        close=df_idx["close"].astype(float),
        entries=entries, exits=exits,
        size=size, size_type="percent",
        init_cash=10_000.0,
        fees=fees, slippage=slip,
        freq="1h",
    )
    elapsed = time.perf_counter() - t0

    n_trades = int(pf.trades.count())
    print(f"trades={n_trades}  total_return={pf.total_return():.4f}  "
          f"sharpe={pf.sharpe_ratio():.3f}  max_dd={pf.max_drawdown():.4f}  "
          f"elapsed={elapsed*1000:.1f}ms")

    # Significance
    if n_trades > 0:
        sig = _trade_significance(pd.Series(pf.trades.returns.values))
        print("significance:", {k: sig[k] for k in (
            "n_trades", "mean_return", "t_stat", "p_value", "is_significant_90"
        )})

    print("BACKTEST SMOKE OK")


if __name__ == "__main__":
    _smoke()
