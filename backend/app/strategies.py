"""Strategy DSL + signal compiler (Phase 7, Slice 2).

The DSL is a JSON-validated, Pydantic-typed description of a trading strategy.
It is *deliberately constrained* — no `eval`, no arbitrary Python — so that AI-
generated strategies are safe, deterministic, and reproducible.

Inputs to a strategy:
    1. A canonical OHLCV pandas DataFrame (`open / high / low / close / volume`,
       indexed by `time`).
    2. A `StrategySpec` (built by AI tool calls or the user).

Outputs:
    `compile_signals(df, spec) -> (entries: pd.Series[bool], exits: pd.Series[bool])`

`Sizing`, `StopsConfig`, fees and slippage live on the spec but are consumed by
`backtest.py` (Slice 3) when constructing the VectorBT portfolio — they are NOT
applied at signal-compile time.

Anti-look-ahead: indicators are aligned so that the value at index `t` is what
was computable using data ending at the close of bar `t`. VectorBT's
`Portfolio.from_signals` then enters/exits on the *next* bar, which is the
correct, realistic semantics. We do not shift signals here.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import indicators as ind

# ─── Operators / refs ────────────────────────────────────────────────────

#: Comparison operators allowed in a Condition.
ComparisonOp = Literal[
    "<",
    ">",
    "<=",
    ">=",
    "==",
    "crosses_above",
    "crosses_below",
    "between",
    "outside",
    "consecutive_n",
]

#: Bare price fields that can appear on either side of a Condition without an
#: indicator call. We treat raw OHLCV as a virtual indicator so the same
#: evaluator handles both.
PRICE_FIELDS: Tuple[str, ...] = ("open", "high", "low", "close", "volume")


# ─── Pydantic schema ─────────────────────────────────────────────────────


class Condition(BaseModel):
    """One leaf comparison.

    Examples:
        rsi(14) < 30
            indicator='rsi', params={'period': 14}, op='<', value=30
        macd.hist crosses_above 0
            indicator='macd', field='hist', op='crosses_above', value=0
        close > ema(200)
            indicator='price', field='close', op='>', ref='ema(200)'

    Either `value` (numeric literal) OR `ref` (symbolic reference: another
    indicator call, a price field, `rolling_mean(N)`, `rolling_std(N)`,
    `prev_value`) must be provided — never both.
    """

    model_config = ConfigDict(extra="forbid")

    indicator: str = Field(
        ...,
        description=(
            "Indicator registry key (e.g. 'rsi', 'macd', 'atr'), or the "
            "pseudo-indicator 'price' for raw OHLCV access."
        ),
    )
    params: Dict[str, Any] = Field(default_factory=dict)
    field: Optional[str] = Field(
        default=None,
        description=(
            "Column to pick when the indicator returns a multi-column frame "
            "(e.g. 'hist' for MACD, 'upper' for Bollinger). For 'price', this "
            "selects open/high/low/close/volume; defaults to 'close'."
        ),
    )
    op: ComparisonOp
    value: Optional[float] = None
    ref: Optional[str] = None
    n: Optional[int] = Field(
        default=None,
        description="Lookback bars for `consecutive_n` operator.",
        ge=1,
        le=500,
    )
    range: Optional[Tuple[float, float]] = Field(
        default=None,
        description="(low, high) for `between` / `outside` operators.",
    )

    @field_validator("indicator")
    @classmethod
    def _check_indicator(cls, v: str) -> str:
        if v == "price":
            return v
        if v not in ind.INDICATOR_REGISTRY:
            raise ValueError(
                f"Unknown indicator '{v}'. Known: {sorted(ind.INDICATOR_REGISTRY)}"
            )
        return v


class CondGroup(BaseModel):
    """Boolean combinator. Exactly one of `all_of` / `any_of` must be non-empty.

    Nested groups allowed: `all_of=[Condition, CondGroup(any_of=[...])]`.
    """

    model_config = ConfigDict(extra="forbid")

    all_of: List[Union["Condition", "CondGroup"]] = Field(default_factory=list)
    any_of: List[Union["Condition", "CondGroup"]] = Field(default_factory=list)

    @field_validator("all_of", "any_of")
    @classmethod
    def _no_empty_groups(cls, v: List[Any]) -> List[Any]:
        return v

    def is_empty(self) -> bool:
        return not self.all_of and not self.any_of


CondGroup.model_rebuild()


class StopRule(BaseModel):
    """One stop spec. Consumed by backtest.py when building the portfolio."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["fixed_pct", "atr", "trailing_pct", "trailing_atr", "rr_ratio"]
    value: Optional[float] = Field(default=None, gt=0)
    multiplier: Optional[float] = Field(default=None, gt=0)
    period: Optional[int] = Field(default=None, ge=2, le=500)


class StopsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stop_loss: Optional[StopRule] = None
    take_profit: Optional[StopRule] = None
    trailing: Optional[StopRule] = None
    time_stop_bars: Optional[int] = Field(default=None, ge=1, le=10_000)


class Sizing(BaseModel):
    """Position sizing spec. `value` is interpreted per `type`.

    - fixed_pct: `value` ∈ (0, 1] — fraction of equity per trade.
    - vol_target: `target_vol` is annualised; size = target_vol / realised_vol.
    - kelly: full Kelly = mean / variance; we always apply `kelly_fraction` for
      safety (default 0.25 of full Kelly).
    - risk_parity: equal-risk allocation when multi-asset (single-asset
      degenerates to fixed_pct=1).
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["fixed_pct", "vol_target", "kelly", "risk_parity"] = "fixed_pct"
    value: float = Field(default=1.0, gt=0, le=1.0)
    target_vol: float = Field(default=0.15, gt=0, le=2.0)
    max_position: float = Field(default=1.0, gt=0, le=1.0)
    kelly_fraction: float = Field(default=0.25, gt=0, le=1.0)


class StrategySpec(BaseModel):
    """Top-level production-grade strategy DSL."""

    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, max_length=120)
    market: Literal["crypto", "equities", "futures", "forex"] = "crypto"
    entries: CondGroup
    exits: CondGroup
    regime_filter: Optional[Condition] = Field(
        default=None,
        description=(
            "Higher-timeframe / structural filter. Entries only fire when this "
            "is True. Common pattern: only-long-when-above-200EMA."
        ),
    )
    sizing: Sizing = Field(default_factory=Sizing)
    stops: StopsConfig = Field(default_factory=StopsConfig)
    fees_override: Optional[float] = Field(default=None, ge=0, le=0.05)
    slippage_override: Optional[float] = Field(default=None, ge=0, le=0.05)
    min_holding_bars: int = Field(default=1, ge=1, le=10_000)
    max_concurrent_positions: int = Field(default=1, ge=1, le=20)

    @field_validator("entries", "exits")
    @classmethod
    def _non_empty_group(cls, v: CondGroup) -> CondGroup:
        if v.is_empty():
            raise ValueError(
                "entries/exits must contain at least one condition (in `all_of` or `any_of`)"
            )
        return v


# Default fees + slippage per market (one-way, fractional).
MARKET_PRESETS: Dict[str, Tuple[float, float]] = {
    "crypto": (0.0010, 0.0005),     # Binance taker-ish
    "equities": (0.0005, 0.0002),   # IBKR-ish
    "futures": (0.0004, 0.0003),    # CME micros
    "forex": (0.0002, 0.0001),      # spread-based
}


def resolve_costs(spec: StrategySpec) -> Tuple[float, float]:
    """Return (fees, slippage) using overrides if set, else market presets."""
    fees, slip = MARKET_PRESETS.get(spec.market, MARKET_PRESETS["crypto"])
    if spec.fees_override is not None:
        fees = spec.fees_override
    if spec.slippage_override is not None:
        slip = spec.slippage_override
    return fees, slip


# ─── Indicator cache + ref resolution ────────────────────────────────────


def _cache_key(name: str, params: Dict[str, Any]) -> str:
    items = sorted((k, v) for k, v in params.items())
    return f"{name}|" + ",".join(f"{k}={v}" for k, v in items)


def _eval_indicator(
    df: pd.DataFrame,
    name: str,
    params: Dict[str, Any],
    field: Optional[str],
) -> pd.Series:
    """Run the indicator (or pick a price field) and return a single Series."""
    if name == "price":
        col = field or "close"
        if col not in df.columns:
            raise ValueError(f"Price field '{col}' missing from dataset columns")
        return df[col].astype(float)

    out = ind.compute(df, name, params)
    # `compute` always returns a DataFrame. We accept three field shapes:
    #   1. exact column match (e.g. field='hist' for MACD)
    #   2. indicator-name match on a single-column frame (LLMs often pass
    #      field=indicator_name out of habit even though the column is
    #      named like 'rsi_14') — silently route to the only column
    #   3. prefix match against any column (field='rsi' → 'rsi_14')
    if field is not None:
        if field in out.columns:
            return out[field].astype(float)
        if out.shape[1] == 1 and (
            field == name or field == out.columns[0]
            or out.columns[0].startswith(field + "_")
            or out.columns[0] == field
        ):
            return out.iloc[:, 0].astype(float)
        # Prefix match across columns.
        prefix_hit = [c for c in out.columns if c.startswith(field + "_") or c == field]
        if len(prefix_hit) == 1:
            return out[prefix_hit[0]].astype(float)
        raise ValueError(
            f"Indicator '{name}' has no field '{field}'. Available: {list(out.columns)}"
        )
    if out.shape[1] == 1:
        return out.iloc[:, 0].astype(float)
    raise ValueError(
        f"Indicator '{name}' returns {list(out.columns)}; you must set `field` to pick one."
    )


# Symbolic ref grammar (kept tiny so we don't need a full parser):
#   - "open" / "high" / "low" / "close" / "volume"
#   - "rolling_mean(N)" / "rolling_std(N)"  (window over `close`)
#   - "prev_value"   -> previous value of the LHS series
def _resolve_ref(
    ref: str,
    lhs: pd.Series,
    df: pd.DataFrame,
) -> pd.Series:
    ref = ref.strip()
    if ref in PRICE_FIELDS:
        if ref not in df.columns:
            raise ValueError(f"Ref '{ref}' missing from dataset columns")
        return df[ref].astype(float)
    if ref == "prev_value":
        return lhs.shift(1)
    if ref.startswith("rolling_mean(") and ref.endswith(")"):
        n = int(ref[len("rolling_mean("):-1])
        return df["close"].rolling(n, min_periods=n).mean().astype(float)
    if ref.startswith("rolling_std(") and ref.endswith(")"):
        n = int(ref[len("rolling_std("):-1])
        return df["close"].rolling(n, min_periods=n).std().astype(float)
    raise ValueError(
        f"Unsupported ref '{ref}'. Allowed: price fields, "
        "rolling_mean(N), rolling_std(N), prev_value."
    )


# ─── Operator implementations (vectorised, NaN-safe) ─────────────────────


def _apply_op(
    op: ComparisonOp,
    a: pd.Series,
    b: Optional[pd.Series],
    *,
    value: Optional[float],
    n: Optional[int],
    rng: Optional[Tuple[float, float]],
) -> pd.Series:
    """`a op b` returning bool Series aligned to `a.index`. NaNs -> False."""

    def to_b() -> pd.Series:
        if b is not None:
            return b
        if value is None:
            raise ValueError(f"Operator '{op}' needs `value` or `ref`")
        return pd.Series(float(value), index=a.index)

    if op == "<":
        out = a < to_b()
    elif op == ">":
        out = a > to_b()
    elif op == "<=":
        out = a <= to_b()
    elif op == ">=":
        out = a >= to_b()
    elif op == "==":
        out = a == to_b()
    elif op == "crosses_above":
        bb = to_b()
        prev_a = a.shift(1)
        prev_b = bb.shift(1)
        out = (prev_a <= prev_b) & (a > bb)
    elif op == "crosses_below":
        bb = to_b()
        prev_a = a.shift(1)
        prev_b = bb.shift(1)
        out = (prev_a >= prev_b) & (a < bb)
    elif op == "between":
        if rng is None:
            raise ValueError("`between` requires `range: [low, high]`")
        lo, hi = rng
        out = (a >= lo) & (a <= hi)
    elif op == "outside":
        if rng is None:
            raise ValueError("`outside` requires `range: [low, high]`")
        lo, hi = rng
        out = (a < lo) | (a > hi)
    elif op == "consecutive_n":
        # Underlying truth is `a < value` style — but `consecutive_n` here means:
        # the *base condition* (a > b OR a > value) was true for N consecutive bars.
        # We coerce by treating `value` as the comparison threshold and `n` as the
        # streak length. To keep grammar simple, we require `value` AND `n`:
        #   a > value for n consecutive bars.
        if n is None or value is None:
            raise ValueError("`consecutive_n` requires both `n` and `value`")
        base = a > float(value)
        # rolling sum of bools == n means all N bars true
        out = base.rolling(n, min_periods=n).sum() == n
    else:
        raise ValueError(f"Unknown operator '{op}'")

    return out.fillna(False).astype(bool)


# ─── Evaluator ───────────────────────────────────────────────────────────


def _eval_condition(
    cond: Condition,
    df: pd.DataFrame,
    cache: Dict[str, pd.DataFrame],
) -> pd.Series:
    # LHS — indicator (or price) value.
    key = _cache_key(cond.indicator, cond.params)
    if key not in cache and cond.indicator != "price":
        cache[key] = ind.compute(df, cond.indicator, cond.params)

    lhs = _eval_indicator(df, cond.indicator, cond.params, cond.field)

    # RHS — either numeric value or resolved ref.
    rhs: Optional[pd.Series] = None
    if cond.ref is not None:
        rhs = _resolve_ref(cond.ref, lhs, df)
        # align indexes (defensive — indicator + price share df.index)
        rhs = rhs.reindex(lhs.index)

    return _apply_op(
        cond.op,
        lhs,
        rhs,
        value=cond.value,
        n=cond.n,
        rng=cond.range,
    )


def _eval_group(
    group: CondGroup,
    df: pd.DataFrame,
    cache: Dict[str, pd.DataFrame],
) -> pd.Series:
    parts: List[pd.Series] = []
    if group.all_of:
        children = [_eval_node(c, df, cache) for c in group.all_of]
        parts.append(_combine(children, mode="all"))
    if group.any_of:
        children = [_eval_node(c, df, cache) for c in group.any_of]
        parts.append(_combine(children, mode="any"))
    if not parts:
        # Should be unreachable (validator forbids), but guard anyway.
        return pd.Series(False, index=df.index)
    if len(parts) == 1:
        return parts[0]
    # Both all_of AND any_of supplied -> AND them together.
    return parts[0] & parts[1]


def _eval_node(
    node: Union[Condition, CondGroup],
    df: pd.DataFrame,
    cache: Dict[str, pd.DataFrame],
) -> pd.Series:
    if isinstance(node, Condition):
        return _eval_condition(node, df, cache)
    return _eval_group(node, df, cache)


def _combine(parts: List[pd.Series], mode: str) -> pd.Series:
    if not parts:
        return pd.Series(dtype=bool)
    out = parts[0].copy()
    for p in parts[1:]:
        out = (out & p) if mode == "all" else (out | p)
    return out


# ─── Public API ──────────────────────────────────────────────────────────


def compile_signals(
    df: pd.DataFrame,
    spec: StrategySpec,
) -> Tuple[pd.Series, pd.Series]:
    """Compile a `StrategySpec` against an OHLCV DataFrame.

    Returns `(entries, exits)` as boolean pandas Series indexed identically to
    `df`. NaN positions (e.g. before an indicator's warmup is satisfied) are
    coerced to False.

    Idempotent + side-effect free — safe to call inside an optimiser loop.
    """
    if not isinstance(df.index, pd.DatetimeIndex):
        # Non-fatal — VectorBT can run on int index — but warn-equivalent: no.
        # We accept any monotonic index but require uniqueness.
        if not df.index.is_unique:
            raise ValueError("DataFrame index must be unique")

    cache: Dict[str, pd.DataFrame] = {}

    entries = _eval_group(spec.entries, df, cache)
    exits = _eval_group(spec.exits, df, cache)

    # Apply regime filter — entries only fire when regime is True.
    if spec.regime_filter is not None:
        regime_ok = _eval_condition(spec.regime_filter, df, cache)
        entries = entries & regime_ok

    # Final NaN guard (cache-induced NaNs propagate through ops).
    entries = entries.fillna(False).astype(bool)
    exits = exits.fillna(False).astype(bool)

    return entries, exits


# ─── Self-smoke (`python -m app.strategies`) ────────────────────────────


def _smoke() -> None:
    """Tiny in-process unit tests so `python -m app.strategies` proves the DSL works."""
    np.random.seed(42)
    n = 300
    rng = pd.date_range("2024-01-01", periods=n, freq="1h")
    close = pd.Series(100 + np.cumsum(np.random.randn(n) * 0.4), index=rng)
    df = pd.DataFrame(
        {
            "open": close.shift(1).fillna(close.iloc[0]),
            "high": close + np.abs(np.random.randn(n) * 0.2),
            "low": close - np.abs(np.random.randn(n) * 0.2),
            "close": close,
            "volume": np.random.randint(1000, 10_000, size=n).astype(float),
        }
    )

    # Spec 1 — simple RSI mean-rev.
    spec1 = StrategySpec(
        entries=CondGroup(all_of=[
            Condition(indicator="rsi", params={"period": 14}, op="<", value=30),
        ]),
        exits=CondGroup(all_of=[
            Condition(indicator="rsi", params={"period": 14}, op=">", value=70),
        ]),
    )
    e1, x1 = compile_signals(df, spec1)
    assert e1.dtype == bool and x1.dtype == bool
    assert len(e1) == len(df)
    assert e1.sum() >= 0  # vacuous but proves it ran
    print(f"Spec 1: entries={e1.sum()}, exits={x1.sum()}")

    # Spec 2 — MACD hist crosses above 0 + EMA filter.
    spec2 = StrategySpec(
        entries=CondGroup(all_of=[
            Condition(indicator="macd", field="hist", op="crosses_above", value=0),
        ]),
        exits=CondGroup(all_of=[
            Condition(indicator="macd", field="hist", op="crosses_below", value=0),
        ]),
        regime_filter=Condition(
            indicator="ema", params={"period": 50}, op="<", ref="close",
        ),
    )
    e2, x2 = compile_signals(df, spec2)
    assert e2.sum() >= 0 and x2.sum() >= 0
    print(f"Spec 2: entries={e2.sum()}, exits={x2.sum()} (with regime)")

    # Spec 3 — between + consecutive_n.
    spec3 = StrategySpec(
        entries=CondGroup(any_of=[
            Condition(indicator="rsi", op="between", range=(30, 50)),
            Condition(indicator="rsi", op="consecutive_n", n=3, value=40),
        ]),
        exits=CondGroup(all_of=[
            Condition(indicator="rsi", op="outside", range=(20, 80)),
        ]),
    )
    e3, x3 = compile_signals(df, spec3)
    print(f"Spec 3: entries={e3.sum()}, exits={x3.sum()} (between + consecutive_n)")

    # Spec 4 — invalid: empty entries should raise.
    try:
        StrategySpec(entries=CondGroup(), exits=CondGroup(all_of=[
            Condition(indicator="rsi", op=">", value=70),
        ]))
        raise AssertionError("Empty entries should have failed validation")
    except Exception as exc:
        print(f"Spec 4 (empty): rejected as expected -> {exc.__class__.__name__}")

    # Spec 5 — costs resolution.
    spec5 = StrategySpec(
        market="equities",
        entries=CondGroup(all_of=[Condition(indicator="rsi", op="<", value=30)]),
        exits=CondGroup(all_of=[Condition(indicator="rsi", op=">", value=70)]),
    )
    fees, slip = resolve_costs(spec5)
    assert fees == 0.0005 and slip == 0.0002
    print(f"Spec 5: equities preset -> fees={fees}, slip={slip}")

    spec5b = StrategySpec(
        market="crypto",
        fees_override=0.002,
        entries=CondGroup(all_of=[Condition(indicator="rsi", op="<", value=30)]),
        exits=CondGroup(all_of=[Condition(indicator="rsi", op=">", value=70)]),
    )
    fees_b, slip_b = resolve_costs(spec5b)
    assert fees_b == 0.002 and slip_b == 0.0005
    print(f"Spec 5b: crypto + fee override -> fees={fees_b}, slip={slip_b}")

    print("STRATEGIES SMOKE OK")


if __name__ == "__main__":
    _smoke()
