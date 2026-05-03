"""Strategy parameter optimisation (Phase 7, Slice 4).

Public API:
    optimize(dataset_id, base_spec, grid, *, ...) -> OptimizeResult

Pipeline:
    1. Validate the base spec, the grid, and an explicit `max_combinations`
       cap so a careless AI tool call cannot DoS the backend.
    2. Materialise the full Cartesian grid as a deterministic list of
       `point` dicts (`{param_path: value, ...}`).
    3. For each point, deep-copy the base spec, mutate it via dotted-path
       assignment, run an in-memory backtest (no FS persistence per combo),
       and record the metrics row.
    4. Apply production-grade veto rules (min_trades, max-drawdown floor,
       significance preference) and rank by `score_metric`.
    5. Detect a *robust region* — for each varied parameter, find the
       contiguous run of values whose marginal mean score stays in the top
       quartile. This protects against curve-fits where a single param
       value happens to hit the global maximum but its neighbours implode.
    6. Persist a single `opt_<id>.json` summary so the chat / report layer
       can re-load the result.

Robustness over peak-fitness: the `verdict` returned is the highest-scoring
combination *inside* the robust region, not necessarily the global maximum.

Why dotted-paths instead of dict-overrides? An `StrategySpec` has nested
lists (`entries.all_of[0].value`); a flat path is unambiguous and AI-
friendly. We accept integer path components for list indexing.
"""

from __future__ import annotations

import copy
import itertools
import json
import math
import secrets
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from .backtest import BacktestResult, run_backtest
from .paths import workspace_dir
from .strategies import StrategySpec
from . import storage


# ─── IDs / paths ────────────────────────────────────────────────────────


def _opt_id() -> str:
    return f"opt_{secrets.token_hex(8)}"


def _opt_dir(project_id: str) -> Path:
    p = workspace_dir(project_id) / "optimizations"
    p.mkdir(parents=True, exist_ok=True)
    return p


# ─── Grid utilities ─────────────────────────────────────────────────────


def _validate_grid(
    grid: Dict[str, Sequence[Any]],
    max_combinations: int,
) -> List[Tuple[str, List[Any]]]:
    """Normalise + cap the grid; raise on misuse."""
    if not isinstance(grid, dict) or not grid:
        raise ValueError("grid must be a non-empty dict of {param_path: [values]}")

    norm: List[Tuple[str, List[Any]]] = []
    total = 1
    for path, vals in grid.items():
        if not isinstance(path, str) or not path:
            raise ValueError(f"grid key must be a non-empty dotted path, got {path!r}")
        if isinstance(vals, (str, bytes)) or not isinstance(vals, Iterable):
            raise ValueError(f"grid[{path!r}] must be a list/sequence of values")
        v_list = list(vals)
        if not v_list:
            raise ValueError(f"grid[{path!r}] is empty")
        if len(v_list) > 50:
            raise ValueError(
                f"grid[{path!r}] has {len(v_list)} values — cap is 50 per axis"
            )
        norm.append((path, v_list))
        total *= len(v_list)

    if total > max_combinations:
        raise ValueError(
            f"Grid expands to {total} combinations, exceeding cap of "
            f"{max_combinations}. Reduce axes or values."
        )
    return norm


def _materialise_grid(
    norm: List[Tuple[str, List[Any]]],
) -> List[Dict[str, Any]]:
    """Deterministic Cartesian product as a list of point-dicts."""
    paths = [p for p, _ in norm]
    value_axes = [v for _, v in norm]
    out: List[Dict[str, Any]] = []
    for combo in itertools.product(*value_axes):
        out.append(dict(zip(paths, combo)))
    return out


def _set_path(d: Any, path: str, value: Any) -> None:
    """Set `d[path] = value` using a dotted path. Integer parts index lists.

    Raises KeyError / IndexError / TypeError with the offending segment
    surfaced so the caller can fix the grid.
    """
    parts = path.split(".")
    cur: Any = d
    for i, part in enumerate(parts[:-1]):
        nxt: Any
        if isinstance(cur, list):
            try:
                idx = int(part)
            except ValueError as exc:
                raise KeyError(
                    f"path segment '{part}' at depth {i} expects an integer "
                    f"index into a list (full path: {path!r})"
                ) from exc
            if idx < 0 or idx >= len(cur):
                raise IndexError(
                    f"index {idx} out of range at depth {i} (len={len(cur)}, path={path!r})"
                )
            nxt = cur[idx]
        elif isinstance(cur, dict):
            if part not in cur:
                raise KeyError(
                    f"key '{part}' missing at depth {i} (available: "
                    f"{sorted(cur.keys())}, path={path!r})"
                )
            nxt = cur[part]
        else:
            raise TypeError(
                f"cannot descend into {type(cur).__name__} at depth {i} "
                f"(path={path!r})"
            )
        cur = nxt

    last = parts[-1]
    if isinstance(cur, list):
        try:
            idx = int(last)
        except ValueError as exc:
            raise KeyError(
                f"path tail '{last}' must be int for list (path={path!r})"
            ) from exc
        if idx < 0 or idx >= len(cur):
            raise IndexError(
                f"index {idx} out of range at tail (len={len(cur)}, path={path!r})"
            )
        cur[idx] = value
    elif isinstance(cur, dict):
        # Dict: allow creating new keys (e.g. flipping `stops.stop_loss=null` to a dict
        # would have failed earlier; we only accept setting existing keys here).
        if last not in cur:
            raise KeyError(
                f"tail key '{last}' missing (available: {sorted(cur.keys())}, "
                f"path={path!r})"
            )
        cur[last] = value
    else:
        raise TypeError(
            f"cannot set on {type(cur).__name__} (path={path!r})"
        )


def _apply_point(base_dict: Dict[str, Any], point: Dict[str, Any]) -> StrategySpec:
    """Deep-copy base, apply each path -> value, re-validate as StrategySpec."""
    d = copy.deepcopy(base_dict)
    for path, value in point.items():
        _set_path(d, path, value)
    return StrategySpec.model_validate(d)


# ─── Result types ───────────────────────────────────────────────────────


@dataclass
class CombinationRow:
    point: Dict[str, Any]
    metrics: Dict[str, Any]
    significance: Dict[str, Any]
    veto_reason: Optional[str] = None
    score: Optional[float] = None


@dataclass
class OptimizeResult:
    opt_id: str
    project_id: str
    dataset_id: str
    base_spec: Dict[str, Any]
    grid: Dict[str, List[Any]]
    score_metric: str
    n_combinations: int
    n_passed: int
    rows: List[Dict[str, Any]]
    top_n: List[Dict[str, Any]]
    robust_region: Dict[str, Any]
    best_in_robust: Optional[Dict[str, Any]]
    param_sensitivity: Dict[str, Any]
    elapsed_sec: float
    created_at: str
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ─── Veto + scoring ─────────────────────────────────────────────────────


def _veto(
    metrics: Dict[str, Any],
    significance: Dict[str, Any],
    *,
    min_trades: int,
    max_dd_floor: float,
) -> Optional[str]:
    """Return None if the row passes vetos, else a short reason string.

    `max_dd_floor` is a *negative* number (e.g. -0.50 = drawdown floor at 50%).
    Anything worse (more negative) is vetoed.
    """
    n = metrics.get("num_trades")
    if n is None or int(n) < min_trades:
        return f"too few trades ({n} < {min_trades})"
    sharpe = metrics.get("sharpe")
    if sharpe is None:
        return "sharpe undefined"
    mdd = metrics.get("max_drawdown")
    if mdd is None:
        return "max_drawdown undefined"
    if float(mdd) < max_dd_floor:
        return f"drawdown {float(mdd):.3f} below floor {max_dd_floor}"
    pf = metrics.get("profit_factor")
    if pf is not None and float(pf) <= 0:
        return f"profit_factor {pf} non-positive"
    return None


def _score(metrics: Dict[str, Any], score_metric: str) -> Optional[float]:
    v = metrics.get(score_metric)
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


# ─── Robust region + sensitivity ────────────────────────────────────────


def _marginal_means(
    rows: List[CombinationRow],
    paths: List[str],
) -> Dict[str, Dict[Any, float]]:
    """For each path, group passing rows by that path's value and take the
    mean score. Ignores vetoed rows."""
    out: Dict[str, Dict[Any, float]] = {}
    for path in paths:
        bucket: Dict[Any, List[float]] = {}
        for r in rows:
            if r.score is None or r.veto_reason is not None:
                continue
            v = r.point.get(path)
            bucket.setdefault(v, []).append(r.score)
        out[path] = {k: float(np.mean(vals)) for k, vals in bucket.items() if vals}
    return out


def _robust_region(
    rows: List[CombinationRow],
    norm_grid: List[Tuple[str, List[Any]]],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Identify a robust region by per-param marginal scores.

    Strategy:
        For each varied parameter, sort its candidate values, compute the
        marginal mean score, and select the maximal contiguous run whose
        scores are all ≥ the 75th percentile of marginal scores for that
        param. Numeric values are sorted numerically; non-numeric values
        are sorted lexicographically with no contiguity constraint.

    Returns (robust_region_dict, sensitivity_dict).
        robust_region[path] -> {"values": [...], "mean_score": float}
        sensitivity[path]   -> {"std_score": float, "range_score": float}
    """
    paths = [p for p, _ in norm_grid]
    margins = _marginal_means(rows, paths)

    region: Dict[str, Any] = {}
    sens: Dict[str, Any] = {}

    for path, axis in norm_grid:
        m = margins.get(path) or {}
        if not m:
            region[path] = {"values": [], "mean_score": None}
            sens[path] = {"std_score": None, "range_score": None}
            continue

        # Sort by axis order if numeric; falls back to lex order.
        try:
            sorted_vals = sorted(m.keys(), key=lambda x: float(x))
            numeric = True
        except (TypeError, ValueError):
            sorted_vals = sorted(m.keys(), key=lambda x: str(x))
            numeric = False

        scores = np.array([m[v] for v in sorted_vals], dtype=float)
        threshold = float(np.percentile(scores, 75))

        if numeric:
            # Find longest contiguous run with score >= threshold.
            best_run: List[int] = []
            cur_run: List[int] = []
            for i, s in enumerate(scores):
                if s >= threshold:
                    cur_run.append(i)
                    if len(cur_run) > len(best_run):
                        best_run = list(cur_run)
                else:
                    cur_run = []
            chosen_idx = best_run if best_run else [int(np.argmax(scores))]
        else:
            # Non-numeric: just pick all values at-or-above the threshold.
            chosen_idx = [i for i, s in enumerate(scores) if s >= threshold]
            if not chosen_idx:
                chosen_idx = [int(np.argmax(scores))]

        chosen_vals = [sorted_vals[i] for i in chosen_idx]
        region[path] = {
            "values": chosen_vals,
            "mean_score": float(np.mean([m[v] for v in chosen_vals])),
            "all_marginal_scores": {str(v): m[v] for v in sorted_vals},
        }
        sens[path] = {
            "std_score": float(scores.std(ddof=0)),
            "range_score": float(scores.max() - scores.min()),
        }

    return region, sens


def _best_in_region(
    rows: List[CombinationRow],
    region: Dict[str, Any],
) -> Optional[CombinationRow]:
    """Pick the highest-score passing row whose every param value is inside
    the robust region. Falls back to global best-passing if no row qualifies.
    """
    candidates = [r for r in rows if r.score is not None and r.veto_reason is None]
    if not candidates:
        return None

    in_region = []
    for r in candidates:
        ok = True
        for path, info in region.items():
            allowed = info.get("values") or []
            if not allowed:
                continue
            if r.point.get(path) not in allowed:
                ok = False
                break
        if ok:
            in_region.append(r)

    pool = in_region or candidates
    return max(pool, key=lambda r: r.score)  # type: ignore[arg-type]


# ─── Main entry ─────────────────────────────────────────────────────────


def optimize(
    dataset_id: str,
    base_spec: StrategySpec,
    grid: Dict[str, Sequence[Any]],
    *,
    score_metric: str = "sharpe",
    min_trades: int = 20,
    max_dd_floor: float = -0.50,
    top_n: int = 10,
    max_combinations: int = 500,
    init_cash: float = 10_000.0,
    persist: bool = True,
) -> OptimizeResult:
    """Run a vectorised parameter sweep + robust-region selection.

    Args:
        dataset_id: dataset to backtest against.
        base_spec: the spec all grid points override.
        grid: {dotted_path: [values]} — Cartesian-producted internally.
        score_metric: which metric to rank by. Common: "sharpe", "calmar",
            "sortino", "total_return".
        min_trades: vetoed below this. Defaults to 20 (statistical floor).
        max_dd_floor: vetoed if max_drawdown < this (negative). Default -0.50.
        top_n: how many top rows to return in the summary.
        max_combinations: hard cap to prevent runaway sweeps.
        init_cash: starting capital for each backtest.
        persist: write `opt_<id>.json` summary on success.

    Raises:
        ValueError on invalid grid, unknown dataset, or bad spec.
    """
    t0 = time.perf_counter()

    norm = _validate_grid(grid, max_combinations)
    points = _materialise_grid(norm)

    # Resolve project once so we know where to persist.
    found = storage._find_dataset_project(dataset_id)
    if found is None:
        raise ValueError(f"Dataset {dataset_id} not found")
    project_id, _ = found

    base_dict = json.loads(base_spec.model_dump_json())

    rows: List[CombinationRow] = []
    for point in points:
        try:
            spec_i = _apply_point(base_dict, point)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            rows.append(CombinationRow(
                point=point,
                metrics={"num_trades": 0},
                significance={"n_trades": 0},
                veto_reason=f"spec invalid: {exc.__class__.__name__}: {exc}",
                score=None,
            ))
            continue

        try:
            res: BacktestResult = run_backtest(
                dataset_id, spec_i,
                init_cash=init_cash,
                persist=False,
            )
        except Exception as exc:  # vbt occasionally raises on degenerate sigs
            rows.append(CombinationRow(
                point=point,
                metrics={"num_trades": 0},
                significance={"n_trades": 0},
                veto_reason=f"backtest failed: {exc.__class__.__name__}",
                score=None,
            ))
            continue

        veto = _veto(
            res.metrics, res.significance,
            min_trades=min_trades, max_dd_floor=max_dd_floor,
        )
        score = _score(res.metrics, score_metric) if veto is None else None
        rows.append(CombinationRow(
            point=point,
            metrics=res.metrics,
            significance=res.significance,
            veto_reason=veto,
            score=score,
        ))

    # Rank passing rows by score (None last).
    passing = [r for r in rows if r.score is not None and r.veto_reason is None]
    passing.sort(key=lambda r: r.score, reverse=True)  # type: ignore[arg-type]

    region, sensitivity = _robust_region(rows, norm)
    best_in_region = _best_in_region(rows, region)

    elapsed = time.perf_counter() - t0
    opt_id = _opt_id()

    notes: List[str] = []
    if not passing:
        notes.append(
            f"No combinations passed vetos (min_trades={min_trades}, "
            f"max_dd_floor={max_dd_floor}). Try widening the grid or "
            "lowering thresholds."
        )

    result = OptimizeResult(
        opt_id=opt_id,
        project_id=project_id,
        dataset_id=dataset_id,
        base_spec=base_dict,
        grid={p: list(v) for p, v in norm},
        score_metric=score_metric,
        n_combinations=len(rows),
        n_passed=len(passing),
        rows=[
            {
                "point": r.point,
                "score": r.score,
                "veto_reason": r.veto_reason,
                "metrics": r.metrics,
                "significance": r.significance,
            }
            for r in rows
        ],
        top_n=[
            {
                "point": r.point,
                "score": r.score,
                "metrics": r.metrics,
                "significance": r.significance,
            }
            for r in passing[: max(1, top_n)]
        ],
        robust_region=region,
        best_in_robust=(
            {
                "point": best_in_region.point,
                "score": best_in_region.score,
                "metrics": best_in_region.metrics,
                "significance": best_in_region.significance,
            }
            if best_in_region is not None
            else None
        ),
        param_sensitivity=sensitivity,
        elapsed_sec=float(elapsed),
        created_at=datetime.now(timezone.utc).isoformat(),
        notes=notes,
    )

    if persist:
        out = _opt_dir(project_id) / f"{opt_id}.json"
        out.write_text(
            json.dumps(result.to_dict(), indent=2, default=str),
            encoding="utf-8",
        )

    return result


def load_optimization_summary(project_id: str, opt_id: str) -> Optional[Dict[str, Any]]:
    p = _opt_dir(project_id) / f"{opt_id}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


# ─── CLI smoke ──────────────────────────────────────────────────────────


def _smoke() -> None:
    """`python -m app.optimize` — sweeps RSI thresholds on synthetic data
    persisted via storage so the full code path (grid expansion, mutation,
    veto, robust region, persistence) is exercised."""
    import tempfile
    import pandas as pd
    from .strategies import CondGroup, Condition

    # 1. Build + register a synthetic dataset via storage's real ingest path.
    np.random.seed(11)
    n = 1500
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

    project = storage.create_project(name="opt smoke project")
    project_id = project.id
    with tempfile.NamedTemporaryFile(
        suffix=".csv", delete=False
    ) as tmp:
        tmp_path = Path(tmp.name)
    df.to_csv(tmp_path, index=False)
    ds = storage.ingest_and_store_dataset(project_id, "smoke.csv", tmp_path)
    try:
        tmp_path.unlink(missing_ok=True)
    except Exception:
        pass
    if ds is None:
        raise RuntimeError("ingest failed in smoke")
    dataset_id = ds.id
    print(f"smoke project={project_id} dataset={dataset_id}")

    base_spec = StrategySpec(
        name="rsi_meanrev_opt_smoke",
        market="crypto",
        entries=CondGroup(all_of=[
            Condition(indicator="rsi", params={"period": 14}, op="<", value=30),
        ]),
        exits=CondGroup(all_of=[
            Condition(indicator="rsi", params={"period": 14}, op=">", value=70),
        ]),
    )

    grid = {
        "entries.all_of.0.value": [20, 25, 30, 35],
        "exits.all_of.0.value": [60, 65, 70, 75],
    }

    res = optimize(
        dataset_id, base_spec, grid,
        score_metric="sharpe",
        min_trades=3,           # synthetic data is small
        max_dd_floor=-0.95,     # let almost everything through
        top_n=5,
        persist=True,
    )

    print(f"combinations={res.n_combinations}  passed={res.n_passed}  "
          f"elapsed={res.elapsed_sec:.2f}s")
    if res.top_n:
        best = res.top_n[0]
        print("best top-N point:", best["point"], "score=", best["score"])
    print("robust region:", {k: v["values"] for k, v in res.robust_region.items()})
    if res.best_in_robust:
        print("best inside robust:", res.best_in_robust["point"],
              "score=", res.best_in_robust["score"])

    # Reload from disk.
    again = load_optimization_summary(res.project_id, res.opt_id)
    assert again is not None and again["opt_id"] == res.opt_id
    print(f"persistence verified: {res.opt_id}")
    print("OPTIMIZE SMOKE OK")


if __name__ == "__main__":
    _smoke()
