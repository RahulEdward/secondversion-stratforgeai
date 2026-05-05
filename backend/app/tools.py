"""Tool schemas the AI orchestrator exposes to LLMs.

Each schema follows Anthropic's tool format (also broadly compatible with OpenAI
function-calling — the ChatGPT subscription provider re-shapes them at the wire).
Tool names match dispatcher entries in :mod:`app.tool_exec` so adding a tool here
is enough to expose it; the executor already knows how to run it.
"""

from __future__ import annotations

from typing import Any, Dict, List

from .indicators import INDICATOR_REGISTRY

# Column used for indicators that accept a "column" parameter.
_COLUMN_ENUM = ["open", "high", "low", "close", "volume"]


def _number_schema(default: float | int) -> Dict[str, Any]:
    return {"type": "number", "default": default}


def _int_schema(default: int, minimum: int = 2) -> Dict[str, Any]:
    return {"type": "integer", "default": default, "minimum": minimum}


def _param_schema(name: str, default: object) -> Dict[str, Any]:
    """Best-effort JSON schema for an indicator parameter based on its default type."""
    if name == "column":
        return {"type": "string", "enum": _COLUMN_ENUM, "default": default}
    if isinstance(default, bool):
        return {"type": "boolean", "default": default}
    if isinstance(default, int):
        return _int_schema(default)
    if isinstance(default, float):
        return _number_schema(default)
    return {"type": "string", "default": default}


def _indicator_tool_schema(name: str, entry: dict) -> Dict[str, Any]:
    params_schema: Dict[str, Any] = {}
    for pname, default in entry["params"].items():
        params_schema[pname] = _param_schema(pname, default)
    return {
        "name": f"compute_{name}",
        "description": (
            f"{entry['description']} Runs against the currently-selected dataset."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "dataset_id": {
                    "type": "string",
                    "description": "Dataset ID (ds_...) to run this indicator on.",
                },
                **params_schema,
            },
            "required": ["dataset_id"],
        },
    }


def indicator_tools() -> List[Dict[str, Any]]:
    """Return the full list of indicator tool schemas."""
    return [
        _indicator_tool_schema(name, entry)
        for name, entry in INDICATOR_REGISTRY.items()
    ]


# ─── Phase 7 / 8 / 9 — strategy DSL + workflow tool schemas ──────────────


# Concrete JSON Schema for the StrategySpec DSL.
#
# A loose ``{"type": "object", "additionalProperties": true}`` was tried
# first — but the OpenAI Responses API tool-calling layer needs concrete
# ``properties`` to anchor what the model should generate. With nothing to
# anchor on, GPT-5.x silently *omits* the field entirely, which surfaces
# downstream as ``Missing required \`strategy_spec\``` errors. The schema
# below is therefore explicit per-field; the server-side Pydantic validator
# in ``app.strategies.StrategySpec`` is still the source of truth and will
# reject malformed payloads.


def _condition_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "description": (
            "One leaf comparison. Use `value` for a numeric RHS or `ref` "
            "for a symbolic RHS (`close`, `prev_value`, `rolling_mean(N)`, "
            "...). `field` picks a column when the indicator returns a "
            "multi-column frame (e.g. `hist` for MACD, `upper` for "
            "Bollinger). For the pseudo-indicator `price`, `field` selects "
            "open/high/low/close/volume."
        ),
        "properties": {
            "indicator": {
                "type": "string",
                "description": (
                    "Indicator key (rsi, macd, atr, sma, ema, "
                    "bollinger_bands, stochastic, adx, ...) or `price` "
                    "for raw OHLCV access."
                ),
            },
            "params": {
                "type": "object",
                "description": "Indicator params, e.g. {\"period\": 14}.",
                "additionalProperties": True,
            },
            "field": {"type": "string"},
            "op": {
                "type": "string",
                "enum": [
                    "<", ">", "<=", ">=", "==",
                    "crosses_above", "crosses_below",
                    "between", "outside", "consecutive_n",
                ],
            },
            "value": {
                "type": "number",
                "description": "Numeric RHS — use either value OR ref, not both.",
            },
            "ref": {
                "type": "string",
                "description": (
                    "Symbolic RHS: `open`/`high`/`low`/`close`/`volume`, "
                    "`prev_value`, `rolling_mean(N)`, `rolling_std(N)`. "
                    "CRITICAL: You CANNOT put indicators like 'donchian.lower' here! "
                    "If comparing an indicator against price, put the indicator on the LHS (as the `indicator` field) and put `close` as the `ref`. Invert the `op` if needed (e.g., 'price crosses below indicator' -> 'indicator crosses above close')."
                ),
            },
            "n": {"type": "integer", "description": "Lookback for `consecutive_n`."},
            "range": {
                "type": "array",
                "items": {"type": "number"},
                "description": "[low, high] for `between` / `outside`.",
            },
        },
        "required": ["indicator", "op"],
    }


def _cond_group_schema() -> Dict[str, Any]:
    cond = _condition_schema()
    return {
        "type": "object",
        "description": (
            "Boolean combinator. Populate `all_of` (AND) or `any_of` (OR) "
            "with at least one Condition; leave the other empty."
        ),
        "properties": {
            "all_of": {"type": "array", "items": cond},
            "any_of": {"type": "array", "items": cond},
        },
    }


def _stop_rule_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "enum": [
                    "fixed_pct", "atr",
                    "trailing_pct", "trailing_atr",
                    "rr_ratio",
                ],
            },
            "value": {"type": "number"},
            "multiplier": {"type": "number"},
            "period": {"type": "integer"},
        },
        "required": ["type"],
    }


def _strategy_spec_schema(description: str) -> Dict[str, Any]:
    """Concrete JSON-Schema for a StrategySpec — see ``app.strategies``."""
    cond = _condition_schema()
    grp = _cond_group_schema()
    stop = _stop_rule_schema()
    return {
        "type": "object",
        "description": description,
        "properties": {
            "name": {"type": "string"},
            "market": {
                "type": "string",
                "enum": ["crypto", "equities", "futures", "forex"],
                "default": "crypto",
            },
            "entries": grp,
            "exits": grp,
            "regime_filter": cond,
            "sizing": {
                "type": "object",
                "description": (
                    "Position sizing. `value` is fraction-of-equity for "
                    "`fixed_pct` (0..1)."
                ),
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": [
                            "fixed_pct", "vol_target", "kelly", "risk_parity",
                        ],
                        "default": "fixed_pct",
                    },
                    "value": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                        "default": 1.0,
                    },
                    "target_vol": {"type": "number", "default": 0.15},
                    "max_position": {"type": "number", "default": 1.0},
                    "kelly_fraction": {"type": "number", "default": 0.25},
                },
            },
            "stops": {
                "type": "object",
                "description": "Stop-loss / take-profit / trailing.",
                "properties": {
                    "stop_loss": stop,
                    "take_profit": stop,
                    "trailing": stop,
                    "time_stop_bars": {"type": "integer"},
                },
            },
            "fees_override": {
                "type": "number",
                "minimum": 0,
                "maximum": 0.05,
                "description": "One-way fees as fraction (0.001 = 10bps).",
            },
            "slippage_override": {
                "type": "number",
                "minimum": 0,
                "maximum": 0.05,
            },
            "min_holding_bars": {
                "type": "integer",
                "minimum": 1,
                "default": 1,
            },
            "max_concurrent_positions": {
                "type": "integer",
                "minimum": 1,
                "default": 1,
            },
        },
        "required": ["entries", "exits"],
    }


def _backtest_tool_schemas() -> List[Dict[str, Any]]:
    """Phase 7 — run / optimize / walk-forward / monte-carlo / score."""
    return [
        {
            "name": "run_backtest",
            "description": (
                "Run a single VectorBT backtest of the given strategy on the "
                "active dataset. Persists a backtest_id you can pass to "
                "score_strategy or render_report."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "dataset_id": {
                        "type": "string",
                        "description": "Dataset ID (ds_...) to backtest on.",
                    },
                    "strategy_spec": _strategy_spec_schema(
                        "Trading strategy DSL. MUST be passed in every "
                        "run_backtest call — required keys are `entries` "
                        "and `exits`, each a CondGroup containing at least "
                        "one Condition."
                    ),
                    "init_cash": {
                        "type": "number",
                        "default": 10_000.0,
                        "minimum": 1.0,
                    },
                },
                "required": ["dataset_id", "strategy_spec"],
            },
        },
        {
            "name": "optimize_strategy",
            "description": (
                "Sweep a parameter grid against `base_spec` and return the "
                "top-N points by score_metric (default sharpe). `grid` keys "
                "are dotted paths into the spec, e.g. "
                "`\"entries.all_of.0.params.period\": [10,12,14,16]` or "
                "`\"stops.stop_loss.value\": [0.01,0.02]`. Caps at 500 combos "
                "by default — bump max_combinations if you need more."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "dataset_id": {"type": "string"},
                    "base_spec": _strategy_spec_schema(
                        "Baseline StrategySpec (same shape as run_backtest)."
                    ),
                    "grid": {
                        "type": "object",
                        "description": (
                            "Map of `dotted.path → [values]` to sweep. "
                            "Each combination becomes one backtest."
                        ),
                        "additionalProperties": {
                            "type": "array",
                            "items": {},
                        },
                    },
                    "score_metric": {
                        "type": "string",
                        "enum": [
                            "sharpe", "sortino", "calmar",
                            "total_return", "cagr", "profit_factor",
                        ],
                        "default": "sharpe",
                    },
                    "min_trades": {"type": "integer", "default": 20, "minimum": 1},
                    "max_dd_floor": {
                        "type": "number",
                        "default": -0.50,
                        "description": "Reject combos with max_drawdown worse than this.",
                    },
                    "top_n": {"type": "integer", "default": 10, "minimum": 1},
                    "max_combinations": {"type": "integer", "default": 500, "minimum": 1},
                    "init_cash": {"type": "number", "default": 10_000.0},
                },
                "required": ["dataset_id", "base_spec", "grid"],
            },
        },
        {
            "name": "walk_forward",
            "description": (
                "Walk-forward validation: split the data into rolling/anchored "
                "in-sample / out-of-sample folds, optionally re-optimise on each "
                "in-sample window, and score out-of-sample to detect overfit."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "dataset_id": {"type": "string"},
                    "base_spec": _strategy_spec_schema("Baseline StrategySpec."),
                    "grid": {
                        "type": "object",
                        "description": (
                            "Optional per-fold optimisation grid. Same format "
                            "as optimize_strategy.grid. Omit to skip per-fold "
                            "re-optimisation."
                        ),
                    },
                    "n_folds": {"type": "integer", "default": 5, "minimum": 2},
                    "is_oos_split": {
                        "type": "number",
                        "default": 0.7,
                        "minimum": 0.5,
                        "maximum": 0.95,
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["rolling", "anchored"],
                        "default": "rolling",
                    },
                    "score_metric": {
                        "type": "string",
                        "default": "sharpe",
                    },
                    "min_trades": {"type": "integer", "default": 10},
                    "max_dd_floor": {"type": "number", "default": -0.50},
                    "max_combinations": {"type": "integer", "default": 200},
                    "init_cash": {"type": "number", "default": 10_000.0},
                },
                "required": ["dataset_id", "base_spec"],
            },
        },
        {
            "name": "monte_carlo",
            "description": (
                "Bootstrap the trade distribution from a backtest spec and "
                "report 5/50/95 percentile equity curves + p-values for "
                "positive-mean and beat-zero return."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "dataset_id": {"type": "string"},
                    "strategy_spec": _strategy_spec_schema(
                        "StrategySpec to backtest then resample."
                    ),
                    "n_iterations": {
                        "type": "integer",
                        "default": 2000,
                        "minimum": 100,
                        "maximum": 10_000,
                    },
                    "init_cash": {"type": "number", "default": 10_000.0},
                    "seed": {
                        "type": "integer",
                        "description": "Optional RNG seed for reproducibility.",
                    },
                },
                "required": ["dataset_id", "strategy_spec"],
            },
        },
        {
            "name": "score_strategy",
            "description": (
                "Composite grade (A+/A/.../F) for a backtest, optionally "
                "boosted by Monte-Carlo and Walk-Forward artifacts. Pass "
                "`save_as` to auto-save to the strategy library when grade "
                "qualifies."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "backtest_id": {"type": "string"},
                    "monte_carlo_id": {"type": "string"},
                    "walk_forward_id": {"type": "string"},
                    "save_as": {
                        "type": "string",
                        "description": "Library name. If set, auto-saves on B-/+ or better.",
                    },
                    "save_description": {"type": "string"},
                },
                "required": ["backtest_id"],
            },
        },
    ]


def _report_tool_schemas() -> List[Dict[str, Any]]:
    """Phase 8 — render the artifact panel HTML/PDF report."""
    return [
        {
            "name": "render_report",
            "description": (
                "Render an HTML report for the artifacts panel covering "
                "metrics, equity curve, trades, and (when supplied) "
                "optimisation / walk-forward / Monte-Carlo sections. Returns "
                "report_id + html_url + pdf_url."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "backtest_id": {"type": "string"},
                    "monte_carlo_id": {"type": "string"},
                    "walk_forward_id": {"type": "string"},
                    "optimization_id": {"type": "string"},
                },
                "required": ["backtest_id"],
            },
        }
    ]


def _library_tool_schemas() -> List[Dict[str, Any]]:
    """Phase 9 — strategy library save / load / list."""
    return [
        {
            "name": "save_strategy",
            "description": (
                "Save a strategy to the project library. Either pass "
                "`backtest_id` (preferred — copies the spec + grade from the "
                "run) or pass `strategy_spec` + `project_id` directly."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "backtest_id": {"type": "string"},
                    "strategy_spec": _strategy_spec_schema(
                        "Spec to save when `backtest_id` is omitted."
                    ),
                    "project_id": {
                        "type": "string",
                        "description": "Required only when saving from a raw spec.",
                    },
                    "monte_carlo_id": {"type": "string"},
                    "walk_forward_id": {"type": "string"},
                },
                "required": ["name"],
            },
        },
        {
            "name": "load_strategy",
            "description": "Fetch a saved strategy by id (returns the full spec).",
            "input_schema": {
                "type": "object",
                "properties": {
                    "strategy_id": {"type": "string"},
                },
                "required": ["strategy_id"],
            },
        },
        {
            "name": "list_strategies",
            "description": (
                "List saved strategies. Pass `project_id` to scope, omit for "
                "all projects."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "string"},
                },
            },
        },
    ]


def _pipeline_tool_schemas() -> List[Dict[str, Any]]:
    """Phase 7+ — single-call pipeline (token-efficient).

    Lets the LLM produce ONE strategy_spec, then call this tool once to
    get back a compact summary with grade + report_id. Diagram's
    "AI Called Only 2-3 Times" guarantee.
    """
    return [
        {
            "name": "run_full_pipeline",
            "description": (
                "Run the entire validation pipeline server-side in one "
                "call: in-sample backtest, optional grid optimisation, "
                "walk-forward, Monte-Carlo, composite score, and HTML "
                "report. Returns a compact summary (grade, vetos, "
                "report_id, html_url) — intermediate metrics stay on "
                "the server. PREFER THIS over chaining individual tools "
                "when the user asks for the full pipeline; it saves "
                "~95% of tokens vs. round-tripping every step."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "dataset_id": {"type": "string"},
                    "strategy_spec": _strategy_spec_schema(
                        "Base StrategySpec — same shape as run_backtest. "
                        "If `optimize` is enabled, the best optimised spec "
                        "is used for walk-forward + Monte-Carlo + report."
                    ),
                    "optimize": {
                        "type": "boolean",
                        "description": "Set to true to run grid optimization. If true, you MUST also provide `optimize_grid`.",
                    },
                    "optimize_grid": {
                        "type": "object",
                        "description": (
                            "REQUIRED if `optimize` is true. Map of `dotted.path → [values]` to sweep. "
                            "Example: {\"entries.all_of.0.params.period\": [10, 14, 21]}"
                        ),
                    },
                    "optimize_score_metric": {
                        "type": "string",
                        "enum": ["sharpe", "sortino", "calmar", "total_return", "profit_factor"],
                        "description": "Optional target metric when `optimize` is true (default: sharpe)."
                    },
                    "walk_forward": {
                        "type": "boolean",
                        "default": True,
                        "description": "Enable walk-forward validation.",
                    },
                    "wf_n_folds": {"type": "integer", "default": 4},
                    "wf_is_oos_split": {"type": "number", "default": 0.7},
                    "wf_mode": {"type": "string", "enum": ["rolling", "anchored"], "default": "rolling"},
                    "monte_carlo": {
                        "type": "boolean",
                        "default": True,
                        "description": "Enable Monte-Carlo bootstrap.",
                    },
                    "mc_n_iterations": {"type": "integer", "default": 1000},
                    "mc_seed": {"type": "integer"},
                    "render": {
                        "type": "boolean",
                        "default": True,
                        "description": "Render the HTML+PDF report at the end.",
                    },
                    "init_cash": {"type": "number", "default": 10_000.0},
                },
                "required": ["dataset_id", "strategy_spec"],
            },
        }
    ]


def _export_tool_schemas() -> List[Dict[str, Any]]:
    """Strategy export tools — Pine Script, signal messages."""
    return [
        {
            "name": "export_pine_script",
            "description": (
                "Export a saved strategy to TradingView Pine Script v5. "
                "Pass either `strategy_id` (from the library) or "
                "`backtest_id` (from a recent pipeline run)."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "strategy_id": {"type": "string"},
                    "backtest_id": {"type": "string"},
                },
            },
        },
        {
            "name": "export_signal_message",
            "description": (
                "Format a strategy as a Telegram/Discord signal message "
                "with key metrics, entry/exit summary, and risk management. "
                "Pass `backtest_id` or `strategy_id`."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "strategy_id": {"type": "string"},
                    "backtest_id": {"type": "string"},
                },
            },
        },
    ]


def all_tools() -> List[Dict[str, Any]]:
    """Aggregate every tool the orchestrator exposes to the LLM.

    Indicators (Phase 3) + Phase 7 backtest/optimise/validate/score +
    Phase 7+ pipeline single-tool + Phase 8 report renderer + Phase 9
    library + export tools + agent system tools.
    """
    from .agent_tools import tool_schemas as agent_tool_schemas

    return (
        indicator_tools()
        + _backtest_tool_schemas()
        + _pipeline_tool_schemas()
        + _report_tool_schemas()
        + _library_tool_schemas()
        + _export_tool_schemas()
        + agent_tool_schemas()
    )
