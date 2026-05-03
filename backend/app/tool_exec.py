"""Tool dispatcher called by the orchestrator.

Every tool name exposed via :func:`app.tools.all_tools` maps here. Phase 6
covers the 15 indicator tools; Phase 7 adds 5 backtest / optimise /
validate / score tools against the same dispatcher without touching the
orchestrator.

The dispatcher is deliberately defensive — any exception gets wrapped in a
``{"error": "…"}`` payload so the LLM sees a clean tool_result instead of
the stream dying mid-turn.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, Optional

from . import storage
from .data import load_dataset
from .indicators import IndicatorError, compute as compute_indicator
from .paths import workspace_dir


_INDICATOR_PREFIX = "compute_"

# Absolute base for report URLs the LLM emits to chat. Bare `/api/...`
# paths aren't clickable in markdown — turning them into full
# `http://127.0.0.1:8765/api/...` links makes them work in the chat
# bubble AND in the artifacts panel iframe.
_REPORT_BASE_URL = "http://127.0.0.1:8765"

# Phase 7 tool names routed in `run_tool`.
_BACKTEST_TOOLS = {
    "run_backtest",
    "optimize_strategy",
    "walk_forward",
    "monte_carlo",
    "score_strategy",
}

# Phase 8 tool names routed in `run_tool`.
_REPORT_TOOLS = {"render_report"}

# Phase 9 tool names routed in `run_tool`.
_LIBRARY_TOOLS = {"save_strategy", "load_strategy", "list_strategies"}

# Phase 7+ token-saver: one tool, full pipeline, single LLM round-trip.
_PIPELINE_TOOLS = {"run_full_pipeline"}


def _round_floats(obj: Any) -> Any:
    """Walk a JSON-shaped payload and round every float to 2 decimals.

    Centralises the "no walls of decimals in chat output" policy — every
    tool_result the LLM (and the chat UI) sees passes through this on
    its way out. Doesn't touch ints, bools, strings, None.
    """
    import math

    if isinstance(obj, dict):
        return {k: _round_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_round_floats(v) for v in obj]
    if isinstance(obj, tuple):
        return tuple(_round_floats(v) for v in obj)
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, float):
        if not math.isfinite(obj):
            return None
        return round(obj, 2)
    return obj


def _tool_result_ok(payload: Any) -> Dict[str, Any]:
    return {"ok": True, "output": _round_floats(payload)}


def _tool_result_err(message: str) -> Dict[str, Any]:
    return {"ok": False, "error": message}


async def run_tool(
    name: str,
    input_: Dict[str, Any],
    *,
    permission_mode: str = "accept-edits",
) -> Dict[str, Any]:
    """Dispatch a single tool call. Never raises — always returns a dict."""
    try:
        if name.startswith(_INDICATOR_PREFIX):
            return await _run_indicator(name[len(_INDICATOR_PREFIX) :], input_)
        if name in _BACKTEST_TOOLS:
            return await _run_backtest_tool(name, input_)
        if name in _REPORT_TOOLS:
            return await _run_report_tool(name, input_)
        if name in _LIBRARY_TOOLS:
            return await _run_library_tool(name, input_)
        if name in _PIPELINE_TOOLS:
            return await _run_full_pipeline(input_)

        from .agent_tools import AGENT_TOOLS, run_agent_tool
        if name in AGENT_TOOLS:
            return await run_agent_tool(name, input_, permission_mode=permission_mode)

        return _tool_result_err(f"Unknown tool: {name}")
    except Exception as exc:  # noqa: BLE001 — boundary
        return _tool_result_err(f"Tool crashed: {exc}")


async def _run_indicator(indicator_name: str, input_: Dict[str, Any]) -> Dict[str, Any]:
    dataset_id = input_.get("dataset_id")
    if not dataset_id or not isinstance(dataset_id, str):
        return _tool_result_err("Missing required `dataset_id`")

    project_id = _resolve_dataset_project(dataset_id)
    if project_id is None:
        return _tool_result_err(f"Dataset {dataset_id} not found")

    # Load parquet off the event loop — indicators are pandas-heavy and sync.
    def _compute() -> Dict[str, Any]:
        path = storage.dataset_path(project_id, dataset_id)
        if not path.exists():
            raise FileNotFoundError(str(path))
        df = load_dataset(path)
        params = {k: v for k, v in input_.items() if k != "dataset_id"}
        result = compute_indicator(df, indicator_name, params)
        # Truncate — tool_result payloads must stay small so they fit in context.
        tail = result.tail(50)
        return {
            "indicator": indicator_name,
            "params": params,
            "rows": len(result),
            "columns": list(result.columns),
            "tail": [
                {c: _jsonable(tail.iloc[i][c]) for c in result.columns}
                for i in range(len(tail))
            ],
        }

    try:
        payload = await asyncio.to_thread(_compute)
        return _tool_result_ok(payload)
    except IndicatorError as exc:
        return _tool_result_err(f"Indicator failed: {exc}")
    except FileNotFoundError:
        return _tool_result_err(f"Dataset {dataset_id} parquet missing on disk")


def _resolve_dataset_project(dataset_id: str) -> str | None:
    """Scan projects for one that owns ``dataset_id``. O(#projects) but dataset
    counts stay tiny in practice, so this keeps the tool layer stateless."""
    for project in storage.list_projects():
        datasets = storage.list_datasets(project.id) or []
        if any(d.id == dataset_id for d in datasets):
            return project.id
    return None


def _jsonable(v: Any) -> Any:
    """Coerce pandas/numpy scalars to JSON-safe primitives, rounding
    floats to 2 decimal places (project-wide chat-output policy)."""
    if v is None:
        return None
    if hasattr(v, "isoformat"):
        try:
            return v.isoformat()
        except Exception:
            pass
    if hasattr(v, "item"):
        try:
            v = v.item()
        except Exception:
            pass
    if isinstance(v, float):
        import math

        if not math.isfinite(v):
            return None
        return round(v, 2)
    return v


# ─── Phase 7 — backtest / optimise / validate / score ───────────────────
#
# The heavy modules (`backtest`, `optimize`, `validate`, `scoring`) are
# imported lazily inside the dispatcher so `import app` at FastAPI startup
# doesn't pay the vectorbt+numba warmup cost unless a chat actually calls
# a Phase 7 tool.


async def _run_backtest_tool(name: str, input_: Dict[str, Any]) -> Dict[str, Any]:
    if name == "run_backtest":
        return await asyncio.to_thread(_do_run_backtest, input_)
    if name == "optimize_strategy":
        return await asyncio.to_thread(_do_optimize, input_)
    if name == "walk_forward":
        return await asyncio.to_thread(_do_walk_forward, input_)
    if name == "monte_carlo":
        return await asyncio.to_thread(_do_monte_carlo, input_)
    if name == "score_strategy":
        return await asyncio.to_thread(_do_score_strategy, input_)
    return _tool_result_err(f"Unrouted backtest tool: {name}")


def _require_spec(input_: Dict[str, Any], key: str):
    """Parse a StrategySpec from the tool input, raising a clean ValueError."""
    from .strategies import StrategySpec

    raw = input_.get(key)
    if raw is None:
        raise ValueError(f"Missing required `{key}`")
    if not isinstance(raw, dict):
        raise ValueError(f"`{key}` must be a JSON object, got {type(raw).__name__}")
    try:
        return StrategySpec.model_validate(raw)
    except Exception as exc:
        raise ValueError(f"Invalid `{key}`: {exc}") from exc


def _require_dataset_id(input_: Dict[str, Any]) -> str:
    ds = input_.get("dataset_id")
    if not isinstance(ds, str) or not ds:
        raise ValueError("Missing required `dataset_id`")
    return ds


def _compact_metrics(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """Keep only fields the LLM actually reads, to minimise tool_result bytes."""
    keep = {
        "total_return", "cagr", "sharpe", "sortino", "max_drawdown",
        "calmar", "num_trades", "win_rate", "profit_factor", "avg_trade",
        "expectancy", "best_trade", "worst_trade", "duration_years",
    }
    return {k: v for k, v in metrics.items() if k in keep}


def _do_run_backtest(input_: Dict[str, Any]) -> Dict[str, Any]:
    try:
        dataset_id = _require_dataset_id(input_)
        spec = _require_spec(input_, "strategy_spec")
        init_cash = float(input_.get("init_cash", 10_000.0))
    except ValueError as exc:
        return _tool_result_err(str(exc))

    from .backtest import run_backtest

    try:
        res = run_backtest(dataset_id, spec, init_cash=init_cash, persist=True)
    except Exception as exc:
        return _tool_result_err(f"Backtest failed: {exc.__class__.__name__}: {exc}")

    return _tool_result_ok({
        "backtest_id": res.bt_id,
        "project_id": res.project_id,
        "dataset_id": res.dataset_id,
        "metrics": _compact_metrics(res.metrics),
        "significance": res.significance,
        "n_bars": res.n_bars,
        "notes": res.notes,
    })


def _do_optimize(input_: Dict[str, Any]) -> Dict[str, Any]:
    try:
        dataset_id = _require_dataset_id(input_)
        base_spec = _require_spec(input_, "base_spec")
        grid = input_.get("grid")
        if not isinstance(grid, dict) or not grid:
            raise ValueError("`grid` must be a non-empty object of {path: [values]}")
    except ValueError as exc:
        return _tool_result_err(str(exc))

    from .optimize import optimize

    try:
        res = optimize(
            dataset_id, base_spec, grid,
            score_metric=str(input_.get("score_metric", "sharpe")),
            min_trades=int(input_.get("min_trades", 20)),
            max_dd_floor=float(input_.get("max_dd_floor", -0.50)),
            top_n=int(input_.get("top_n", 10)),
            max_combinations=int(input_.get("max_combinations", 500)),
            init_cash=float(input_.get("init_cash", 10_000.0)),
            persist=True,
        )
    except Exception as exc:
        return _tool_result_err(f"Optimise failed: {exc.__class__.__name__}: {exc}")

    # Keep payload compact — drop per-row details, keep top_n + robust region.
    return _tool_result_ok({
        "opt_id": res.opt_id,
        "project_id": res.project_id,
        "dataset_id": res.dataset_id,
        "score_metric": res.score_metric,
        "n_combinations": res.n_combinations,
        "n_passed": res.n_passed,
        "elapsed_sec": res.elapsed_sec,
        "top_n": [
            {"point": t["point"], "score": t["score"],
             "metrics": _compact_metrics(t.get("metrics") or {})}
            for t in res.top_n
        ],
        "robust_region": {
            k: {"values": v.get("values"), "mean_score": v.get("mean_score")}
            for k, v in res.robust_region.items()
        },
        "best_in_robust": (
            {
                "point": res.best_in_robust["point"],
                "score": res.best_in_robust["score"],
                "metrics": _compact_metrics(
                    res.best_in_robust.get("metrics") or {}),
            }
            if res.best_in_robust is not None else None
        ),
        "param_sensitivity": res.param_sensitivity,
        "notes": res.notes,
    })


def _do_walk_forward(input_: Dict[str, Any]) -> Dict[str, Any]:
    try:
        dataset_id = _require_dataset_id(input_)
        base_spec = _require_spec(input_, "base_spec")
    except ValueError as exc:
        return _tool_result_err(str(exc))

    from .validate import walk_forward

    grid = input_.get("grid")
    if grid is not None and (not isinstance(grid, dict) or not grid):
        return _tool_result_err("If provided, `grid` must be a non-empty object")

    try:
        res = walk_forward(
            dataset_id, base_spec,
            grid=grid,
            n_folds=int(input_.get("n_folds", 5)),
            is_oos_split=float(input_.get("is_oos_split", 0.7)),
            mode=str(input_.get("mode", "rolling")),
            score_metric=str(input_.get("score_metric", "sharpe")),
            min_trades=int(input_.get("min_trades", 10)),
            max_dd_floor=float(input_.get("max_dd_floor", -0.50)),
            max_combinations=int(input_.get("max_combinations", 200)),
            init_cash=float(input_.get("init_cash", 10_000.0)),
            persist=True,
        )
    except Exception as exc:
        return _tool_result_err(
            f"Walk-forward failed: {exc.__class__.__name__}: {exc}")

    return _tool_result_ok({
        "walk_forward_id": res.val_id,
        "project_id": res.project_id,
        "dataset_id": res.dataset_id,
        "n_folds": res.n_folds,
        "mode": res.fold_mode,
        "is_oos_split": res.is_oos_split,
        "score_metric": res.score_metric,
        "wfe": res.wfe,
        "verdict": res.verdict,
        "aggregate": res.aggregate,
        "folds": [
            {
                "fold_id": f["fold_id"],
                "chosen_point": f.get("chosen_point") or {},
                "in_sample_sharpe": (f.get("in_sample_metrics") or {}).get("sharpe"),
                "out_sample_sharpe": (f.get("out_sample_metrics") or {}).get("sharpe"),
                "in_sample_total_return": (f.get("in_sample_metrics") or {}).get("total_return"),
                "out_sample_total_return": (f.get("out_sample_metrics") or {}).get("total_return"),
                "in_sample_start": f.get("in_sample_start"),
                "out_sample_end": f.get("out_sample_end"),
            }
            for f in res.folds
        ],
        "elapsed_sec": res.elapsed_sec,
    })


def _do_monte_carlo(input_: Dict[str, Any]) -> Dict[str, Any]:
    try:
        dataset_id = _require_dataset_id(input_)
        spec = _require_spec(input_, "strategy_spec")
    except ValueError as exc:
        return _tool_result_err(str(exc))

    from .validate import monte_carlo

    try:
        res = monte_carlo(
            dataset_id, spec,
            n_iterations=int(input_.get("n_iterations", 2000)),
            init_cash=float(input_.get("init_cash", 10_000.0)),
            seed=(int(input_["seed"]) if "seed" in input_ else None),
            persist=True,
        )
    except Exception as exc:
        return _tool_result_err(
            f"Monte Carlo failed: {exc.__class__.__name__}: {exc}")

    return _tool_result_ok({
        "monte_carlo_id": res.val_id,
        "project_id": res.project_id,
        "dataset_id": res.dataset_id,
        "n_iterations": res.n_iterations,
        "n_trades": res.n_trades,
        "p_value_positive_mean": res.p_value_positive_mean,
        "p_value_beats_zero_return": res.p_value_beats_zero_return,
        "expected_total_return": res.expected_total_return,
        "expected_max_drawdown": res.expected_max_drawdown,
        "verdict": res.verdict,
        "percentiles": res.percentiles,
        "elapsed_sec": res.elapsed_sec,
    })


# ─── ID resolution for score_strategy ───────────────────────────────────


def _find_artifact(subdir: str, file_id: str) -> Optional[Path]:
    """Find `<workspace>/<subdir>/<file_id>.json` across all projects."""
    for project in storage.list_projects():
        p = workspace_dir(project.id) / subdir / f"{file_id}.json"
        if p.exists():
            return p
    return None


def _list_recent_artifact_ids(subdir: str, prefix: str, limit: int = 5) -> list[str]:
    """Return the most-recent artifact ids matching ``prefix`` across all projects.

    Used by error helpers to nudge the LLM toward a real id when it has
    fabricated one — particularly common when ``score_strategy`` or
    ``render_report`` is called in the same turn as the tool that
    produces the id they need.
    """
    candidates: list[tuple[float, str]] = []
    for project in storage.list_projects():
        d = workspace_dir(project.id) / subdir
        if not d.exists():
            continue
        for f in d.glob(f"{prefix}_*.json"):
            try:
                candidates.append((f.stat().st_mtime, f.stem))
            except OSError:
                continue
    candidates.sort(reverse=True)
    return [stem for _, stem in candidates[:limit]]


def _id_not_found_msg(kind: str, supplied_id: str, subdir: str) -> str:
    """Friendly error that hints at fabrication and lists real recent ids."""
    prefix = supplied_id.split("_", 1)[0] if "_" in supplied_id else ""
    if prefix in {"bt", "mc", "wf", "opt", "rp"}:
        recent = _list_recent_artifact_ids(subdir, prefix)
    else:
        recent = []
    base = (
        f"{kind} {supplied_id!s} not found. Do not invent IDs — copy the "
        f"exact value from the prior tool_result that produced it."
    )
    if recent:
        base += f" Recent {kind} IDs you may have meant: {recent}."
    return base


def _do_score_strategy(input_: Dict[str, Any]) -> Dict[str, Any]:
    bt_id = input_.get("backtest_id")
    if not isinstance(bt_id, str) or not bt_id:
        return _tool_result_err("Missing required `backtest_id`")

    bt_path = _find_artifact("backtests", bt_id)
    if bt_path is None:
        return _tool_result_err(_id_not_found_msg("Backtest", bt_id, "backtests"))

    try:
        bt = json.loads(bt_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return _tool_result_err(f"Could not read backtest: {exc}")

    mc: Optional[Dict[str, Any]] = None
    wf: Optional[Dict[str, Any]] = None

    mc_id = input_.get("monte_carlo_id")
    if isinstance(mc_id, str) and mc_id:
        mc_path = _find_artifact("validations", mc_id)
        if mc_path is None:
            return _tool_result_err(_id_not_found_msg("Monte Carlo", mc_id, "validations"))
        try:
            mc = json.loads(mc_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return _tool_result_err(f"Could not read Monte Carlo: {exc}")

    wf_id = input_.get("walk_forward_id")
    if isinstance(wf_id, str) and wf_id:
        wf_path = _find_artifact("validations", wf_id)
        if wf_path is None:
            return _tool_result_err(_id_not_found_msg("Walk-forward", wf_id, "validations"))
        try:
            wf = json.loads(wf_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return _tool_result_err(f"Could not read Walk-forward: {exc}")

    from .scoring import score_backtest

    result = score_backtest(
        bt.get("metrics") or {},
        bt.get("significance") or {},
        mc=mc,
        wf=wf,
    )

    # ── Phase 9 — save-to-library hook ──────────────────────────────────
    # Silent auto-save on every score_strategy call would spam the
    # library. Instead we emit a `save_suggestion` when the grade is
    # library-worthy, and optionally auto-save when the caller opts in
    # with `save_as="name"`.
    save_suggestion: Optional[Dict[str, Any]] = None
    auto_saved: Optional[Dict[str, Any]] = None

    library_worthy = _is_library_worthy(result.grade)
    if library_worthy:
        spec = bt.get("spec_used") or bt.get("strategy_spec") or {}
        save_suggestion = {
            "suggested_name": _suggest_strategy_name(spec, bt_id),
            "reason": (
                f"Grade {result.grade} ({result.verdict}) — worth saving "
                f"to the library for reuse / comparison."
            ),
        }

        save_as = input_.get("save_as")
        if isinstance(save_as, str) and save_as.strip():
            auto_saved = _auto_save_after_score(
                bt=bt,
                bt_id=bt_id,
                name=save_as.strip(),
                description=input_.get("save_description"),
                grade=result.grade,
                verdict=result.verdict,
                score=float(result.score),
            )

    payload: Dict[str, Any] = {
        "backtest_id": bt_id,
        "monte_carlo_id": mc_id,
        "walk_forward_id": wf_id,
        "score": result.score,
        "grade": result.grade,
        "verdict": result.verdict,
        "headline": result.headline,
        "confidence": result.confidence,
        "in_sample_score": result.in_sample_score,
        "oos_adjustment": result.oos_adjustment,
        "vetos": [{"rule": v.rule, "message": v.message} for v in result.vetos],
        "components": [
            {"metric": c.metric, "raw_value": c.raw_value,
             "normalised": c.normalised, "weight": c.weight,
             "contribution": c.contribution}
            for c in result.components
        ],
        "notes": result.notes,
    }
    if save_suggestion is not None:
        payload["save_suggestion"] = save_suggestion
    if auto_saved is not None:
        payload["auto_saved"] = auto_saved
    return _tool_result_ok(payload)


# ─── Phase 9 auto-save helpers ─────────────────────────────────────────


# Grades we'll nudge the user to save. Anything C or below isn't worth
# cluttering the library with.
_LIBRARY_WORTHY_GRADES = {"A+", "A", "A-", "B+", "B", "B-"}


def _is_library_worthy(grade: Optional[str]) -> bool:
    return isinstance(grade, str) and grade in _LIBRARY_WORTHY_GRADES


def _suggest_strategy_name(spec: Dict[str, Any], bt_id: str) -> str:
    """Build a sensible default name from the spec. Falls back to `strat_<bt tail>`."""
    raw = spec.get("name") if isinstance(spec, dict) else None
    if isinstance(raw, str) and raw.strip():
        base = raw.strip()
    else:
        base = f"strategy_{bt_id[-6:]}"
    # Lowercase, hyphen/underscore-safe, trimmed.
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in base)
    return safe[:120] or f"strategy_{bt_id[-6:]}"


def _auto_save_after_score(
    *,
    bt: Dict[str, Any],
    bt_id: str,
    name: str,
    description: Any,
    grade: str,
    verdict: str,
    score: float,
) -> Dict[str, Any]:
    """Best-effort save. Returns a result dict — never raises into the tool layer."""
    spec = bt.get("spec_used") or bt.get("strategy_spec")
    if not isinstance(spec, dict):
        return {"ok": False, "error": "Backtest is missing `spec_used`"}

    project_id = bt.get("project_id")
    if not isinstance(project_id, str):
        return {"ok": False, "error": "Backtest is missing `project_id`"}

    desc = description if isinstance(description, str) else None

    try:
        saved = storage.create_strategy(
            project_id,
            name=name,
            spec=spec,
            description=desc,
            source_backtest_id=bt_id,
            grade=grade,
            verdict=verdict,
            score=score,
        )
    except storage.StrategyNameConflict as exc:
        return {"ok": False, "error": str(exc)}
    if saved is None:
        return {"ok": False, "error": f"Project {project_id} not found"}

    return {
        "ok": True,
        "strategy_id": saved.id,
        "name": saved.name,
        "project_id": saved.project_id,
    }


# ─── Phase 8 — report rendering ────────────────────────────────────────


async def _run_report_tool(name: str, input_: Dict[str, Any]) -> Dict[str, Any]:
    if name == "render_report":
        # HTML rendering is pure-python / synchronous — keep it off the loop.
        return await asyncio.to_thread(_do_render_report, input_)
    return _tool_result_err(f"Unrouted report tool: {name}")


def _do_render_report(input_: Dict[str, Any]) -> Dict[str, Any]:
    bt_id = input_.get("backtest_id")
    if not isinstance(bt_id, str) or not bt_id:
        return _tool_result_err("Missing required `backtest_id`")

    mc_id = input_.get("monte_carlo_id") or None
    wf_id = input_.get("walk_forward_id") or None
    opt_id = input_.get("optimization_id") or None
    for name, val in (("monte_carlo_id", mc_id), ("walk_forward_id", wf_id),
                      ("optimization_id", opt_id)):
        if val is not None and not isinstance(val, str):
            return _tool_result_err(f"`{name}` must be a string if supplied")

    # Pre-flight: detect fabricated IDs before invoking the heavier
    # ``reports.render_report`` so the model sees a hint with real recent
    # IDs to retry with, instead of a generic 'not found' error.
    if _find_artifact("backtests", bt_id) is None:
        return _tool_result_err(_id_not_found_msg("Backtest", bt_id, "backtests"))
    if mc_id and _find_artifact("validations", mc_id) is None:
        return _tool_result_err(_id_not_found_msg("Monte Carlo", mc_id, "validations"))
    if wf_id and _find_artifact("validations", wf_id) is None:
        return _tool_result_err(_id_not_found_msg("Walk-forward", wf_id, "validations"))
    if opt_id and _find_artifact("optimizations", opt_id) is None:
        return _tool_result_err(_id_not_found_msg("Optimization", opt_id, "optimizations"))

    from .reports import render_report

    try:
        meta = render_report(
            backtest_id=bt_id,
            monte_carlo_id=mc_id,
            walk_forward_id=wf_id,
            optimization_id=opt_id,
        )
    except ValueError as exc:
        return _tool_result_err(str(exc))
    except Exception as exc:
        return _tool_result_err(
            f"Report render failed: {exc.__class__.__name__}: {exc}")

    return _tool_result_ok({
        "report_id": meta.report_id,
        "project_id": meta.project_id,
        "title": meta.title,
        "grade": meta.grade,
        "verdict": meta.verdict,
        "score": meta.score,
        "sections": meta.sections,
        "html_url": f"{_REPORT_BASE_URL}/api/reports/{meta.report_id}",
        "pdf_url":  f"{_REPORT_BASE_URL}/api/reports/{meta.report_id}.pdf",
        "created_at": meta.created_at,
    })


# ─── Phase 9 — strategy library ────────────────────────────────────────


async def _run_library_tool(name: str, input_: Dict[str, Any]) -> Dict[str, Any]:
    if name == "save_strategy":
        return await asyncio.to_thread(_do_save_strategy, input_)
    if name == "load_strategy":
        return await asyncio.to_thread(_do_load_strategy, input_)
    if name == "list_strategies":
        return await asyncio.to_thread(_do_list_strategies, input_)
    return _tool_result_err(f"Unrouted library tool: {name}")


def _strategy_summary(s: "storage.SavedStrategy") -> Dict[str, Any]:
    """Slim dict for `list_strategies` — no spec payload."""
    return {
        "strategy_id": s.id,
        "project_id": s.project_id,
        "name": s.name,
        "description": s.description,
        "grade": s.grade,
        "verdict": s.verdict,
        "score": s.score,
        "source_backtest_id": s.source_backtest_id,
        "created_at": s.created_at,
        "updated_at": s.updated_at,
    }


def _strategy_full(s: "storage.SavedStrategy") -> Dict[str, Any]:
    """Full dict including the StrategySpec — for `load_strategy` + `save_strategy`."""
    return {**_strategy_summary(s), "strategy_spec": s.spec}


class SaveFromBacktestError(Exception):
    """Raised by :func:`save_strategy_from_backtest` for any non-conflict failure.

    Conflicts (duplicate name) surface as :class:`storage.StrategyNameConflict`
    directly — callers catch them separately to map to HTTP 409.
    """


def save_strategy_from_backtest(
    *,
    backtest_id: str,
    name: str,
    description: Optional[str] = None,
    monte_carlo_id: Optional[str] = None,
    walk_forward_id: Optional[str] = None,
) -> "storage.SavedStrategy":
    """Persist the strategy spec embedded in `backtest_id` as a library entry.

    Scoring is attempted (using optional MC/WF artifacts) so the saved row
    also carries `grade`/`verdict`/`score`. If scoring blows up, the entry
    is still saved without those fields.

    Raises:
        SaveFromBacktestError: validation / IO / missing-project failures.
        storage.StrategyNameConflict: if `name` already exists in the project.
    """
    if not isinstance(name, str) or not name.strip():
        raise SaveFromBacktestError("Missing required `name`")
    name = name.strip()
    if description is not None and not isinstance(description, str):
        raise SaveFromBacktestError("`description` must be a string if supplied")
    if not isinstance(backtest_id, str) or not backtest_id:
        raise SaveFromBacktestError("`backtest_id` must be a non-empty string")

    bt_path = _find_artifact("backtests", backtest_id)
    if bt_path is None:
        raise SaveFromBacktestError(f"Backtest {backtest_id} not found")
    try:
        bt = json.loads(bt_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SaveFromBacktestError(f"Could not read backtest: {exc}") from exc

    project_id = bt.get("project_id") or bt_path.parent.parent.name
    spec_dict = bt.get("spec_used") or bt.get("strategy_spec")
    if not isinstance(spec_dict, dict):
        raise SaveFromBacktestError(
            f"Backtest {backtest_id} is missing `spec_used` — cannot save"
        )

    mc_data: Optional[Dict[str, Any]] = None
    wf_data: Optional[Dict[str, Any]] = None
    if monte_carlo_id:
        mc_path = _find_artifact("validations", monte_carlo_id)
        if mc_path is None:
            raise SaveFromBacktestError(f"Monte Carlo {monte_carlo_id} not found")
        try:
            mc_data = json.loads(mc_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise SaveFromBacktestError(
                f"Could not read Monte Carlo: {exc}"
            ) from exc
    if walk_forward_id:
        wf_path = _find_artifact("validations", walk_forward_id)
        if wf_path is None:
            raise SaveFromBacktestError(
                f"Walk-forward {walk_forward_id} not found"
            )
        try:
            wf_data = json.loads(wf_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise SaveFromBacktestError(
                f"Could not read Walk-forward: {exc}"
            ) from exc

    grade: Optional[str] = None
    verdict: Optional[str] = None
    score: Optional[float] = None
    try:
        from .scoring import score_backtest

        result = score_backtest(
            bt.get("metrics") or {},
            bt.get("significance") or {},
            mc=mc_data,
            wf=wf_data,
        )
        grade = result.grade
        verdict = result.verdict
        score = float(result.score)
    except Exception:
        # Non-fatal — save without grade if scoring blows up.
        pass

    saved = storage.create_strategy(
        project_id,
        name=name,
        spec=spec_dict,
        description=description,
        source_backtest_id=backtest_id,
        grade=grade,
        verdict=verdict,
        score=score,
    )
    if saved is None:
        raise SaveFromBacktestError(f"Project {project_id} not found")
    return saved


def _do_save_strategy(input_: Dict[str, Any]) -> Dict[str, Any]:
    name = input_.get("name")
    if not isinstance(name, str) or not name.strip():
        return _tool_result_err("Missing required `name`")
    name = name.strip()
    description = input_.get("description")
    if description is not None and not isinstance(description, str):
        return _tool_result_err("`description` must be a string if supplied")

    bt_id = input_.get("backtest_id") or None
    raw_spec = input_.get("strategy_spec")
    explicit_project_id = input_.get("project_id") or None

    if bt_id:
        try:
            saved = save_strategy_from_backtest(
                backtest_id=bt_id,
                name=name,
                description=description,
                monte_carlo_id=input_.get("monte_carlo_id") or None,
                walk_forward_id=input_.get("walk_forward_id") or None,
            )
        except SaveFromBacktestError as exc:
            return _tool_result_err(str(exc))
        except storage.StrategyNameConflict as exc:
            return _tool_result_err(str(exc))
        return _tool_result_ok(_strategy_full(saved))

    # Raw-spec branch (AI builds a spec and saves without running a backtest).
    if not isinstance(raw_spec, dict):
        return _tool_result_err(
            "Provide either `backtest_id` or a `strategy_spec` object"
        )
    if not isinstance(explicit_project_id, str) or not explicit_project_id:
        return _tool_result_err(
            "`project_id` is required when saving from a raw `strategy_spec`"
        )
    try:
        from .strategies import StrategySpec

        parsed = StrategySpec.model_validate(raw_spec)
        spec_dict = parsed.model_dump()
    except Exception as exc:
        return _tool_result_err(f"Invalid `strategy_spec`: {exc}")

    try:
        saved = storage.create_strategy(
            explicit_project_id,
            name=name,
            spec=spec_dict,
            description=description,
            source_backtest_id=None,
            grade=None,
            verdict=None,
            score=None,
        )
    except storage.StrategyNameConflict as exc:
        return _tool_result_err(str(exc))
    if saved is None:
        return _tool_result_err(f"Project {explicit_project_id} not found")

    return _tool_result_ok(_strategy_full(saved))


def _do_load_strategy(input_: Dict[str, Any]) -> Dict[str, Any]:
    sid = input_.get("strategy_id")
    if not isinstance(sid, str) or not sid:
        return _tool_result_err("Missing required `strategy_id`")
    saved = storage.get_strategy(sid)
    if saved is None:
        return _tool_result_err(f"Strategy {sid} not found")
    return _tool_result_ok(_strategy_full(saved))


def _do_list_strategies(input_: Dict[str, Any]) -> Dict[str, Any]:
    project_id = input_.get("project_id") or None
    if project_id is not None and not isinstance(project_id, str):
        return _tool_result_err("`project_id` must be a string if supplied")

    if project_id:
        lst = storage.list_strategies(project_id)
        if lst is None:
            return _tool_result_err(f"Project {project_id} not found")
        strategies = lst
    else:
        # Aggregate across all projects.
        strategies = []
        for project in storage.list_projects():
            lst = storage.list_strategies(project.id) or []
            strategies.extend(lst)
        # Latest-first across the union.
        strategies.sort(
            key=lambda s: (s.updated_at or s.created_at),
            reverse=True,
        )

    return _tool_result_ok({
        "count": len(strategies),
        "strategies": [_strategy_summary(s) for s in strategies],
    })


# ─── Phase 7+: full-pipeline single tool ───────────────────────────────
#
# This is the diagram's "AI called only 2-3 times" guarantee. The model
# generates ONE strategy_spec, calls THIS tool once, and gets back a
# compact summary with grade + report_id. All intermediate tool I/O
# (indicators, optimisation grids, MC iterations, walk-forward folds)
# stay server-side — no token round-trips.


async def _run_full_pipeline(input_: Dict[str, Any]) -> Dict[str, Any]:
    return await asyncio.to_thread(_do_run_full_pipeline, input_)


def _do_run_full_pipeline(input_: Dict[str, Any]) -> Dict[str, Any]:
    """Run backtest → [optimize] → walk_forward → monte_carlo → score → render.

    Each step is optional via flags. The base ``strategy_spec`` is used
    for the in-sample backtest; if ``optimize`` is enabled, the best
    point's spec replaces it for downstream walk-forward + Monte-Carlo.
    """
    import time as _time

    started = _time.perf_counter()

    try:
        dataset_id = _require_dataset_id(input_)
        base_spec_dict = input_.get("strategy_spec")
        if not isinstance(base_spec_dict, dict):
            raise ValueError("Missing required `strategy_spec`")
    except ValueError as exc:
        return _tool_result_err(str(exc))

    init_cash = float(input_.get("init_cash", 10_000.0))
    do_optimize = input_.get("optimize")
    do_wf = bool(input_.get("walk_forward", True))
    do_mc = bool(input_.get("monte_carlo", True))
    do_render = bool(input_.get("render", True))

    summary: Dict[str, Any] = {
        "dataset_id": dataset_id,
        "stages": [],
    }

    # ── Stage 1: optional optimisation ─────────────────────────────────
    final_spec_dict = base_spec_dict
    optimization_id: Optional[str] = None
    opt_top_5: List[Dict[str, Any]] = []
    if do_optimize:
        try:
            from .strategies import StrategySpec

            base_spec = StrategySpec.model_validate(base_spec_dict)
        except Exception as exc:
            return _tool_result_err(f"Invalid `strategy_spec`: {exc}")

        grid = (
            do_optimize.get("grid")
            if isinstance(do_optimize, dict)
            else input_.get("optimize_grid")
        )
        if not isinstance(grid, dict) or not grid:
            return _tool_result_err(
                "When `optimize` is set, supply a `grid` mapping "
                "{dotted_path: [values]} (or pass `optimize_grid` at top level)."
            )
        from .optimize import optimize as _optimize

        try:
            opt_res = _optimize(
                dataset_id, base_spec, grid,
                score_metric=str(_pick(do_optimize, "score_metric", default="sharpe")),
                min_trades=int(_pick(do_optimize, "min_trades", default=20)),
                max_dd_floor=float(_pick(do_optimize, "max_dd_floor", default=-0.50)),
                top_n=int(_pick(do_optimize, "top_n", default=5)),
                max_combinations=max(100, int(_pick(do_optimize, "max_combinations", default=500))),
                init_cash=init_cash,
                persist=True,
            )
        except Exception as exc:
            return _tool_result_err(
                f"Optimise failed: {exc.__class__.__name__}: {exc}"
            )
        optimization_id = opt_res.opt_id
        opt_top_5 = [
            {"point": t["point"], "score": t["score"],
             "metrics": _compact_metrics(t.get("metrics") or {})}
            for t in opt_res.top_n[:5]
        ]
        # Best point becomes the spec for everything that follows.
        if opt_res.top_n:
            best_point = opt_res.top_n[0].get("spec_used")
            if isinstance(best_point, dict):
                final_spec_dict = best_point
        summary["stages"].append("optimize")

    # ── Stage 2: in-sample backtest (on final_spec_dict) ──────────────
    from .backtest import run_backtest as _run_backtest
    from .strategies import StrategySpec

    try:
        spec_obj = StrategySpec.model_validate(final_spec_dict)
    except Exception as exc:
        return _tool_result_err(f"Invalid spec after optimise: {exc}")

    try:
        bt_res = _run_backtest(
            dataset_id, spec_obj, init_cash=init_cash, persist=True
        )
    except Exception as exc:
        return _tool_result_err(
            f"Backtest failed: {exc.__class__.__name__}: {exc}"
        )
    summary["stages"].append("backtest")

    # ── Stage 3: walk-forward (optional) ───────────────────────────────
    wf_id: Optional[str] = None
    wf_payload: Optional[Dict[str, Any]] = None
    if do_wf:
        from .validate import walk_forward as _walk_forward

        try:
            wf_res = _walk_forward(
                dataset_id, spec_obj,
                grid=None,
                n_folds=int(input_.get("wf_n_folds", 4)),
                is_oos_split=float(input_.get("wf_is_oos_split", 0.7)),
                mode=str(input_.get("wf_mode", "rolling")),
                init_cash=init_cash,
                persist=True,
            )
            wf_id = wf_res.val_id
            # Compact subset for the LLM — no per-fold trade lists.
            wf_payload = {
                "walk_forward_id": wf_id,
                "n_folds": wf_res.n_folds,
                "wfe": wf_res.wfe,
                "verdict": wf_res.verdict,
                "aggregate": wf_res.aggregate,
            }
            summary["stages"].append("walk_forward")
        except Exception as exc:
            wf_payload = {"error": f"{exc.__class__.__name__}: {exc}"}

    # ── Stage 4: monte-carlo (optional) ────────────────────────────────
    mc_id: Optional[str] = None
    mc_payload: Optional[Dict[str, Any]] = None
    if do_mc:
        from .validate import monte_carlo as _monte_carlo

        try:
            mc_res = _monte_carlo(
                dataset_id, spec_obj,
                n_iterations=int(input_.get("mc_n_iterations", 1000)),
                init_cash=init_cash,
                seed=(int(input_["mc_seed"]) if "mc_seed" in input_ else None),
                persist=True,
            )
            mc_id = mc_res.val_id
            mc_payload = {
                "monte_carlo_id": mc_id,
                "n_iterations": mc_res.n_iterations,
                "p_value_positive_mean": mc_res.p_value_positive_mean,
                "expected_total_return": mc_res.expected_total_return,
                "expected_max_drawdown": mc_res.expected_max_drawdown,
                "survival_rate": mc_res.survival_rate,
                "dd_within_limit_rate": mc_res.dd_within_limit_rate,
                "verdict": mc_res.verdict,
            }
            summary["stages"].append("monte_carlo")
        except Exception as exc:
            mc_payload = {"error": f"{exc.__class__.__name__}: {exc}"}

    # ── Stage 5: composite score with strict gates ────────────────────
    from .scoring import score_backtest

    # Reload artifacts for scoring (it expects dicts, not dataclasses).
    bt_dict = _read_artifact("backtests", bt_res.bt_id) or {}
    mc_dict = _read_artifact("validations", mc_id) if mc_id else None
    wf_dict = _read_artifact("validations", wf_id) if wf_id else None

    score_res = score_backtest(
        bt_dict.get("metrics") or bt_res.metrics,
        bt_dict.get("significance") or bt_res.significance,
        mc=mc_dict,
        wf=wf_dict,
    )
    summary["stages"].append("score")

    # ── Stage 6: render report (optional) ──────────────────────────────
    report_payload: Optional[Dict[str, Any]] = None
    if do_render:
        try:
            from .reports import render_report as _render_report

            meta = _render_report(
                backtest_id=bt_res.bt_id,
                monte_carlo_id=mc_id,
                walk_forward_id=wf_id,
                optimization_id=optimization_id,
            )
            report_payload = {
                "report_id": meta.report_id,
                "title": meta.title,
                "html_url": f"{_REPORT_BASE_URL}/api/reports/{meta.report_id}",
                "pdf_url":  f"{_REPORT_BASE_URL}/api/reports/{meta.report_id}.pdf",
                "sections": meta.sections,
            }
            summary["stages"].append("report")
        except Exception as exc:
            report_payload = {"error": f"{exc.__class__.__name__}: {exc}"}

    # ── Compact final summary ──────────────────────────────────────────
    summary.update({
        "elapsed_sec": round(_time.perf_counter() - started, 2),
        "backtest_id": bt_res.bt_id,
        "metrics": _compact_metrics(bt_res.metrics),
        "data_usage_pct": bt_res.metrics.get("data_usage_pct"),
        "optimization_id": optimization_id,
        "optimization_top_5": opt_top_5 or None,
        "walk_forward": wf_payload,
        "monte_carlo": mc_payload,
        "score": {
            "score": score_res.score,
            "grade": score_res.grade,
            "verdict": score_res.verdict,
            "headline": score_res.headline,
            "confidence": score_res.confidence,
            "vetos": [
                {"rule": v.rule, "message": v.message} for v in score_res.vetos
            ],
            "notes": score_res.notes,
        },
        "report": report_payload,
        "final_spec_used": final_spec_dict,
    })

    return _tool_result_ok(summary)


def _pick(obj: Any, key: str, *, default: Any) -> Any:
    """Read ``key`` from ``obj`` if it's a dict, else fall back to default."""
    if isinstance(obj, dict) and key in obj:
        return obj[key]
    return default


def _read_artifact(subdir: str, file_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if not file_id:
        return None
    p = _find_artifact(subdir, file_id)
    if p is None:
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
