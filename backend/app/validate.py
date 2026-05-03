"""Out-of-sample validation (Phase 7, Slice 5).

Two production-grade tools for telling a *real* edge from curve-fitting noise:

1. **Walk-forward analysis** (`walk_forward`):
   - Split the dataset into K rolling/anchored folds.
   - For each fold, optionally re-optimise on the in-sample window via a
     supplied `grid`, then evaluate the chosen spec on the immediately-
     following out-of-sample window.
   - Aggregate OOS metrics and report the IS-vs-OOS *degradation ratio*.
     A WFE (walk-forward efficiency) ratio in [0.5, 1.0] suggests robust
     edge; below 0.5 is overfit; above 1.0 is suspiciously lucky OOS and
     usually means a regime shift.

2. **Monte Carlo bootstrap** (`monte_carlo`):
   - Take the trade-return series from a single backtest.
   - Resample with replacement N times to build a synthetic distribution
     of equity curves.
   - Report percentile bands for total_return, max_drawdown, sharpe, plus
     P(mean trade > 0) — the bootstrap p-value for "this strategy has a
     real positive edge versus its own noise".

Both functions persist a JSON summary to `workspaces/<pid>/validations/`
so the chat layer can re-load and reference results by id.

Why not k-fold cross-validation? Because trading data is sequential —
shuffling future bars into training would leak look-ahead. Walk-forward
preserves time order and is the industry standard for strategy QA.
"""

from __future__ import annotations

import json
import math
import secrets
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from . import data as _data
from . import storage
from .backtest import BacktestResult, run_backtest_on_df, _bars_per_year
from .optimize import optimize as run_optimize
from .paths import workspace_dir
from .strategies import StrategySpec


# ─── IDs / paths ────────────────────────────────────────────────────────


def _val_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


def _val_dir(project_id: str) -> Path:
    p = workspace_dir(project_id) / "validations"
    p.mkdir(parents=True, exist_ok=True)
    return p


# ─── Dataset loading helper ─────────────────────────────────────────────


def _load_full_df(dataset_id: str) -> Tuple[str, pd.DataFrame]:
    """Resolve project + load the full parquet once."""
    found = storage._find_dataset_project(dataset_id)
    if found is None:
        raise ValueError(f"Dataset {dataset_id} not found")
    project_id, _ = found
    path = storage.dataset_path(project_id, dataset_id)
    if not path.exists():
        raise ValueError(f"Dataset parquet missing on disk: {path}")
    df = _data.load_dataset(path)
    if "time" in df.columns:
        df = df.set_index(pd.to_datetime(df["time"]))
    if not df.index.is_unique:
        df = df[~df.index.duplicated(keep="first")]
    df = df.sort_index()
    return project_id, df


# ─── Walk-forward ───────────────────────────────────────────────────────


@dataclass
class WFFold:
    fold_id: int
    in_sample_start: str
    in_sample_end: str
    out_sample_start: str
    out_sample_end: str
    chosen_point: Dict[str, Any]
    in_sample_metrics: Dict[str, Any]
    out_sample_metrics: Dict[str, Any]
    notes: List[str] = field(default_factory=list)


@dataclass
class WalkForwardResult:
    val_id: str
    project_id: str
    dataset_id: str
    base_spec: Dict[str, Any]
    grid: Optional[Dict[str, List[Any]]]
    score_metric: str
    n_folds: int
    is_oos_split: float
    fold_mode: str
    folds: List[Dict[str, Any]]
    aggregate: Dict[str, Any]
    wfe: Optional[float]
    verdict: str
    elapsed_sec: float
    created_at: str
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _split_folds(
    df: pd.DataFrame,
    n_folds: int,
    is_oos_split: float,
    mode: str,
) -> List[Tuple[pd.DataFrame, pd.DataFrame]]:
    """Slice the df into (in_sample, out_sample) tuples.

    mode:
        "rolling": fixed-size sliding IS window followed by an OOS chunk.
        "anchored": IS window grows from the start, OOS chunk advances.
    """
    n = len(df)
    if n_folds < 2:
        raise ValueError("n_folds must be >= 2")
    if not (0.3 <= is_oos_split <= 0.95):
        raise ValueError("is_oos_split must be in [0.30, 0.95]")
    if mode not in ("rolling", "anchored"):
        raise ValueError("mode must be 'rolling' or 'anchored'")

    # Total fold size = IS + OOS bars. OOS chunks tile the dataset end-to-end.
    # Pick OOS_size so the first fold's IS_size starts inside the data, and
    # n_folds OOS chunks fit. Intuitively:
    #   IS_size + n_folds * OOS_size == n
    # solve with the requested IS:OOS ratio:
    #   IS_size = is_oos_split * (IS_size + OOS_size)
    #   => OOS_size = IS_size * (1 - is_oos_split) / is_oos_split
    # Together: IS_size + n_folds * IS_size * (1-r)/r = n
    #   IS_size * (1 + n_folds*(1-r)/r) = n
    r = is_oos_split
    is_size = int(n / (1.0 + n_folds * (1.0 - r) / r))
    oos_size = max(1, int(is_size * (1.0 - r) / r))
    if is_size < 50 or oos_size < 20:
        raise ValueError(
            f"Computed IS={is_size}/OOS={oos_size} bars are too small. "
            f"Need a longer dataset, fewer folds, or a different split ratio."
        )

    folds: List[Tuple[pd.DataFrame, pd.DataFrame]] = []
    for i in range(n_folds):
        oos_start = is_size + i * oos_size
        oos_end = oos_start + oos_size
        if oos_end > n:
            break
        if mode == "rolling":
            is_start = oos_start - is_size
            is_end = oos_start
        else:  # anchored
            is_start = 0
            is_end = oos_start
        folds.append((df.iloc[is_start:is_end], df.iloc[oos_start:oos_end]))
    if not folds:
        raise ValueError("No usable folds — dataset too short for the request")
    return folds


def _idx_str(ts: Any) -> str:
    if isinstance(ts, pd.Timestamp):
        return ts.isoformat()
    return str(ts)


def _wfe(is_metrics: List[Dict[str, Any]], oos_metrics: List[Dict[str, Any]],
         metric: str) -> Optional[float]:
    """Walk-forward efficiency = mean(OOS metric) / mean(IS metric).

    Returns None if either side has no usable values or IS mean is ~0.
    """
    is_vals = [m.get(metric) for m in is_metrics if m.get(metric) is not None]
    oos_vals = [m.get(metric) for m in oos_metrics if m.get(metric) is not None]
    if not is_vals or not oos_vals:
        return None
    is_mean = float(np.mean(is_vals))
    oos_mean = float(np.mean(oos_vals))
    if abs(is_mean) < 1e-9:
        return None
    return oos_mean / is_mean


def _wfe_verdict(wfe: Optional[float], oos_mean_sharpe: Optional[float]) -> str:
    """Plain-English judgement on walk-forward result."""
    if wfe is None:
        return "inconclusive — insufficient data for WFE"
    if oos_mean_sharpe is None or oos_mean_sharpe <= 0:
        return "fails OOS — strategy loses money out of sample"
    if wfe < 0.3:
        return "severe overfit — OOS keeps <30% of IS edge"
    if wfe < 0.5:
        return "moderate overfit — OOS keeps 30-50% of IS edge"
    if wfe < 0.8:
        return "acceptable — OOS keeps 50-80% of IS edge"
    if wfe <= 1.2:
        return "robust — OOS roughly matches IS"
    return "regime tail — OOS exceeds IS, treat with caution"


def walk_forward(
    dataset_id: str,
    base_spec: StrategySpec,
    *,
    grid: Optional[Dict[str, Sequence[Any]]] = None,
    n_folds: int = 5,
    is_oos_split: float = 0.7,
    mode: str = "rolling",
    score_metric: str = "sharpe",
    min_trades: int = 10,
    max_dd_floor: float = -0.50,
    max_combinations: int = 200,
    init_cash: float = 10_000.0,
    persist: bool = True,
) -> WalkForwardResult:
    """Walk-forward validation. If `grid` is provided, each fold re-optimises
    on its in-sample window; otherwise the base_spec is evaluated as-is on
    every fold (still useful — measures stability across regimes)."""

    t0 = time.perf_counter()
    project_id, df = _load_full_df(dataset_id)

    folds_data = _split_folds(df, n_folds, is_oos_split, mode)

    fold_results: List[WFFold] = []
    is_metrics_list: List[Dict[str, Any]] = []
    oos_metrics_list: List[Dict[str, Any]] = []

    for i, (is_df, oos_df) in enumerate(folds_data):
        fold_notes: List[str] = []
        chosen_point: Dict[str, Any] = {}
        chosen_spec: StrategySpec = base_spec

        # 1. Optionally re-optimise on IS only — we cannot reuse `optimize()`
        # because it loads the full dataset from storage; we'd leak the OOS
        # window into the search. Instead reuse its grid + veto/score helpers
        # against in-memory IS-slice backtests.
        if grid:
            try:
                from .optimize import (
                    _apply_point,
                    _materialise_grid,
                    _score,
                    _validate_grid,
                    _veto,
                )

                norm = _validate_grid(grid, max_combinations)
                points = _materialise_grid(norm)
                base_dict = json.loads(base_spec.model_dump_json())
                best_score: Optional[float] = None
                best_point: Optional[Dict[str, Any]] = None
                best_spec: Optional[StrategySpec] = None
                for pt in points:
                    try:
                        s_i = _apply_point(base_dict, pt)
                        r_i = run_backtest_on_df(
                            is_df, s_i,
                            project_id=project_id, dataset_id=dataset_id,
                            init_cash=init_cash, persist=False,
                        )
                    except Exception:
                        continue
                    if _veto(
                        r_i.metrics, r_i.significance,
                        min_trades=min_trades, max_dd_floor=max_dd_floor,
                    ) is not None:
                        continue
                    s = _score(r_i.metrics, score_metric)
                    if s is None:
                        continue
                    if best_score is None or s > best_score:
                        best_score = s
                        best_point = pt
                        best_spec = s_i
                if best_spec is None:
                    fold_notes.append("no IS combo passed vetos; falling back to base_spec")
                else:
                    chosen_point = best_point or {}
                    chosen_spec = best_spec
            except Exception as exc:
                fold_notes.append(
                    f"IS optimisation failed: {exc.__class__.__name__}: {exc}"
                )

        # 2. Evaluate chosen spec on IS and OOS for IS-vs-OOS comparison.
        try:
            is_res = run_backtest_on_df(
                is_df, chosen_spec,
                project_id=project_id, dataset_id=dataset_id,
                init_cash=init_cash, persist=False,
            )
            is_m = is_res.metrics
        except Exception as exc:
            is_m = {"error": f"{exc.__class__.__name__}: {exc}"}
        try:
            oos_res = run_backtest_on_df(
                oos_df, chosen_spec,
                project_id=project_id, dataset_id=dataset_id,
                init_cash=init_cash, persist=False,
            )
            oos_m = oos_res.metrics
        except Exception as exc:
            oos_m = {"error": f"{exc.__class__.__name__}: {exc}"}

        is_metrics_list.append(is_m)
        oos_metrics_list.append(oos_m)

        fold_results.append(WFFold(
            fold_id=i,
            in_sample_start=_idx_str(is_df.index[0]),
            in_sample_end=_idx_str(is_df.index[-1]),
            out_sample_start=_idx_str(oos_df.index[0]),
            out_sample_end=_idx_str(oos_df.index[-1]),
            chosen_point=chosen_point,
            in_sample_metrics=is_m,
            out_sample_metrics=oos_m,
            notes=fold_notes,
        ))

    # Aggregate
    def _safe_mean(ms: List[Dict[str, Any]], key: str) -> Optional[float]:
        vals = [m.get(key) for m in ms if isinstance(m.get(key), (int, float))]
        return float(np.mean(vals)) if vals else None

    aggregate = {
        "is_mean_sharpe": _safe_mean(is_metrics_list, "sharpe"),
        "oos_mean_sharpe": _safe_mean(oos_metrics_list, "sharpe"),
        "is_mean_total_return": _safe_mean(is_metrics_list, "total_return"),
        "oos_mean_total_return": _safe_mean(oos_metrics_list, "total_return"),
        "is_mean_max_dd": _safe_mean(is_metrics_list, "max_drawdown"),
        "oos_mean_max_dd": _safe_mean(oos_metrics_list, "max_drawdown"),
        "oos_pos_sharpe_folds": int(sum(
            1 for m in oos_metrics_list
            if isinstance(m.get("sharpe"), (int, float)) and m["sharpe"] > 0
        )),
        "oos_total_folds": len(oos_metrics_list),
    }
    wfe = _wfe(is_metrics_list, oos_metrics_list, score_metric)
    verdict = _wfe_verdict(wfe, aggregate["oos_mean_sharpe"])

    val_id = _val_id("wf")
    result = WalkForwardResult(
        val_id=val_id,
        project_id=project_id,
        dataset_id=dataset_id,
        base_spec=json.loads(base_spec.model_dump_json()),
        grid={k: list(v) for k, v in grid.items()} if grid else None,
        score_metric=score_metric,
        n_folds=len(fold_results),
        is_oos_split=is_oos_split,
        fold_mode=mode,
        folds=[asdict(f) for f in fold_results],
        aggregate=aggregate,
        wfe=wfe,
        verdict=verdict,
        elapsed_sec=float(time.perf_counter() - t0),
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    if persist:
        out = _val_dir(project_id) / f"{val_id}.json"
        out.write_text(
            json.dumps(result.to_dict(), indent=2, default=str), encoding="utf-8"
        )

    return result


# ─── Monte Carlo bootstrap ──────────────────────────────────────────────


@dataclass
class MonteCarloResult:
    val_id: str
    project_id: str
    dataset_id: str
    base_spec: Dict[str, Any]
    n_iterations: int
    n_trades: int
    bars_per_year: float
    duration_years: float
    actual_metrics: Dict[str, Any]
    percentiles: Dict[str, Dict[str, float]]
    p_value_positive_mean: Optional[float]
    p_value_beats_zero_return: Optional[float]
    expected_total_return: Optional[float]
    expected_max_drawdown: Optional[float]
    # ── Phase-3 expansion: validation-engine gates ──
    # `survival_rate` = fraction of MC iterations that ended with positive
    # total return. Diagram's "Monte Carlo Rule: Survival Rate > 90%".
    survival_rate: Optional[float] = None
    # `dd_within_limit_rate` = fraction of MC iterations whose max DD did
    # not exceed `dd_limit` (default -30%). Diagram's "Drawdown Within Limit".
    dd_within_limit_rate: Optional[float] = None
    dd_limit: float = -0.30
    verdict: str = ""
    elapsed_sec: float = 0.0
    created_at: str = ""
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _bootstrap_sample(
    trade_returns: np.ndarray,
    n_trades: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Sample `n_trades` returns with replacement."""
    return rng.choice(trade_returns, size=n_trades, replace=True)


def _equity_stats(samples: np.ndarray) -> Tuple[float, float, float]:
    """Compounded total return, max drawdown, sharpe-like ratio (mean/std)
    of a single bootstrap sample's compounded equity curve."""
    eq = np.cumprod(1.0 + samples)
    total_return = float(eq[-1] - 1.0)
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / peak
    max_dd = float(dd.min())
    if samples.std(ddof=1) > 0:
        sharpe_like = float(samples.mean() / samples.std(ddof=1) * math.sqrt(len(samples)))
    else:
        sharpe_like = 0.0
    return total_return, max_dd, sharpe_like


def monte_carlo(
    dataset_id: str,
    spec: StrategySpec,
    *,
    n_iterations: int = 2000,
    init_cash: float = 10_000.0,
    persist: bool = True,
    seed: Optional[int] = None,
) -> MonteCarloResult:
    """Bootstrap N synthetic equity curves from the actual trade returns.

    Reports percentile bands + a one-sided p-value for the mean trade
    return being > 0 under the null that returns are i.i.d. with mean ≤ 0.
    """
    if n_iterations < 200:
        raise ValueError("n_iterations must be >= 200 for stable percentiles")
    if n_iterations > 50_000:
        raise ValueError("n_iterations capped at 50,000 (memory + runtime)")

    t0 = time.perf_counter()

    # Run the actual backtest first.
    project_id, df = _load_full_df(dataset_id)
    actual = run_backtest_on_df(
        df, spec,
        project_id=project_id, dataset_id=dataset_id,
        init_cash=init_cash, persist=False,
    )

    # Reload trade returns from the persisted-but-now-not-persisted result by
    # re-running its underlying portfolio. Actually `actual.metrics` already
    # has the per-bar info we need; but for trade returns we need to re-run
    # `run_backtest_on_df` with persist=True or expose them. The easier
    # path: re-construct via vectorbt directly. To avoid duplication we'll
    # instead re-execute and grab trades.returns.
    from .strategies import compile_signals, resolve_costs
    from .backtest import _build_size_series, _stop_args, _normalise_df, _robust_freq
    import vectorbt as vbt

    df_n = _normalise_df(df)
    entries, exits = compile_signals(df_n, spec)
    size_series, _ = _build_size_series(df_n, spec)
    fees, slip = resolve_costs(spec)
    pf = vbt.Portfolio.from_signals(
        close=df_n["close"].astype(float),
        entries=entries, exits=exits,
        size=size_series, size_type="percent",
        init_cash=init_cash, fees=fees, slippage=slip,
        freq=_robust_freq(df_n.index),
        **_stop_args(df_n, spec.stops),
    )
    trade_returns = np.asarray(pf.trades.returns.values, dtype=float)
    trade_returns = trade_returns[~np.isnan(trade_returns)]
    n_trades = int(trade_returns.size)

    if n_trades < 5:
        mc_val_id = _val_id("mc")
        result = MonteCarloResult(
            val_id=mc_val_id,
            project_id=project_id,
            dataset_id=dataset_id,
            base_spec=json.loads(spec.model_dump_json()),
            n_iterations=0,
            n_trades=n_trades,
            bars_per_year=_bars_per_year(df_n.index)
                if isinstance(df_n.index, pd.DatetimeIndex) else 252.0,
            duration_years=actual.metrics.get("duration_years") or 0.0,
            actual_metrics=actual.metrics,
            percentiles={},
            p_value_positive_mean=None,
            p_value_beats_zero_return=None,
            expected_total_return=None,
            expected_max_drawdown=None,
            verdict="inconclusive — fewer than 5 trades to bootstrap",
            elapsed_sec=float(time.perf_counter() - t0),
            created_at=datetime.now(timezone.utc).isoformat(),
            notes=["Strategy generated too few trades for a meaningful Monte Carlo."],
        )
        # Persist even inconclusive results so downstream report renderer
        # can find the artifact by ID (pipeline captures val_id regardless).
        if persist:
            out = _val_dir(project_id) / f"{mc_val_id}.json"
            out.write_text(
                json.dumps(result.to_dict(), indent=2, default=str), encoding="utf-8"
            )
        return result

    rng = np.random.default_rng(seed)
    total_returns = np.empty(n_iterations, dtype=float)
    max_dds = np.empty(n_iterations, dtype=float)
    sharpe_likes = np.empty(n_iterations, dtype=float)
    mean_returns = np.empty(n_iterations, dtype=float)

    for k in range(n_iterations):
        sample = _bootstrap_sample(trade_returns, n_trades, rng)
        tr, dd, sh = _equity_stats(sample)
        total_returns[k] = tr
        max_dds[k] = dd
        sharpe_likes[k] = sh
        mean_returns[k] = float(sample.mean())

    pct_levels = [5, 10, 25, 50, 75, 90, 95]

    def _pcts(arr: np.ndarray) -> Dict[str, float]:
        out = {f"p{p}": float(np.percentile(arr, p)) for p in pct_levels}
        out["mean"] = float(arr.mean())
        out["std"] = float(arr.std(ddof=1))
        return out

    percentiles = {
        "total_return": _pcts(total_returns),
        "max_drawdown": _pcts(max_dds),
        "sharpe_like": _pcts(sharpe_likes),
        "mean_trade_return": _pcts(mean_returns),
    }

    # Bootstrap p-value: P(bootstrap mean trade return <= 0) under
    # the null that the resampling distribution centres on zero.
    # Standard one-sided test: count how many synthetic sample means
    # were <= 0 — that proportion is our p-value for "edge is real".
    p_pos = float((mean_returns <= 0).mean())
    # Probability a random reshuffle produces a non-positive equity
    # outcome (conservative "did we make money?" check).
    p_pos_eq = float((total_returns <= 0).mean())

    expected_tr = float(total_returns.mean())
    expected_dd = float(max_dds.mean())
    # Production-grade gates the AI-Backtester-Flow diagram requires.
    survival_rate = float((total_returns > 0).mean())
    dd_limit = -0.30
    dd_within_rate = float((max_dds > dd_limit).mean())

    if p_pos < 0.05 and expected_tr > 0:
        verdict = "strong edge — bootstrap rejects null at 95% confidence"
    elif p_pos < 0.10 and expected_tr > 0:
        verdict = "marginal edge — bootstrap rejects null at 90% confidence"
    elif expected_tr > 0:
        verdict = "uncertain — positive mean but inside noise"
    else:
        verdict = "no edge — bootstrap mean is non-positive"

    val_id = _val_id("mc")
    result = MonteCarloResult(
        val_id=val_id,
        project_id=project_id,
        dataset_id=dataset_id,
        base_spec=json.loads(spec.model_dump_json()),
        n_iterations=n_iterations,
        n_trades=n_trades,
        bars_per_year=_bars_per_year(df_n.index)
            if isinstance(df_n.index, pd.DatetimeIndex) else 252.0,
        duration_years=actual.metrics.get("duration_years") or 0.0,
        actual_metrics=actual.metrics,
        percentiles=percentiles,
        p_value_positive_mean=p_pos,
        p_value_beats_zero_return=p_pos_eq,
        expected_total_return=expected_tr,
        expected_max_drawdown=expected_dd,
        survival_rate=survival_rate,
        dd_within_limit_rate=dd_within_rate,
        dd_limit=dd_limit,
        verdict=verdict,
        elapsed_sec=float(time.perf_counter() - t0),
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    if persist:
        out = _val_dir(project_id) / f"{val_id}.json"
        out.write_text(
            json.dumps(result.to_dict(), indent=2, default=str), encoding="utf-8"
        )

    return result


def load_validation_summary(project_id: str, val_id: str) -> Optional[Dict[str, Any]]:
    p = _val_dir(project_id) / f"{val_id}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


# ─── CLI smoke ──────────────────────────────────────────────────────────


def _smoke() -> None:
    """`python -m app.validate` — runs WF + MC end-to-end on synthetic data."""
    import tempfile
    from .strategies import CondGroup, Condition

    np.random.seed(13)
    n = 3000  # need enough bars for 5 folds @ 70/30
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

    project = storage.create_project(name="validate smoke project")
    project_id = project.id
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    df.to_csv(tmp_path, index=False)
    ds = storage.ingest_and_store_dataset(project_id, "smoke.csv", tmp_path)
    try:
        tmp_path.unlink(missing_ok=True)
    except Exception:
        pass
    if ds is None:
        raise RuntimeError("ingest failed")
    dataset_id = ds.id
    print(f"smoke project={project_id} dataset={dataset_id}")

    spec = StrategySpec(
        name="rsi_meanrev_validate",
        market="crypto",
        entries=CondGroup(all_of=[
            Condition(indicator="rsi", params={"period": 14}, op="<", value=30),
        ]),
        exits=CondGroup(all_of=[
            Condition(indicator="rsi", params={"period": 14}, op=">", value=70),
        ]),
    )

    # 1. Walk-forward (no grid → just stability test)
    wf = walk_forward(
        dataset_id, spec,
        n_folds=3, is_oos_split=0.7, mode="rolling",
        score_metric="sharpe", min_trades=3, max_dd_floor=-0.95,
    )
    print(f"WF folds={wf.n_folds} wfe={wf.wfe} verdict='{wf.verdict}'")
    print(f"   IS sharpe={wf.aggregate['is_mean_sharpe']:.3f} "
          f"OOS sharpe={wf.aggregate['oos_mean_sharpe']:.3f}")

    # 2. Walk-forward WITH a tiny grid → exercises the optimise path
    wf2 = walk_forward(
        dataset_id, spec,
        grid={"entries.all_of.0.value": [25, 30, 35]},
        n_folds=3, is_oos_split=0.7, mode="rolling",
        score_metric="sharpe", min_trades=3, max_dd_floor=-0.95,
        max_combinations=10,
    )
    print(f"WF+grid folds={wf2.n_folds} wfe={wf2.wfe}")
    for f in wf2.folds:
        print(f"   fold {f['fold_id']}: chosen={f['chosen_point']} "
              f"OOS_sharpe={f['out_sample_metrics'].get('sharpe')}")

    # 3. Monte Carlo
    mc = monte_carlo(dataset_id, spec, n_iterations=500, seed=42)
    print(f"MC iters={mc.n_iterations} trades={mc.n_trades} "
          f"p_pos={mc.p_value_positive_mean} verdict='{mc.verdict}'")
    print(f"   total_return p5={mc.percentiles['total_return']['p5']:.4f} "
          f"p50={mc.percentiles['total_return']['p50']:.4f} "
          f"p95={mc.percentiles['total_return']['p95']:.4f}")
    print(f"   max_dd p5={mc.percentiles['max_drawdown']['p5']:.4f} "
          f"p50={mc.percentiles['max_drawdown']['p50']:.4f}")

    # 4. Reload
    again = load_validation_summary(project_id, mc.val_id)
    assert again is not None and again["val_id"] == mc.val_id
    print("VALIDATE SMOKE OK")


if __name__ == "__main__":
    _smoke()
